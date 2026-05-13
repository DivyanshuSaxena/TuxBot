#!/usr/bin/env python3
"""Dependency-free tabular Q-learning tuner over a discretized parameter space."""

import logging
import math
import random
from typing import Any, Dict, List

from ..benchmark import BenchmarkMetrics
from .base import TunerInterface, TunerResponse

logger = logging.getLogger(__name__)


class QLearningTuner(TunerInterface):
    """Q-learning tuner for small discrete or discretized search spaces."""

    def __init__(self, config):
        self.config = config
        if config.parameters_to_tune is not None:
            self.parameter_ranges = {
                key: value
                for key, value in config.parameter_ranges.items()
                if key in config.parameters_to_tune
            }
        else:
            self.parameter_ranges = dict(config.parameter_ranges)
        self.fixed_parameters = getattr(config, "fixed_parameters", {})
        self.optimization_metric = config.optimization_metric
        self.optimization_goal = config.optimization_goal

        self.grid_points = int(getattr(config, "qlearning_grid_points", 10))
        self.max_actions = int(getattr(config, "qlearning_max_actions", 1000))
        self.learning_rate = float(getattr(config, "qlearning_learning_rate", 0.1))
        self.epsilon = float(getattr(config, "qlearning_epsilon_start", 1.0))
        self.epsilon_end = float(getattr(config, "qlearning_epsilon_end", 0.1))
        self.epsilon_decay = float(getattr(config, "qlearning_epsilon_decay", 0.995))
        self.gamma = float(getattr(config, "qlearning_gamma", 0.99))
        self.seed = getattr(config, "qlearning_seed", None)
        if self.seed is not None:
            random.seed(int(self.seed))

        self.param_names = list(self.parameter_ranges)
        self.discretized_ranges = self._create_discretized_ranges()
        self.action_space_size = self._action_space_size()
        if self.action_space_size > self.max_actions:
            raise ValueError(
                f"Q-learning action space is too large ({self.action_space_size} > {self.max_actions}). "
                "Tune fewer parameters, lower qlearning_grid_points, or raise qlearning_max_actions."
            )

        self.q_table: Dict[tuple[int, int], float] = {}
        self.current_state: int | None = None
        self.last_action: int | None = None
        logger.info("Initialized Q-learning tuner with %d actions", self.action_space_size)

    def _create_discretized_ranges(self) -> Dict[str, List[Any]]:
        discretized: Dict[str, List[Any]] = {}
        for param_name, param_range in self.parameter_ranges.items():
            if isinstance(param_range, tuple):
                min_val, max_val = param_range
                if self.grid_points <= 1:
                    values = [min_val]
                elif min_val > 0 and max_val > 0:
                    log_min = math.log10(min_val)
                    step = (math.log10(max_val) - log_min) / (self.grid_points - 1)
                    values = [10 ** (log_min + step * idx) for idx in range(self.grid_points)]
                else:
                    step = (max_val - min_val) / (self.grid_points - 1)
                    values = [min_val + step * idx for idx in range(self.grid_points)]

                if isinstance(min_val, int) and isinstance(max_val, int):
                    values = [int(round(value)) for value in values]
                discretized[param_name] = sorted(dict.fromkeys(values))
            elif isinstance(param_range, list):
                discretized[param_name] = list(param_range)
            else:
                raise ValueError(f"Unsupported parameter range for {param_name}: {param_range}")
        return discretized

    def _action_space_size(self) -> int:
        size = 1
        for values in self.discretized_ranges.values():
            size *= max(1, len(values))
        return size

    def _action_to_parameters(self, action: int) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        remaining = action
        for param_name in reversed(self.param_names):
            values = self.discretized_ranges[param_name]
            if not values:
                continue
            idx = remaining % len(values)
            params[param_name] = values[idx]
            remaining //= len(values)
        return params

    def _parameters_to_action(self, parameters: Dict[str, Any]) -> int:
        action = 0
        multiplier = 1
        for param_name in reversed(self.param_names):
            values = self.discretized_ranges[param_name]
            if not values:
                continue
            value = parameters.get(param_name, self.fixed_parameters.get(param_name, values[0]))
            idx = self._closest_index(values, value)
            action += idx * multiplier
            multiplier *= len(values)
        return action

    @staticmethod
    def _closest_index(values: List[Any], value: Any) -> int:
        if isinstance(value, (int, float)):
            numeric = [
                (idx, candidate)
                for idx, candidate in enumerate(values)
                if isinstance(candidate, (int, float))
            ]
            if numeric:
                return min(numeric, key=lambda item: abs(item[1] - value))[0]
        try:
            return values.index(value)
        except ValueError:
            return 0

    def _q_value(self, state: int, action: int) -> float:
        return self.q_table.get((state, action), 0.0)

    def _select_action(self, state: int) -> int:
        if self.action_space_size <= 1:
            return 0
        if random.random() < self.epsilon:
            return random.randint(0, self.action_space_size - 1)
        return max(range(self.action_space_size), key=lambda action: self._q_value(state, action))

    def _update_q_table(self, state: int, action: int, reward: float, next_state: int) -> None:
        old_value = self._q_value(state, action)
        next_best = max(self._q_value(next_state, next_action) for next_action in range(self.action_space_size))
        new_value = old_value + self.learning_rate * (reward + self.gamma * next_best - old_value)
        self.q_table[(state, action)] = new_value

    def suggest_parameters(
        self,
        metrics: BenchmarkMetrics,
        current_params: Dict[str, Any],
        iteration: int,
        best_reward: float = 0.0,
        **kwargs,
    ) -> TunerResponse:
        reward = metrics.get_metric(self.optimization_metric) if metrics else 0.0
        learning_reward = -reward if self.optimization_goal == "minimize" else reward
        current_state = self._parameters_to_action(current_params)

        if self.current_state is not None and self.last_action is not None:
            self._update_q_table(self.current_state, self.last_action, learning_reward, current_state)

        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        next_action = self._select_action(current_state)
        self.current_state = current_state
        self.last_action = next_action

        return TunerResponse(
            parameters=self._action_to_parameters(next_action),
            confidence=1.0 - self.epsilon,
            justification=f"Q-learning suggestion (epsilon={self.epsilon:.3f})",
        )
