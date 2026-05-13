# SemaTune

SemaTune is a system-wide OS tuning framework for improving the performance of
application targets. It runs a host-side control loop: observe a target over a
measurement window, collect direct application metrics or proxy system metrics,
ask a tuner for the next OS parameter setting, validate the proposal, apply the
change, and record what happened.

The current command-line entry point is still `os-param-tuning`; the Python
package and imports are unchanged. The project name used in docs and releases is
SemaTune.

## Included Examples

The repository includes two maintained targets that double as worked examples:

- `sysbench_cpu`: a small CPU-bound target for installation checks and quick
  tuning walkthroughs.
- BenchBase `tpcc` on PostgreSQL: a database-backed target with application
  latency metrics.

These examples are intentionally small enough to understand end to end. The
extension docs explain how to add another target, metric parser, OS parameter,
or tuner.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs,llm]"

.venv/bin/os-param-tuning doctor
.venv/bin/os-param-tuning --help
```

Install every public tuner, including Bayesian, MLOS, and DQN:

```bash
pip install -e ".[dev,docs,llm,tuners]"
```

LLM runs require your own API key:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
# or
export OPENROUTER_API_KEY="<your OpenRouter API key>"
```

Do not put real keys in config files or commits.

Run a short sysbench CPU fixed-parameter smoke test on a prepared host:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_fixed.json
```

Build the documentation:

```bash
mkdocs build --strict
```

## Reproducibility

SemaTune changes live Linux kernel and system parameters. Use a dedicated host,
review configs before running them, and preserve `OS_PARAM_TUNING_ROOT` when
running with `sudo`. Read [Safety and Restore](docs/safety-and-restore.md)
before widening parameter ranges or running long sessions.

The project aims to make setup, configs, commands, and output layout
reproducible on a documented host. Benchmark numbers still depend on hardware,
kernel version, firmware settings, background load, and provider behavior for
LLM-backed tuners.

## Citation

If SemaTune helps your research, please cite:

```bibtex
TODO: Add citation / BibTeX before public release.
```
