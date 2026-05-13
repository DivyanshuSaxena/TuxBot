# Reproducibility Model

SemaTune targets reproducible tuning sessions on a documented host, not
bit-identical performance numbers across machines.

Each published experiment should keep:

- the exact JSON config used for the run
- the command line used to launch it
- the host setup notes needed to recreate the machine state
- `sysbench`, Java, PostgreSQL, and `perf` versions from `.venv/bin/os-param-tuning doctor`
- per-window metrics, target output, LLM logs, and final optimization history

The optimizer intentionally does not write `run_metadata.json` and does not
capture git diff or dirty status. That keeps result directories focused on
target and tuner outputs, and avoids accidentally publishing private local state.

## Recommended Practice

Use a quiet dedicated host. Disable unrelated services, record BIOS and kernel
settings in your lab notes, and run each experiment multiple times.

## Host Snapshot Commands

```bash
uname -a
lscpu
sysbench --version
python --version
.venv/bin/os-param-tuning doctor
```

For TPCC runs, also record:

```bash
psql --version
java -version
git -C deps/benchbase rev-parse HEAD
```

## Lab Notes Template

```text
Host:
Kernel:
CPU:
BIOS / turbo / hyperthreading:
Governor:
Command:
Config file:
Git commit:
Python version:
sysbench version:
PostgreSQL version:
BenchBase commit:
LLM provider/model:
Run notes:
```

Keep lab notes outside `results_dir` if they contain private host details. The
result directory should stay focused on target output, optimizer history, and
LLM logs.
