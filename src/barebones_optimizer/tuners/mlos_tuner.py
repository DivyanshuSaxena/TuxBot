#!/usr/bin/env python3
"""Optional MLOS-backed optimizer tuner."""

import logging
from typing import Any, Dict

from ..benchmark import BenchmarkMetrics
from .base import TunerInterface, TunerResponse

logger = logging.getLogger(__name__)


def _load_mlos_dependencies():
    try:
        import pandas as pd  # type: ignore
        from ConfigSpace import (  # type: ignore
            CategoricalHyperparameter,
            ConfigurationSpace,
            UniformFloatHyperparameter,
            UniformIntegerHyperparameter,
        )
        from mlos_core.data_classes import Observation, Observations  # type: ignore
        from mlos_core.optimizers.bayesian_optimizers.smac_optimizer import SmacOptimizer  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "The MLOS tuner requires optional dependencies. "
            'Install them with: pip install -e ".[mlos]"'
        ) from exc

    return {
        "CategoricalHyperparameter": CategoricalHyperparameter,
        "ConfigurationSpace": ConfigurationSpace,
        "Observation": Observation,
        "Observations": Observations,
        "pd": pd,
        "SmacOptimizer": SmacOptimizer,
        "UniformFloatHyperparameter": UniformFloatHyperparameter,
        "UniformIntegerHyperparameter": UniformIntegerHyperparameter,
    }


