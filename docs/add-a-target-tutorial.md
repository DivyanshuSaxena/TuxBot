# Add a Target Tutorial

This tutorial adds a tiny command target. It is intentionally simple so you can
copy the structure before adapting it to a real service.

The existing config field is named `benchmark` for compatibility. In SemaTune
docs, a benchmark implementation is a target adapter.

## Goal

Create `my_command_target`, a target that runs one command per measurement
window and parses a throughput value from stdout.

Example command output:

```text
throughput=1234.5
latency_p99_ms=2.7
```

## Minimal Adapter

Create a module under `src/barebones_optimizer/benchmarks/`:

```python
import os
import re
import subprocess
from pathlib import Path

from barebones_optimizer.benchmark import BenchmarkInterface, BenchmarkMetrics


class MyCommandTarget(BenchmarkInterface):
    def pre_execute(self) -> bool:
        if not getattr(self.config, "my_command", None):
            raise RuntimeError("my_command is required")
        return True

    def execute_window(self, window_number: int, duration: int) -> BenchmarkMetrics:
        window_dir = Path(self.results_dir) / "my_command_windows" / f"window_{window_number}"
        window_dir.mkdir(parents=True, exist_ok=True)
        log_file = window_dir / "target.log"

        command = list(self.config.my_command) + ["--time", str(duration)]
        result = subprocess.run(
            self._wrap_with_taskset(command),
            text=True,
            capture_output=True,
            timeout=duration + 30,
        )
        log_file.write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"my_command_target failed; see {log_file}")
        return self.parse_results(str(window_dir))

    def parse_results(self, output_dir: str) -> BenchmarkMetrics:
        text = Path(output_dir, "target.log").read_text(encoding="utf-8")
        throughput = float(re.search(r"throughput=([0-9.]+)", text).group(1))
        latency_p99 = float(re.search(r"latency_p99_ms=([0-9.]+)", text).group(1))
        return BenchmarkMetrics(
            throughput=throughput,
            goodput=throughput,
            latency_avg=0.0,
            latency_p95=0.0,
            extra_metrics={"latency_p99": latency_p99},
        )

    def cleanup(self) -> None:
        pass
```

For a real target, replace the parser with fixture-tested parsing and make
preflight errors actionable.

## Minimal Config

Add stable config fields to `SimpleConfig` only when they are part of the public
interface. For this toy target you might add:

```python
my_command: Optional[List[str]] = None
```

Then use:

```json
{
  "benchmark": "my_command_target",
  "my_command": ["./scripts/my-load-generator"],
  "tuner_type": "fixed",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize",
  "max_iterations": 3,
  "window_duration": 10,
  "results_dir": "results/my_command_target"
}
```

## Registry Wiring

Wire the target in three places:

- add a `BenchmarkType` entry in `benchmarks/benchmark_registry.py`
- add a branch in `create_benchmark()` in `main.py`
- add one example config under `config/examples/` if the target is documented

The public name in configs should be stable and lowercase, for example
`my_command_target`.

## Parser Test

Use tiny fixture text. Do not require sudo or launch the real command in parser
tests.

```python
def test_my_command_parser_reads_metrics(tmp_path):
    output_dir = tmp_path / "window"
    output_dir.mkdir()
    (output_dir / "target.log").write_text(
        "throughput=1234.5\nlatency_p99_ms=2.7\n",
        encoding="utf-8",
    )
    config = SimpleConfig(benchmark="my_command_target", results_dir=str(tmp_path))
    target = MyCommandTarget(config)

    metrics = target.parse_results(str(output_dir))

    assert metrics.throughput == 1234.5
    assert metrics.extra_metrics["latency_p99"] == 2.7
```

## Smoke Command

After parser/unit tests pass, run a short smoke test:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/my_command_target_fixed.json
```

Expected outputs:

- `results/my_command_target/optimization_history_*.json`
- `results/my_command_target/my_command_windows/window_1/target.log`
- one history entry per measured window

## Before Making It Public

Document:

- setup prerequisites
- supported metrics and units
- target-specific config fields
- expected output files
- known unsafe host assumptions

Then update [Extending SemaTune](extending.md), [Configuration Reference](configuration.md),
and the docs coverage tests if you add public fields.
