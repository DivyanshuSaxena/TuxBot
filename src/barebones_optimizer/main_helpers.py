#!/usr/bin/env python3
"""Helpers for constructing supported tuner implementations."""

from dataclasses import replace

from barebones_optimizer.config import SimpleConfig


def create_tuner_from_config(config: SimpleConfig):
    if config.tuner_type == "fixed":
        from barebones_optimizer.tuners import FixedTuner

        return FixedTuner(config)
    if config.tuner_type == "llm":
        from barebones_optimizer.tuners import LLMTuner

        if config.llm_loop == "dual":
            raise ValueError("Dual-loop LLM runs are created by SimpleDualLoopOptimizer")
        return LLMTuner(config, agent_type="single")
    if config.tuner_type == "bayesian":
        from barebones_optimizer.tuners.bayesian import BayesianOptimizerTuner

        return BayesianOptimizerTuner(config)
    if config.tuner_type == "mlos":
        from barebones_optimizer.tuners.mlos_tuner import MLOSTuner

        return MLOSTuner(config)
    if config.tuner_type == "qlearning":
        from barebones_optimizer.tuners.qlearning import QLearningTuner

        return QLearningTuner(config)
    if config.tuner_type == "dqn":
        from barebones_optimizer.tuners.dqn import DQNTuner

        return DQNTuner(config)
    raise ValueError(f"Unsupported tuner type for v1: {config.tuner_type}")


def create_trimming_tuner_from_config(config: SimpleConfig):
    """Create the optional LLM trimming tuner for single-loop LLM runs."""

    if not config.trimming_enabled:
        return None
    if config.tuner_type != "llm" or config.llm_loop != "single":
        raise ValueError("LLM trimming is supported only for single-loop llm configs")

    from barebones_optimizer.tuners import LLMTrimmingTuner

    trimming_config = config
    if config.trimming_model_name:
        trimming_config = replace(config, llm_model_name=config.trimming_model_name)
    return LLMTrimmingTuner(trimming_config, agent_type="single")
