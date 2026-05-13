#!/usr/bin/env python3
"""Optional SMAC-backed Bayesian optimization tuner."""

import logging
import os
import shutil
import tempfile
from typing import Any, Dict

from ..benchmark import BenchmarkMetrics
from .base import TunerInterface, TunerResponse

logger = logging.getLogger(__name__)


def _load_smac_dependencies():
    try:
        from ConfigSpace import (  # type: ignore
            CategoricalHyperparameter,
            Configuration,
            ConfigurationSpace,
            UniformFloatHyperparameter,
            UniformIntegerHyperparameter,
        )
        from smac import HyperparameterOptimizationFacade, Scenario  # type: ignore
        from smac.runhistory.dataclasses import TrialValue  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "The Bayesian tuner requires optional dependencies. "
            'Install them with: pip install -e ".[bayesian]"'
        ) from exc

    return {
        "CategoricalHyperparameter": CategoricalHyperparameter,
        "Configuration": Configuration,
        "ConfigurationSpace": ConfigurationSpace,
        "UniformFloatHyperparameter": UniformFloatHyperparameter,
        "UniformIntegerHyperparameter": UniformIntegerHyperparameter,
        "HyperparameterOptimizationFacade": HyperparameterOptimizationFacade,
        "Scenario": Scenario,
        "TrialValue": TrialValue,
    }


class BayesianOptimizerTuner(TunerInterface):
    """Bayesian optimization tuner using SMAC ask/tell."""

    def __init__(self, config):
        self._deps = _load_smac_dependencies()
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
        self.n_trials = int(getattr(config, "bayesian_n_trials", 50))
        self.seed = int(getattr(config, "bayesian_seed", 42))

        self.configspace = self._create_configuration_space()
        self.temp_dir = tempfile.mkdtemp(prefix="os_param_tuning_smac_")
        self.scenario = self._deps["Scenario"](
            configspace=self.configspace,
            deterministic=False,
            n_trials=self.n_trials,
            n_workers=1,
            seed=self.seed,
            output_directory=self.temp_dir,
        )
        self.smac = None
        self.current_config = None
        logger.info("Initialized Bayesian optimizer tuner with SMAC")

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

    def _configuration_to_parameters(self, configuration) -> Dict[str, Any]:
        if hasattr(configuration, "config"):
            configuration = configuration.config

        params: Dict[str, Any] = {}
        for param_name, param_range in self.parameter_ranges.items():
            if param_name not in configuration:
                continue
            value = configuration[param_name]
            if isinstance(param_range, tuple):
                min_val, max_val = param_range
                if isinstance(min_val, int) and isinstance(max_val, int):
                    params[param_name] = int(value)
                else:
                    params[param_name] = float(value)
            elif isinstance(param_range, list):
                value_text = str(value)
                params[param_name] = next(
                    (original for original in param_range if str(original) == value_text),
                    value,
                )

        return params

    def _parameters_to_configuration(self, parameters: Dict[str, Any]):
        optimized_only = {}
        for param_name, param_range in self.parameter_ranges.items():
            if param_name not in parameters:
                continue
            value = parameters[param_name]
            if isinstance(param_range, list):
                value = str(value)
            optimized_only[param_name] = value
        return self._deps["Configuration"](self.configspace, optimized_only)

    @staticmethod
    def _target_function(config, seed: int = 0):
        return 0.0

    def suggest_parameters(
        self,
        metrics: BenchmarkMetrics,
        current_params: Dict[str, Any],
        iteration: int,
        best_reward: float = 0.0,
        **kwargs,
    ) -> TunerResponse:
        if self.smac is None:
            self.smac = self._deps["HyperparameterOptimizationFacade"](
                scenario=self.scenario,
                target_function=self._target_function,
                overwrite=True,
            )
            self.current_config = self.smac.ask()
            return TunerResponse(
                parameters=self._configuration_to_parameters(self.current_config),
                confidence=1.0,
                justification="SMAC initial configuration",
            )

        reward = metrics.get_metric(self.optimization_metric) if metrics else 0.0
        smac_value = -reward if self.optimization_goal == "maximize" else reward

        if self.current_config is not None:
            trial_value = self._deps["TrialValue"](cost=smac_value, time=0.5)
            self.smac.tell(self.current_config, trial_value)

        try:
            self.current_config = self.smac.ask()
            return TunerResponse(
                parameters=self._configuration_to_parameters(self.current_config),
                confidence=1.0,
                justification="SMAC Bayesian optimization suggestion",
            )
        except Exception as exc:
            logger.error("SMAC failed to suggest parameters: %s", exc, exc_info=True)
            return TunerResponse(
                parameters={
                    key: value
                    for key, value in current_params.items()
                    if key in self.parameter_ranges
                },
                confidence=0.0,
                justification=f"SMAC error; keeping current parameters: {exc}",
            )

    def __del__(self):
        temp_dir = getattr(self, "temp_dir", None)
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
