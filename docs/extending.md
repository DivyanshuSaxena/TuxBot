# Extending SemaTune

SemaTune is meant to be extended. The included targets and tuners are examples
of the framework contracts: target adapters produce measurement windows, tuners
propose parameter settings, and the optimizer owns scoring, validation,
actuation, and output history.

This page describes what to implement when adding a new application target or
tuner.
For a smaller copy-paste walkthrough, start with
[Add a Target Tutorial](add-a-target-tutorial.md), then return here for the full
contract.

## Adding A Target

Add a target when you have a workload or service that can be prepared, measured
over a bounded window, and summarized into metrics. The target may be a command,
a benchmark harness, a database-backed service, or a long-running application
that SemaTune observes while an external load generator drives traffic.

The target contract is:

- prepare the target once before tuning starts
- run or observe one timed measurement window
- parse direct application metrics, proxy system metrics, or both
- write target-specific output under `results_dir`
- clean up child processes and temporary runtime state
- fail early with actionable messages when host prerequisites are missing

Implement a class that subclasses `BenchmarkInterface` from
`src/barebones_optimizer/benchmark.py`. The internal name still says
`BenchmarkInterface` for compatibility; conceptually, this is the target
adapter interface.

Required methods:

- `pre_execute(self) -> bool`: prepare the target before tuning starts.
- `execute_window(self, window_number: int, duration: int) -> BenchmarkMetrics`: run or observe one measured window.
- `parse_results(self, output_dir: str) -> BenchmarkMetrics`: parse target output into the common metric object.
- `cleanup(self) -> None`: stop processes and remove temporary runtime state.

Optional method:

- `update_workload(self, iteration: int) -> None`: change load shape between windows.

Minimal shape:

```python
from barebones_optimizer.benchmark import BenchmarkInterface, BenchmarkMetrics


class MyServiceTarget(BenchmarkInterface):
    def pre_execute(self) -> bool:
        self._check_prerequisites()
        self._start_service_if_needed()
        return True

    def execute_window(self, window_number: int, duration: int) -> BenchmarkMetrics:
        output_dir = self._window_output_dir(window_number)
        self._drive_or_observe_load(duration, output_dir)
        return self.parse_results(output_dir)

    def parse_results(self, output_dir: str) -> BenchmarkMetrics:
        summary = self._read_summary(output_dir)
        return BenchmarkMetrics(
            throughput=summary["throughput"],
            goodput=summary.get("goodput", summary["throughput"]),
            latency_avg=summary["latency_avg"],
            latency_p95=summary["latency_p95"],
            extra_metrics={
                "latency_p99": summary["latency_p99"],
                "error_rate": summary["error_rate"],
            },
        )

    def cleanup(self) -> None:
        self._stop_children()
```

Wire it in:

- Add target-specific config fields to `SimpleConfig` only when they are stable
  user-facing settings.
- Add a `BenchmarkType` entry in `benchmarks/benchmark_registry.py`.
- Add a branch in `create_benchmark()` in `main.py`.
- Add one small example config under `config/examples/`.
- Add a target page or section that documents setup, smoke run, metrics, and
  output files.

Target implementation rules:

- Do not require private paths, private hosts, credentials, or unpublished data.
- Respect `pin_to_cores` by using `_wrap_with_taskset()` for launched commands.
- Put all generated files under `self.results_dir`.
- Return common metrics plus target-specific values in `extra_metrics`.
- Keep destructive setup and real workload tests behind explicit opt-in markers.
- Make missing binaries, missing jars, connection failures, and parser failures
  explain what the user should install or check next.

Minimum tests:

- Config validation accepts the new target name.
- The target is listed only if it is intended to be part of the documented
  public surface.
- Parser tests cover normal output and at least one missing or partial metric
  case.
- Command-construction tests do not require `sudo`.
- A live smoke test is marked `benchmark_smoke`.
- Any test that mutates host state is also marked `host_mutation`.

## Adding Metrics

A target should return the direct metric the run optimizes when possible. If
the target can also expose useful proxy metrics, put them in `extra_metrics` so
they can appear in optimization history and LLM prompts.

Good metric additions have:

- a stable name, such as `latency_p99`, `ipc`, or `cache_misses`
- units documented in the target page
- parser tests with small fixture outputs
- clear behavior when the metric is unavailable

For LLM prompt modes, document whether the metric is a direct objective or a
proxy signal. Proxy metrics are evidence about system state; they are not
automatically a good scalar reward for non-LLM tuners.

## Adding OS Parameters

Add an OS parameter when SemaTune should be allowed to change another host
setting. The parameter manager needs enough metadata to validate proposals and
write values safely.

A public parameter should have:

- a stable config name
- type metadata: continuous or categorical
- scope metadata: global or per-core
- a conservative documented range or domain
- a getter when possible, so SemaTune can restore original values
- a setter that writes through a known Linux interface, not arbitrary shell
  commands
- unit tests for validation and value normalization
- documentation in [OS Parameter Reference](os-parameters.md)

Keep parameter ranges target-specific in configs. The global metadata describes
what the parameter is; each experiment decides what range is safe to explore.

## Adding A Tuner

A tuner receives recent metrics, the current configuration, and the configured
parameter surface. It returns a proposal for the next parameter values. The
optimizer handles scoring, validation, application, and output files.

Implement `TunerInterface` from `src/barebones_optimizer/tuners/base.py`.

Required method:

- `suggest_parameters(metrics, current_params, iteration, best_reward=0.0, **kwargs) -> TunerResponse`

Minimal shape:

```python
from barebones_optimizer.tuners.base import TunerInterface, TunerResponse


class MyTuner(TunerInterface):
    def __init__(self, config):
        self.config = config
        self.parameter_ranges = config.parameter_ranges

    def suggest_parameters(self, metrics, current_params, iteration, best_reward=0.0, **kwargs):
        return TunerResponse(
            parameters=current_params,
            confidence=1.0,
            justification="Keeping current parameters",
        )
```

Wire it in:

- Add the tuner name to `SimpleConfig.validate()`.
- Add a lazy import branch in `create_tuner_from_config()`.
- Add the tuner to CLI `SUPPORTED_TUNERS`.
- Add config fields only for stable user-facing knobs.
- Add example configs for `sysbench_cpu` and TPCC when the tuner is meant to be
  documented.
- Document install requirements, expected use cases, and failure modes.

Tuner implementation rules:

- Return only tunable parameter names, not fixed parameters.
- Do not mutate host state directly.
- Do not import heavy optional dependencies at package import time.
- Raise a clear `ImportError` with an install hint when an optional dependency
  is missing.
- Bound action/search spaces from config so accidental huge runs fail early.
- Use `optimization_goal` to convert minimize objectives into a learning reward
  when the algorithm expects rewards to increase.

Minimum tests:

- Config validation accepts the tuner name and rejects bad tuner-specific
  settings.
- The tuner can suggest a bounded parameter set using fake `BenchmarkMetrics`.
- Optional dependencies are imported lazily and fail with an install hint.
- Base `pytest` still runs without installing optional tuner dependencies.

## Current Tuners

- `fixed`: no dependencies; best for baselines and host validation.
- `llm`: Gemini/OpenRouter SDKs via `.[llm]`; supports `llm_loop: single|dual`.
- `bayesian`: SMAC via `.[bayesian]`.
- `mlos`: MLOS Core via `.[mlos]`.
- `qlearning`: no extra dependency; best for small discretized spaces.
- `dqn`: PyTorch via `.[dqn]`.
