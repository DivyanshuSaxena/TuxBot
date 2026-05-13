import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from barebones_optimizer.benchmarks.benchmark_registry import BenchmarkType
from barebones_optimizer.benchmark import BenchmarkMetrics
from barebones_optimizer.config import SimpleConfig
from barebones_optimizer.main_helpers import create_tuner_from_config, create_trimming_tuner_from_config


def test_public_registry_only_lists_v1_benchmarks():
    assert BenchmarkType.list_all() == ["sysbench_cpu", "tpcc"]
    with pytest.raises(ValueError):
        BenchmarkType.from_string("unsupported_workload")


def test_example_configs_preserve_run_controls():
    expected = {
        "config/examples/sysbench_cpu_fixed.json": ("sysbench_cpu", "fixed", 10, 3, "outside-of-window"),
        "config/examples/sysbench_cpu_llm_single.json": ("sysbench_cpu", "llm", 10, 3, "outside-of-window"),
        "config/examples/sysbench_cpu_llm_dual.json": ("sysbench_cpu", "llm", 10, 3, "outside-of-window"),
        "config/examples/sysbench_cpu_bayesian.json": ("sysbench_cpu", "bayesian", 10, 3, "outside-of-window"),
        "config/examples/sysbench_cpu_mlos.json": ("sysbench_cpu", "mlos", 10, 3, "outside-of-window"),
        "config/examples/sysbench_cpu_qlearning.json": ("sysbench_cpu", "qlearning", 10, 3, "outside-of-window"),
        "config/examples/sysbench_cpu_dqn.json": ("sysbench_cpu", "dqn", 10, 3, "outside-of-window"),
        "config/examples/tpcc_fixed.json": ("tpcc", "fixed", 30, 3, "outside-of-window"),
        "config/examples/tpcc_llm_single.json": ("tpcc", "llm", 30, 3, "outside-of-window"),
        "config/examples/tpcc_llm_dual.json": ("tpcc", "llm", 30, 3, "outside-of-window"),
        "config/examples/tpcc_bayesian.json": ("tpcc", "bayesian", 30, 3, "outside-of-window"),
        "config/examples/tpcc_mlos.json": ("tpcc", "mlos", 30, 3, "outside-of-window"),
        "config/examples/tpcc_qlearning.json": ("tpcc", "qlearning", 30, 3, "outside-of-window"),
        "config/examples/tpcc_dqn.json": ("tpcc", "dqn", 30, 3, "outside-of-window"),
    }

    old_gemini = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "dummy-for-validation"
    try:
        for path, values in expected.items():
            config = SimpleConfig.load(path)
            assert (
                config.benchmark,
                config.tuner_type,
                config.window_duration,
                config.max_iterations,
                config.tuning_mode,
            ) == values
    finally:
        if old_gemini is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = old_gemini