class MLOSTuner(TunerInterface):
    """MLOS optimizer tuner using MLOS Core's SMAC wrapper."""

    def __init__(self, config):
        self._deps = _load_mlos_dependencies()
        self.pd = self._deps["pd"]
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

        self.max_trials = int(getattr(config, "mlos_max_trials", 100))
        self.n_random_init = int(getattr(config, "mlos_n_random_init", 3))
        self.max_ratio = getattr(config, "mlos_max_ratio", None)
        self.use_default_config = bool(getattr(config, "mlos_use_default_config", False))
        self.n_random_probability = float(getattr(config, "mlos_n_random_probability", 0.1))
        self.seed = int(getattr(config, "mlos_seed", 42))
        self.run_name = getattr(config, "mlos_run_name", None)
        self.output_directory = getattr(config, "mlos_output_directory", None)
        self.objective_weights = getattr(config, "mlos_objective_weights", None)

        self.configspace = self._create_configuration_space()
        self.mlos_optimizer = None
        self.iteration_count = 0
        logger.info("Initialized MLOS tuner")

    def _create_configuration_space(self):
        cs = self._deps["ConfigurationSpace"](seed=self.seed)
        parameter_types = getattr(self.config, "parameter_types", None) or {}

        for param_name, param_range in self.parameter_ranges.items():
            explicit_type = parameter_types.get(param_name)
            if isinstance(param_range, tuple):
                min_val, max_val = param_range
                if explicit_type == "float" or any(isinstance(v, float) for v in param_range):
                    hyperparameter = self._deps["UniformFloatHyperparameter"](
                        name=param_name,
                        lower=float(min_val),
                        upper=float(max_val),
                        log=False,
                    )
                else:
                    hyperparameter = self._deps["UniformIntegerHyperparameter"](
                        name=param_name,
                        lower=int(min_val),
                        upper=int(max_val),
                        log=False,
                    )
                cs.add_hyperparameter(hyperparameter)
            elif isinstance(param_range, list):
                hyperparameter = self._deps["CategoricalHyperparameter"](
                    name=param_name,
                    choices=[str(value) for value in param_range],
                )
                cs.add_hyperparameter(hyperparameter)
            else:
                logger.warning("Skipping unsupported parameter range for %s", param_name)

        return cs

    def _initialize_optimizer(self) -> None:
        if self.mlos_optimizer is not None:
            return

        self.mlos_optimizer = self._deps["SmacOptimizer"](
            parameter_space=self.configspace,
            optimization_targets=[self.optimization_metric],
            objective_weights=self.objective_weights,
            space_adapter=None,
            seed=self.seed,
            run_name=self.run_name,
            output_directory=self.output_directory,
            max_trials=self.max_trials,
            n_random_init=max(1, self.n_random_init),
            max_ratio=self.max_ratio if self.max_ratio is not None else 0.1,
            use_default_config=self.use_default_config,
            n_random_probability=self.n_random_probability,
        )

    def _dict_to_series(self, params: Dict[str, Any]):
        values = {}
        for param_name, param_range in self.parameter_ranges.items():
            if param_name not in params:
                continue
            value = params[param_name]
            if isinstance(value, dict) and "value" in value:
                value = value["value"]
            if isinstance(param_range, list):
                values[param_name] = str(value)
            elif isinstance(param_range, tuple):
                min_val, max_val = param_range
                values[param_name] = int(value) if isinstance(min_val, int) and isinstance(max_val, int) else float(value)
        return self.pd.Series(values, dtype=object)

    def _series_to_dict(self, series) -> Dict[str, Any]:
        params = {}
        for param_name, param_range in self.parameter_ranges.items():
            if param_name not in series.index:
                continue
            value = series[param_name]
            if isinstance(param_range, list):
                value_text = str(value)
                params[param_name] = next(
                    (original for original in param_range if str(original) == value_text),
                    value,
                )
            elif isinstance(param_range, tuple):
                min_val, max_val = param_range
                params[param_name] = int(value) if isinstance(min_val, int) and isinstance(max_val, int) else float(value)
        return params

    def _suggest_random(self) -> TunerResponse:
        configuration = self.configspace.sample_configuration()
        params = {}
        for param_name, param_range in self.parameter_ranges.items():
            if param_name not in configuration:
                continue
            value = configuration[param_name]
            if isinstance(param_range, list):
                value_text = str(value)
                params[param_name] = next(
                    (original for original in param_range if str(original) == value_text),
                    value,
                )
            elif isinstance(param_range, tuple):
                min_val, max_val = param_range
                params[param_name] = int(value) if isinstance(min_val, int) and isinstance(max_val, int) else float(value)

        self.iteration_count += 1
        return TunerResponse(
            parameters=params,
            confidence=0.5,
            justification=f"MLOS random initialization ({self.iteration_count}/{self.n_random_init})",
        )

    def suggest_parameters(
        self,
        metrics: BenchmarkMetrics,
        current_params: Dict[str, Any],
        iteration: int,
        best_reward: float = 0.0,
        **kwargs,
    ) -> TunerResponse:
        try:
            if self.iteration_count < max(1, self.n_random_init):
                return self._suggest_random()

            self._initialize_optimizer()
            reward = metrics.get_metric(self.optimization_metric) if metrics else 0.0

            if current_params:
                score = -reward if self.optimization_goal == "maximize" else reward
                observation = self._deps["Observation"](
                    config=self._dict_to_series(current_params),
                    score=self.pd.Series({self.optimization_metric: score}),
                    context=None,
                    metadata=None,
                )
                self.mlos_optimizer.register(self._deps["Observations"](observations=[observation]))

            suggestion = self.mlos_optimizer.suggest()
            self.iteration_count += 1
            return TunerResponse(
                parameters=self._series_to_dict(suggestion.config),
                confidence=1.0,
                justification=f"MLOS SMAC suggestion (iteration {self.iteration_count})",
            )
        except StopIteration:
            self.iteration_count += 1
            return TunerResponse(
                parameters={
                    key: value
                    for key, value in current_params.items()
                    if key in self.parameter_ranges
                },
                confidence=1.0,
                justification="MLOS exhausted the search space; keeping current parameters",
            )
        except Exception as exc:
            logger.error("MLOS failed to suggest parameters: %s", exc, exc_info=True)
            return TunerResponse(
                parameters={
                    key: value
                    for key, value in current_params.items()
                    if key in self.parameter_ranges
                },
                confidence=0.0,
                justification=f"MLOS error; keeping current parameters: {exc}",
            )

    def __del__(self):
        optimizer = getattr(self, "mlos_optimizer", None)
        if optimizer is not None and hasattr(optimizer, "cleanup"):
            try:
                optimizer.cleanup()
            except Exception as exc:
                logger.warning("Error cleaning up MLOS optimizer: %s", exc)
