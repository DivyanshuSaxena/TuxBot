import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import barebones_optimizer.tuners.llm as llm_module
from barebones_optimizer.config import SimpleConfig
from barebones_optimizer.tuners.llm import LLMTuner
from barebones_optimizer.tuners.llm_trimming import LLMTrimmingTuner


def _replay_file(tmp_path):
    path = tmp_path / "replay.json"
    path.write_text(json.dumps({"history": []}), encoding="utf-8")
    return str(path)


def _llm_config(tmp_path, **overrides):
    data = {
        "tuner_type": "llm",
        "llm_replay_file": _replay_file(tmp_path),
        "parameter_ranges": {
            "min_granularity_ns": (100000, 100000000),
            "cstate_max": ["POLL", "C6", "C1"],
        },
        "parameters_to_tune": ["min_granularity_ns", "cstate_max"],
        "optimization_metric": "latency_p99",
        "optimization_goal": "minimize",
    }
    data.update(overrides)
    config = SimpleConfig(**data)
    config.validate()
    return config


@pytest.mark.parametrize(
    ("mode", "expected_text"),
    [
        ("default", "OPTIMIZATION STRATEGY"),
        ("full_metrics", "supporting evidence"),
        ("full_metrics_signature", "Metric Signature"),
        ("indirect_recent", "Metric Signature"),
        ("indirect_all_plain", "primary optimization metric is NOISY or HIDDEN"),
        ("indirect_all_signature", "Metric Signature"),
    ],
)
def test_supported_llm_prompt_modes_render_without_api_calls(tmp_path, mode, expected_text):
    metrics = ["instructions_per_cycle", "cycles"]
    config = _llm_config(
        tmp_path,
        llm_prompt_mode=mode,
        llm_additional_metrics=metrics if mode != "default" else None,
    )

    tuner = LLMTuner(config)
    prompt = tuner._create_base_prompt()

    assert expected_text in prompt
    assert "min_granularity_ns" in prompt
    assert "Minimum scheduling granularity" in prompt


def test_prompt_customization_is_additive_and_preserves_default_prompt(tmp_path):
    extra_file = tmp_path / "extra_prompt.txt"
    extra_file.write_text("Prefer stable changes over aggressive jumps.", encoding="utf-8")
    config = _llm_config(
        tmp_path,
        workload_description="TPC-C high-percentile latency tuning",
        llm_prompt_extra_instructions="Do not change all parameters at once.",
        llm_prompt_extra_instructions_file=str(extra_file),
    )

    prompt = LLMTuner(config)._create_base_prompt()

    assert "Linux kernel scheduler tuning expert" in prompt
    assert "TPC-C high-percentile latency tuning" in prompt
    assert "Do not change all parameters at once." in prompt
    assert "Prefer stable changes over aggressive jumps." in prompt


