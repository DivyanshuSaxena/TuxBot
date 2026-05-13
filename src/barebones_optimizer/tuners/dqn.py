#!/usr/bin/env python3
"""Optional PyTorch DQN tuner over a discretized parameter space."""

from collections import deque, namedtuple
import logging
import math
import random
from typing import Any, Dict, List

from ..benchmark import BenchmarkMetrics
from .base import TunerInterface, TunerResponse

logger = logging.getLogger(__name__)


def _load_torch_dependencies():
    try:
        import torch  # type: ignore
        import torch.nn as nn  # type: ignore
        import torch.nn.functional as functional  # type: ignore
        import torch.optim as optim  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "The DQN tuner requires PyTorch. Install it with: pip install -e \".[dqn]\""
        ) from exc
    return torch, nn, functional, optim


class DQNTuner(TunerInterface):
    """Deep Q-network tuner for small discrete or discretized search spaces."""

    def __init__(self, config):
        self.torch, self.nn, self.functional, self.optim = _load_torch_dependencies()
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

        self.grid_points = int(getattr(config, "dqn_grid_points", 10))
        self.max_actions = int(getattr(config, "dqn_max_actions", 1000))
        self.learning_rate = float(getattr(config, "dqn_learning_rate", 0.001))
        self.epsilon = float(getattr(config, "dqn_epsilon_start", 1.0))
        self.epsilon_end = float(getattr(config, "dqn_epsilon_end", 0.1))
        self.epsilon_decay = float(getattr(config, "dqn_epsilon_decay", 0.995))
        self.batch_size = int(getattr(config, "dqn_batch_size", 32))
        self.memory_size = int(getattr(config, "dqn_memory_size", 1000))
        self.target_update_freq = int(getattr(config, "dqn_target_update_freq", 10))
        self.hidden_size = int(getattr(config, "dqn_hidden_size", 128))
        self.gamma = float(getattr(config, "dqn_gamma", 0.99))
        self.seed = getattr(config, "dqn_seed", None)
        if self.seed is not None:
            random.seed(int(self.seed))
            self.torch.manual_seed(int(self.seed))

        self.param_names = list(self.parameter_ranges)
        self.discretized_ranges = self._create_discretized_ranges()
        self.action_space_size = self._action_space_size()
        if self.action_space_size > self.max_actions:
            raise ValueError(
                f"DQN action space is too large ({self.action_space_size} > {self.max_actions}). "
                "Tune fewer parameters, lower dqn_grid_points, or raise dqn_max_actions."
            )

        self.state_size = len(self.param_names) + 3
        self.device = self.torch.device("cuda" if self.torch.cuda.is_available() else "cpu")
        network_cls = self._network_class()
        self.q_network = network_cls(self.state_size, self.action_space_size, self.hidden_size).to(self.device)
        self.target_network = network_cls(self.state_size, self.action_space_size, self.hidden_size).to(self.device)
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.optimizer = self.optim.Adam(self.q_network.parameters(), lr=self.learning_rate)

        self.Experience = namedtuple("Experience", ["state", "action", "reward", "next_state", "done"])
        self.memory = deque(maxlen=self.memory_size)
        self.current_state = None
        self.last_action = None
        self.steps_since_target_update = 0
        logger.info("Initialized DQN tuner with %d actions on %s", self.action_space_size, self.device)

    def _network_class(self):
        nn = self.nn
        functional = self.functional

        class DQNNetwork(nn.Module):
            def __init__(self, state_size: int, action_size: int, hidden_size: int):
                super().__init__()
                self.fc1 = nn.Linear(state_size, hidden_size)
                self.fc2 = nn.Linear(hidden_size, hidden_size)
                self.fc3 = nn.Linear(hidden_size, action_size)

            def forward(self, state):
                x = functional.relu(self.fc1(state))
                x = functional.relu(self.fc2(x))
                return self.fc3(x)

        return DQNNetwork

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

    def _create_state(self, parameters: Dict[str, Any], reward: float, iteration: int) -> List[float]:
        state = []
        for param_name in self.param_names:
            values = self.discretized_ranges[param_name]
            value = parameters.get(param_name, self.fixed_parameters.get(param_name, values[0]))
            if isinstance(self.parameter_ranges[param_name], tuple):
                min_val, max_val = self.parameter_ranges[param_name]
                state.append((float(value) - float(min_val)) / (float(max_val) - float(min_val)))
            else:
                idx = self._closest_index(values, value)
                state.append(idx / max(1, len(values) - 1))

        normalized_reward = -reward if self.optimization_goal == "minimize" else reward
        state.append(max(-1.0, min(1.0, normalized_reward / 10000.0)))
        state.append(min(1.0, iteration / max(1, self.config.max_iterations)))
        state.append(1.0 - self.epsilon)
        return state

    def _select_action(self, state: List[float]) -> int:
        if self.action_space_size <= 1:
            return 0
        if random.random() < self.epsilon:
            return random.randint(0, self.action_space_size - 1)
        with self.torch.no_grad():
            state_tensor = self.torch.tensor([state], dtype=self.torch.float32, device=self.device)
            return int(self.q_network(state_tensor).argmax().item())

    def _remember(self, state, action, reward, next_state) -> None:
        self.memory.append(self.Experience(state, action, reward, next_state, False))

    def _replay(self) -> None:
        if len(self.memory) < self.batch_size:
            return
        batch = random.sample(self.memory, self.batch_size)
        states = self.torch.tensor([item.state for item in batch], dtype=self.torch.float32, device=self.device)
        actions = self.torch.tensor([item.action for item in batch], dtype=self.torch.long, device=self.device)
        rewards = self.torch.tensor([item.reward for item in batch], dtype=self.torch.float32, device=self.device)
        next_states = self.torch.tensor([item.next_state for item in batch], dtype=self.torch.float32, device=self.device)

        current_q = self.q_network(states).gather(1, actions.unsqueeze(1)).squeeze()
        next_q = self.target_network(next_states).max(1)[0].detach()
        target_q = rewards + self.gamma * next_q
        loss = self.functional.mse_loss(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

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
        state = self._create_state(current_params, reward, iteration)

        if self.current_state is not None and self.last_action is not None:
            self._remember(self.current_state, self.last_action, learning_reward, state)
            self._replay()
            self.steps_since_target_update += 1
            if self.steps_since_target_update >= self.target_update_freq:
                self.target_network.load_state_dict(self.q_network.state_dict())
                self.steps_since_target_update = 0

        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        action = self._select_action(state)
        self.current_state = state
        self.last_action = action

        return TunerResponse(
            parameters=self._action_to_parameters(action),
            confidence=1.0 - self.epsilon,
            justification=f"DQN suggestion (epsilon={self.epsilon:.3f})",
        )
