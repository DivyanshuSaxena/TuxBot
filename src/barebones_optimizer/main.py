#!/usr/bin/env python3
"""Command-line entry point for the open-source v1 optimizer."""

import argparse
import atexit
import logging
import os
import signal
import sys

from barebones_optimizer.benchmarks.benchbase import BenchBaseBenchmark
from barebones_optimizer.benchmarks.benchmark_registry import BenchmarkType
from barebones_optimizer.benchmarks.sysbench import SysbenchBenchmark
from barebones_optimizer.config import SimpleConfig
from barebones_optimizer.doctor import run_doctor
from barebones_optimizer.main_helpers import create_tuner_from_config, create_trimming_tuner_from_config
from barebones_optimizer.dual_loop_optimizer import SimpleDualLoopOptimizer
from barebones_optimizer.optimizer import SimpleOptimizer


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(asctime)s - %(filename)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("main")

SUPPORTED_TUNERS = ["fixed", "llm", "bayesian", "mlos", "qlearning", "dqn"]
SUPPORTED_LLM_LOOPS = ["single", "dual"]

_global_optimizer = None
_global_benchmark = None
_cleanup_in_progress = False


def cleanup_handler(signum=None, frame=None):
    """Best-effort cleanup on process exit or signal."""

    global _global_optimizer, _global_benchmark, _cleanup_in_progress
    if _cleanup_in_progress:
        if signum is not None:
            os._exit(1)
        return

    _cleanup_in_progress = True
    if _global_benchmark is not None:
        try:
            _global_benchmark.cleanup()
        except Exception as exc:
            logger.error("Benchmark cleanup failed: %s", exc, exc_info=True)

    if _global_optimizer is not None:
        try:
            _global_optimizer._finish("interrupted" if signum else "normal_exit")
        except Exception as exc:
            logger.error("Optimizer cleanup failed: %s", exc, exc_info=True)


def setup_signal_handlers():
    atexit.register(cleanup_handler)
    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)


def create_benchmark(config: SimpleConfig):
    benchmark_name = BenchmarkType.from_string(config.benchmark).value.name
    if benchmark_name == "sysbench_cpu":
        return SysbenchBenchmark(config)
    if benchmark_name == "tpcc":
        return BenchBaseBenchmark(config)
    raise ValueError(f"Unsupported benchmark: {config.benchmark}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OS parameter tuner for sysbench_cpu and TPCC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run an optimization config")
    run_parser.add_argument("-c", "--config", required=True, help="Path to JSON config")
    run_parser.add_argument("--tuner", choices=SUPPORTED_TUNERS, help="Override config tuner")
    run_parser.add_argument("--llm-loop", choices=SUPPORTED_LLM_LOOPS, help="Override LLM loop mode")

    subparsers.add_parser("doctor", help="Check host prerequisites")

    parser.add_argument(
        "-c",
        "--config",
        help="Compatibility shortcut for: os-param-tuning run --config <path>",
    )
    parser.add_argument(
        "--tuner",
        choices=SUPPORTED_TUNERS,
        help="Compatibility tuner override when using top-level --config",
    )
    parser.add_argument(
        "--llm-loop",
        choices=SUPPORTED_LLM_LOOPS,
        help="Compatibility LLM loop override when using top-level --config",
    )
    return parser


def run_config(
    config_path: str,
    tuner_override: str | None = None,
    llm_loop_override: str | None = None,
):
    global _global_optimizer, _global_benchmark

    setup_signal_handlers()
    config = SimpleConfig.load(config_path)
    if tuner_override:
        config.tuner_type = tuner_override
    if llm_loop_override:
        config.llm_loop = llm_loop_override
    if tuner_override or llm_loop_override:
        config.validate()

    benchmark = create_benchmark(config)
    if config.tuner_type == "llm" and config.llm_loop == "dual":
        optimizer = SimpleDualLoopOptimizer(config, benchmark)
    else:
        tuner = create_tuner_from_config(config)
        trimming_tuner = create_trimming_tuner_from_config(config)
        optimizer = SimpleOptimizer(config, benchmark, tuner, trimming_tuner=trimming_tuner)
    _global_benchmark = benchmark
    _global_optimizer = optimizer
    result = optimizer.run()
    _global_optimizer = None
    _global_benchmark = None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor()

    if args.command == "run":
        run_config(args.config, args.tuner, args.llm_loop)
        return 0

    if args.config:
        run_config(args.config, args.tuner, args.llm_loop)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