def test_llm_api_log_writes_exact_log_and_response_index(tmp_path):
    config = _llm_config(tmp_path, results_dir=str(tmp_path / "results"))
    tuner = LLMTuner(config)

    tuner._write_llm_api_log(
        iteration=2,
        request_contents=["base prompt", "window update"],
        request_config={"temperature": 0.2},
        response_text='Analysis: try a nearby value\nConfig: {"min_granularity_ns": 2000000}',
        response_parsed={"min_granularity_ns": 2000000},
        response_raw={"id": "fake-response"},
        request_timestamp=1_700_000_000.123,
        aggregation_interval_s=10.0,
    )

    log_dir = Path(config.results_dir) / "llm_api_logs"
    log_files = list(log_dir.glob("llm_api_iter0002_single_*.txt"))
    assert len(log_files) == 1
    assert "fake-response" in log_files[0].read_text(encoding="utf-8")

    index_lines = (log_dir / "llm_responses.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(index_lines) == 1
    index = json.loads(index_lines[0])
    assert index["iteration"] == 2
    assert index["agent"] == "single"
    assert index["response_parsed"]["min_granularity_ns"] == 2000000
    assert index["log_file"] == str(log_files[0])


def test_llm_gist_generation_is_logged(tmp_path):
    config = _llm_config(tmp_path, results_dir=str(tmp_path / "results"))
    tuner = LLMTuner(config)

    class FakeResponse:
        text = "Use higher min_granularity_ns next time."
        usage_metadata = SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=6,
            total_token_count=16,
        )

    class FakeModels:
        def generate_content(self, **kwargs):
            return FakeResponse()

    tuner.client = SimpleNamespace(models=FakeModels())
    summary, _ = tuner.generate_gist(
        [
            {
                "iteration": 1,
                "reward": 1.0,
                "parameters": {"min_granularity_ns": 1000000},
                "metrics": {"throughput": 1.0},
            }
        ]
    )

    assert summary == "Use higher min_granularity_ns next time."
    index_lines = (Path(config.results_dir) / "llm_api_logs" / "llm_responses.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    index = json.loads(index_lines[-1])
    assert index["request_config"]["purpose"] == "optimization_gist"
    assert index["response_text"] == "Use higher min_granularity_ns next time."


def test_gemini_provider_uses_gemini_env_key(monkeypatch):
    captured = {}

    class FakeGenAI:
        class Client:
            def __init__(self, api_key):
                captured["api_key"] = api_key

    monkeypatch.setattr(llm_module, "GOOGLE_GENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "genai", FakeGenAI)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    config = SimpleConfig(tuner_type="llm", llm_provider="gemini", llm_model_name="gemini-2.5-flash")
    config.validate()
    tuner = LLMTuner(config)

    assert tuner._use_gemini is True
    assert captured["api_key"] == "gemini-test-key"


def test_openrouter_provider_uses_openrouter_env_key(monkeypatch):
    captured = {}

    class FakeOpenAI:
        class OpenAI:
            def __init__(self, api_key, base_url):
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = SimpleNamespace(completions=SimpleNamespace())

    monkeypatch.setattr(llm_module, "OPENAI_SDK_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "openai_sdk", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-test-key")

    config = SimpleConfig(tuner_type="llm", llm_provider="openrouter", llm_model_name="openai/gpt-4o-mini")
    config.validate()
    tuner = LLMTuner(config)

    assert tuner._use_gemini is False
    assert captured["api_key"] == "openrouter-test-key"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"


def test_gemma_models_route_to_gemini_in_auto_mode_with_replay(tmp_path):
    config = _llm_config(
        tmp_path,
        llm_provider="auto",
        llm_model_name="gemma-4-31b-it",
        llm_thinking_level="HIGH",
    )
    tuner = LLMTuner(config)

    assert tuner._use_gemini is True
    assert tuner.model_name == "gemma-4-31b-it"
    assert tuner.thinking_level == "HIGH"
    assert tuner.thinking_budget is None


def test_dual_loop_gemma_uses_per_agent_thinking_with_replay(tmp_path):
    config = _llm_config(
        tmp_path,
        llm_loop="dual",
        llm_actor_model="gemma-4-31b-it",
        llm_actor_thinking_level="HIGH",
        llm_speculator_model="gemma-4-26b-a4b-it",
        llm_speculator_thinking_level="MINIMAL",
    )

    speculator = LLMTuner(config, agent_type="quick")
    actor = LLMTuner(config, agent_type="reasoning")

    assert speculator._use_gemini is True
    assert speculator.model_name == "gemma-4-26b-a4b-it"
    assert speculator.thinking_level == "MINIMAL"
    assert actor._use_gemini is True
    assert actor.model_name == "gemma-4-31b-it"
    assert actor.thinking_level == "HIGH"


def test_missing_llm_keys_raise_actionable_errors(monkeypatch):
    monkeypatch.setattr(llm_module, "GOOGLE_GENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "genai", SimpleNamespace(Client=lambda api_key: object()))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    gemini_config = SimpleConfig(tuner_type="llm", llm_provider="gemini", llm_model_name="gemini-2.5-flash")
    gemini_config.validate()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        LLMTuner(gemini_config)

    monkeypatch.setattr(llm_module, "OPENAI_SDK_AVAILABLE", True)
    monkeypatch.setattr(llm_module, "openai_sdk", SimpleNamespace(OpenAI=lambda **kwargs: object()))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    openrouter_config = SimpleConfig(tuner_type="llm", llm_provider="openrouter", llm_model_name="openai/gpt-4o-mini")
    openrouter_config.validate()
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        LLMTuner(openrouter_config)


def test_llm_trimming_updates_ranges_and_eliminates_parameters(tmp_path):
    config = _llm_config(
        tmp_path,
        trimming_enabled=True,
        trimming_cycles=2,
    )
    tuner = LLMTrimmingTuner(config)

    params, justification, warnings = tuner._parse_structured_response(
        {
            "min_granularity_ns": 2000000,
            "suggested_ranges": {
                "min_granularity_ns": {"min": 1000000, "max": 5000000},
                "cstate_max": {"values": ["C6", "C1"]},
            },
            "eliminated_params": ["cstate_max"],
            "justification": "The initial runs favor a narrower region.",
            "converged": False,
        }
    )

    assert warnings == []
    assert params["min_granularity_ns"] == 2000000
    assert justification == "The initial runs favor a narrower region."
    assert tuner.get_effective_ranges() == {"min_granularity_ns": (1000000, 5000000)}
    assert tuner.get_eliminated_params() == {"cstate_max": "C6"}
