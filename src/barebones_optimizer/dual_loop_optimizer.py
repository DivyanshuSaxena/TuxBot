#!/usr/bin/env python3
"""Dual-loop LLM optimizer for the public v1 benchmark surface."""

import concurrent.futures
import logging
import threading
import time
from typing import Any, Dict, Optional

from .benchmark import BenchmarkMetrics
from .optimizer import SimpleOptimizer, _is_fatal_llm_http_error
from .parameter_manager import get_default_parameters
from .tuners import LLMTuner

logger = logging.getLogger(__name__)


class SimpleDualLoopOptimizer(SimpleOptimizer):
    """Actor/speculator optimizer for `llm_loop="dual"` configs."""

    def __init__(self, config, benchmark, quick_tuner=None, reasoning_tuner=None):
        reasoning = reasoning_tuner or LLMTuner(config, agent_type="reasoning")
        super().__init__(config=config, benchmark=benchmark, tuner=reasoning)
        self.reasoning_tuner = reasoning
        self.quick_tuner = quick_tuner or LLMTuner(config, agent_type="quick")
        self.quick_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.reasoning_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.baseline_index = 0

    def run(self) -> Dict[str, Any]:
        try:
            logger.info("=" * 60)
            logger.info("Starting dual-loop LLM OS parameter optimization")
            logger.info("Benchmark: %s", self.config.benchmark)
            logger.info("Speculator model: %s", self.quick_tuner.model_name)
            logger.info("Actor model: %s", self.reasoning_tuner.model_name)
            logger.info("Optimizing for: %s %s", self.config.optimization_goal, self.config.optimization_metric)
            logger.info("Tuning mode: %s", self.config.tuning_mode)
            logger.info("=" * 60)

            if hasattr(self.benchmark, "pre_execute") and not self.benchmark.pre_execute():
                raise RuntimeError("Benchmark pre-execute failed")

            default_params = get_default_parameters()
            experiment_param_names = set(self.config.parameter_ranges) | set(self.config.fixed_parameters)
            initial_params = {
                name: value
                for name, value in default_params.items()
                if name in experiment_param_names
            }
            initial_params.update(self.config.fixed_parameters)
            self._snapshot_original_parameters(initial_params.keys())
            if not self.param_manager.set_parameters(initial_params):
                raise RuntimeError("Failed to apply initial parameters")
            self.current_parameters = initial_params.copy()

            return self._run_dual_loop()
        except KeyboardInterrupt:
            logger.info("Dual-loop optimization interrupted by user")
            return self._finish("interrupted")
        except Exception as exc:
            logger.error("Error during dual-loop optimization: %s", exc, exc_info=True)
            return self._finish("error")

    def _run_dual_loop(self) -> Dict[str, Any]:
        total_iterations = self._total_iterations()
        latest_metrics: Optional[BenchmarkMetrics] = None

        for iteration in range(1, total_iterations + 1):
            self.iteration = iteration
            tuning_active = iteration <= self.config.max_iterations
            logger.info("=== ITERATION %s/%s ===", iteration, total_iterations)

            tuner_timing = None
            if self.config.tuning_mode == "in-window" and tuning_active and latest_metrics is not None:
                futures = self._dispatch_agents(latest_metrics, iteration - 1)
                metrics, tuner_timing = self._execute_window_monitoring(iteration, futures, iteration - 1)
            else:
                metrics = self._execute_window_simple(iteration)

            if metrics is None:
                logger.warning("No metrics object from iteration %s", iteration)
                continue

            reward, constraint_violated = self._reward_from_metrics(metrics)
            self._update_best(reward)
            history_entry = self._history_entry(
                iteration=iteration,
                metrics=metrics,
                reward=reward,
                constraint_violated=constraint_violated,
                post_tuning_phase=not tuning_active,
                tuner_timing=tuner_timing,
            )
            self.history.append(history_entry)
            latest_metrics = metrics

            if (
                self.config.tuning_mode == "outside-of-window"
                and tuning_active
                and iteration < self.config.max_iterations
            ):
                tuner_timing = self._dispatch_and_wait(metrics, iteration)
                if tuner_timing:
                    history_entry["tuner_timing"] = tuner_timing

        return self._finish("complete")

    def _execute_window_simple(self, iteration: int) -> Optional[BenchmarkMetrics]:
        try:
            if self.benchmark and hasattr(self.benchmark, "update_workload"):
                self.benchmark.update_workload(iteration)
            return self.benchmark.execute_window(
                window_number=iteration,
                duration=self.config.window_duration,
            )
        except Exception as exc:
            logger.error("Benchmark error in window %s: %s", iteration, exc, exc_info=True)
            return None

    def _execute_window_monitoring(self, iteration: int, futures: Dict[str, Dict[str, Any]], call_iteration: int):
        metrics_result = [None]
        error_result = [None]

        def run_window():
            try:
                metrics_result[0] = self._execute_window_simple(iteration)
            except Exception as exc:
                error_result[0] = exc

        window_thread = threading.Thread(target=run_window, daemon=True)
        window_thread.start()
        timings: Dict[str, Any] = {}

        while window_thread.is_alive():
            self._collect_completed_futures(futures, call_iteration, timings, timeout=0)
            time.sleep(0.1)

        window_thread.join(timeout=self.config.window_duration + 10)
        if error_result[0]:
            raise error_result[0]

        self._collect_completed_futures(futures, call_iteration, timings, timeout=0)
        for item in futures.values():
            item["future"].cancel()
        return metrics_result[0], timings or None

    def _dispatch_and_wait(self, metrics: BenchmarkMetrics, iteration: int) -> Dict[str, Any]:
        futures = self._dispatch_agents(metrics, iteration)
        timings: Dict[str, Any] = {}
        self._collect_completed_futures(futures, iteration, timings, timeout=300)
        for item in futures.values():
            item["future"].cancel()
        return timings

    def _dispatch_agents(self, metrics: BenchmarkMetrics, iteration: int) -> Dict[str, Dict[str, Any]]:
        history_snapshot = [entry.copy() for entry in self.history]
        tunable_params = self._get_tunable_parameters(self.current_parameters)
        aggregation_interval_s = float(self.config.window_duration)

        logger.info("Dispatching Speculator and Actor for iteration %s", iteration + 1)
        return {
            "quick": {
                "future": self.quick_executor.submit(
                    self.quick_tuner.suggest_parameters,
                    metrics=metrics,
                    current_params=tunable_params,
                    iteration=iteration,
                    best_reward=self.best_reward,
                    history=history_snapshot,
                    baseline_index=self.baseline_index,
                    aggregation_interval_s=aggregation_interval_s,
                ),
                "started_at": time.time(),
                "tuner_type": "speculator_quick",
                "label": "Speculator",
            },
            "reasoning": {
                "future": self.reasoning_executor.submit(
                    self.reasoning_tuner.suggest_parameters,
                    metrics=metrics,
                    current_params=tunable_params,
                    iteration=iteration,
                    best_reward=self.best_reward,
                    history=history_snapshot,
                    baseline_index=self.baseline_index,
                    aggregation_interval_s=aggregation_interval_s,
                ),
                "started_at": time.time(),
                "tuner_type": "actor_reasoning",
                "label": "Actor",
            },
        }

    def _collect_completed_futures(
        self,
        futures: Dict[str, Dict[str, Any]],
        call_iteration: int,
        timings: Dict[str, Any],
        timeout: float,
    ) -> None:
        for name, item in list(futures.items()):
            future = item["future"]
            if timeout == 0 and not future.done():
                continue
            try:
                response = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning("%s did not respond before timeout", item["label"])
                continue
            except Exception as exc:
                if _is_fatal_llm_http_error(exc):
                    raise
                logger.error("%s failed: %s", item["label"], exc, exc_info=True)
                futures.pop(name, None)
                continue

            duration = time.time() - item["started_at"]
            timing = self._apply_tuner_parameters(response, call_iteration, duration_s=duration)
            if timing is None:
                timing = {"parameters_applied": False}
            timing.update(
                {
                    "tuner_type": item["tuner_type"],
                    "agent": name,
                    "proposed_parameters": dict(response.parameters) if response and response.parameters else None,
                }
            )
            timings[name] = timing
            if name == "reasoning":
                self.baseline_index = len(self.history)
            futures.pop(name, None)

    def _reward_from_metrics(self, metrics: BenchmarkMetrics) -> tuple[float, bool]:
        reward = metrics.get_metric(self.config.optimization_metric)
        if reward is None or (isinstance(reward, float) and reward != reward):
            reward = 0.0

        constraint_violated = False
        if self.config.constraint_metric and self.config.constraint_threshold is not None:
            constraint_value = metrics.get_metric(self.config.constraint_metric)
            if self.config.constraint_direction == "less_than":
                constraint_violated = constraint_value >= self.config.constraint_threshold
            else:
                constraint_violated = constraint_value <= self.config.constraint_threshold

        logger.info(
            "Iteration %s reward: %.4f (%s)",
            self.iteration,
            reward,
            self.config.optimization_metric,
        )
        return float(reward), constraint_violated

    def _update_best(self, reward: float) -> None:
        is_better = (
            self.config.optimization_goal == "maximize" and reward > self.best_reward
        ) or (
            self.config.optimization_goal == "minimize" and reward < self.best_reward
        )
        if is_better:
            self.best_reward = reward
            self.best_parameters = self.current_parameters.copy()

    def _history_entry(
        self,
        iteration: int,
        metrics: BenchmarkMetrics,
        reward: float,
        constraint_violated: bool,
        post_tuning_phase: bool,
        tuner_timing: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        extra_metrics = dict(metrics.extra_metrics)
        system_metrics = extra_metrics.pop("system_metrics", None)
        entry = {
            "iteration": iteration,
            "timestamp": time.time(),
            "parameters": self.current_parameters.copy(),
            "metrics": {
                "throughput": metrics.throughput,
                "goodput": metrics.goodput,
                "latency_avg": metrics.latency_avg,
                "latency_p95": metrics.latency_p95,
                **extra_metrics,
            },
            "reward": reward,
            "constraint_violated": constraint_violated,
            "post_tuning_phase": post_tuning_phase,
            "llm_loop": "dual",
        }
        if system_metrics:
            entry["system_metrics"] = system_metrics
        if tuner_timing:
            entry["tuner_timing"] = tuner_timing
        return entry

    def _finish(self, reason: str) -> Dict[str, Any]:
        for executor in (self.quick_executor, self.reasoning_executor, self.executor):
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception as exc:
                logger.warning("Error shutting down dual-loop executor: %s", exc)
        result = super()._finish(reason)
        result["llm_loop"] = "dual"
        return result
