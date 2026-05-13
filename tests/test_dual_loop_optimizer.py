from barebones_optimizer import dual_loop_optimizer
from barebones_optimizer.benchmark import BenchmarkMetrics
from barebones_optimizer.config import SimpleConfig
from barebones_optimizer.tuners import TunerResponse


class FakeParameterManager:
    def __init__(self):
        self.values = {}

    def set_parameters(self, params):
        self.values.update(params)
        return True

    def get_parameter(self, name):
        return self.values.get(name, 0)


class FakeBenchmark:
    def __init__(self):
        self.cleaned_up = False

    def pre_execute(self):
        return True

    def update_workload(self, iteration):
        return None

    def execute_window(self, window_number, duration):
        return BenchmarkMetrics(throughput=100.0 + window_number, latency_avg=1.0, latency_p95=2.0)

    def cleanup(self):
        self.cleaned_up = True


def test_dual_loop_routes_to_actor_and_speculator_without_real_llm(monkeypatch, tmp_path):
    created_agent_types = []

    class FakeLLMTuner:
        def __init__(self, config, agent_type):
            self.agent_type = agent_type
            self.model_name = f"fake-{agent_type}"
            created_agent_types.append(agent_type)

        def suggest_parameters(self, **kwargs):
            value = 2000000 if self.agent_type == "quick" else 3000000
            return TunerResponse(
                parameters={"min_granularity_ns": value},
                confidence=1.0,
                justification=self.agent_type,
            )

    monkeypatch.setattr(dual_loop_optimizer, "LLMTuner", FakeLLMTuner)
    monkeypatch.setattr(
        dual_loop_optimizer,
        "get_default_parameters",
        lambda: {"min_granularity_ns": 1000000},
    )

    config = SimpleConfig(
        benchmark="sysbench_cpu",
        tuner_type="llm",
        llm_loop="dual",
        llm_actor_model="gemini-2.5-flash",
        llm_speculator_model="gemini-2.5-flash-lite",
        parameter_ranges={"min_granularity_ns": (100000, 50000000)},
        parameters_to_tune=["min_granularity_ns"],
        optimization_metric="throughput",
        optimization_goal="maximize",
        max_iterations=2,
        post_tuning_windows=0,
        window_duration=1,
        tuning_mode="outside-of-window",
        results_dir=str(tmp_path),
    )

    optimizer = dual_loop_optimizer.SimpleDualLoopOptimizer(config, FakeBenchmark())
    optimizer.param_manager = FakeParameterManager()

    result = optimizer.run()

    assert result["llm_loop"] == "dual"
    assert set(created_agent_types) == {"quick", "reasoning"}
    assert len(optimizer.history) == 2
    assert optimizer.history[0]["tuner_timing"]["quick"]["tuner_type"] == "speculator_quick"
    assert optimizer.history[0]["tuner_timing"]["reasoning"]["tuner_type"] == "actor_reasoning"
    assert optimizer.history[1]["parameters"]["min_granularity_ns"] == 3000000