def test_all_public_example_configs_load_and_do_not_embed_api_keys():
    key_fields = {"llm_api_key", "openrouter_api_key"}
    for path in sorted(Path("config/examples").glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert not (key_fields & set(raw)), f"{path} embeds an API key field"
        config = SimpleConfig.load(str(path))
        assert config.validate()


def test_public_prompt_modes_validate_and_map_to_internal_flags():
    metrics = ["instructions_per_cycle", "cycles"]
    cases = {
        "full_metrics": (False, True, False, True),
        "full_metrics_signature": (False, True, True, True),
        "indirect_recent": (True, False, False, False),
        "indirect_all_plain": (True, False, False, True),
        "indirect_all_signature": (True, False, False, True),
    }
    for mode, expected in cases.items():
        config = SimpleConfig(
            tuner_type="llm",
            llm_prompt_mode=mode,
            llm_additional_metrics=metrics,
        )
        config.validate()
        assert (
            config.use_indirect_optimization,
            config.llm_full_metrics_prompt_mode,
            config.llm_full_metrics_explicit_signature_compare,
            config.llm_indirect_history_show_all_metrics,
        ) == expected


def test_invalid_prompt_mode_and_missing_prompt_metrics_fail_clearly():
    with pytest.raises(ValueError, match="llm_prompt_mode"):
        SimpleConfig(tuner_type="llm", llm_prompt_mode="mystery").validate()

    with pytest.raises(ValueError, match="requires llm_additional_metrics"):
        SimpleConfig(tuner_type="llm", llm_prompt_mode="full_metrics").validate()


def test_trimming_requires_single_loop_llm_and_positive_cycles():
    with pytest.raises(ValueError, match="requires tuner_type='llm'"):
        SimpleConfig(tuner_type="fixed", trimming_enabled=True, trimming_cycles=2).validate()

    with pytest.raises(ValueError, match="single"):
        SimpleConfig(
            tuner_type="llm",
            llm_loop="dual",
            llm_actor_model="gemini-2.5-flash",
            llm_speculator_model="gemini-2.5-flash-lite",
            trimming_enabled=True,
            trimming_cycles=2,
        ).validate()

    with pytest.raises(ValueError, match="trimming_cycles"):
        SimpleConfig(tuner_type="llm", trimming_enabled=True, trimming_cycles=0).validate()


def test_unknown_config_fields_fail_clearly(tmp_path):
    config_path = tmp_path / "bad.json"
    config_path.write_text(json.dumps({"benchmark": "sysbench_cpu", "surprise": True}))

    with pytest.raises(ValueError, match="Unknown config fields"):
        SimpleConfig.load(str(config_path))


def test_dual_loop_requires_llm_actor_and_speculator_models():
    config = SimpleConfig(tuner_type="llm", llm_loop="dual")
    with pytest.raises(ValueError, match="llm_actor_model"):
        config.validate()

    config.llm_actor_model = "gemini-2.5-flash"
    with pytest.raises(ValueError, match="llm_speculator_model"):
        config.validate()

    config.llm_speculator_model = "gemini-2.5-flash-lite"
    assert config.validate()


def test_dual_loop_only_valid_for_llm_tuner():
    config = SimpleConfig(
        tuner_type="bayesian",
        llm_loop="dual",
        llm_actor_model="gemini-2.5-flash",
        llm_speculator_model="gemini-2.5-flash-lite",
    )
    with pytest.raises(ValueError, match="requires tuner_type='llm'"):
        config.validate()


@pytest.mark.parametrize(
    ("tuner_type", "extra"),
    [
        ("bayesian", ".[bayesian]"),
        ("mlos", ".[mlos]"),
        ("dqn", ".[dqn]"),
    ],
)
def test_optional_tuners_fail_clearly_without_optional_deps(tuner_type, extra):
    config = SimpleConfig(tuner_type=tuner_type)
    try:
        tuner = create_tuner_from_config(config)
    except ImportError as exc:
        assert extra in str(exc)
    else:
        assert hasattr(tuner, "suggest_parameters")


def test_qlearning_tuner_suggests_bounded_parameters():
    config = SimpleConfig(
        tuner_type="qlearning",
        parameter_ranges={"min_granularity_ns": (100000, 50000000)},
        parameters_to_tune=["min_granularity_ns"],
        qlearning_grid_points=4,
        qlearning_seed=1,
    )
    tuner = create_tuner_from_config(config)
    response = tuner.suggest_parameters(
        metrics=BenchmarkMetrics(throughput=10.0),
        current_params={"min_granularity_ns": 1000000},
        iteration=1,
    )
    assert set(response.parameters) == {"min_granularity_ns"}
    assert 100000 <= response.parameters["min_granularity_ns"] <= 50000000


def test_trimming_tuner_factory_uses_replay_without_api_key(tmp_path):
    replay = tmp_path / "replay.json"
    replay.write_text('{"history": []}', encoding="utf-8")
    config = SimpleConfig(
        tuner_type="llm",
        llm_replay_file=str(replay),
        trimming_enabled=True,
        trimming_cycles=2,
    )
    config.validate()

    tuner = create_trimming_tuner_from_config(config)
    assert tuner is not None
    assert tuner.agent_type == "trimming"


def test_main_help_runs_without_optional_benchmark_deps():
    result = subprocess.run(
        [sys.executable, "-m", "barebones_optimizer.main", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "sysbench_cpu" in result.stdout or "OS parameter tuner" in result.stdout
    assert "bayesian" in result.stdout
    assert "mlos" in result.stdout
    assert "qlearning" in result.stdout
    assert "dqn" in result.stdout
