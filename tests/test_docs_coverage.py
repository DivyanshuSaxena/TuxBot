from dataclasses import fields
from pathlib import Path

from barebones_optimizer.config import SimpleConfig
from barebones_optimizer.parameter_manager import PARAMETER_METADATA


def test_configuration_docs_cover_simple_config_fields():
    docs = Path("docs/configuration.md").read_text(encoding="utf-8")
    missing = [field.name for field in fields(SimpleConfig) if f"`{field.name}`" not in docs]
    assert missing == []


def test_os_parameter_docs_cover_parameter_metadata():
    docs = Path("docs/os-parameters.md").read_text(encoding="utf-8")
    missing = [name for name in PARAMETER_METADATA if f"`{name}`" not in docs]
    assert missing == []


def test_prompt_mode_docs_reference_examples():
    docs = Path("docs/llm-prompt-modes.md").read_text(encoding="utf-8")
    modes = {
        "default": "tpcc_llm_8param_default_gemini.json",
        "full_metrics": "tpcc_llm_8param_full_metrics.json",
        "full_metrics_signature": "tpcc_llm_8param_full_metrics_signature.json",
        "indirect_recent": "tpcc_llm_8param_indirect_recent.json",
        "indirect_all_plain": "tpcc_llm_8param_indirect_all_plain.json",
        "indirect_all_signature": "tpcc_llm_8param_indirect_all_signature.json",
    }
    for mode, filename in modes.items():
        assert f"`{mode}`" in docs
        assert filename in docs
        assert Path("config/examples", filename).exists()


def test_config_recipe_replay_files_exist():
    docs = Path("docs/config-recipes.md").read_text(encoding="utf-8")
    replay_config = Path("config/examples/sysbench_cpu_llm_replay.json")
    replay_history = Path("config/replay/sysbench_cpu_llm_replay_history.json")

    assert "sysbench_cpu_llm_replay.json" in docs
    assert "config/replay/sysbench_cpu_llm_replay_history.json" in docs
    assert replay_config.exists()
    assert replay_history.exists()
