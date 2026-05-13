# Quick Start

This path gets from a fresh checkout to a successful SemaTune smoke run. It uses
`sysbench_cpu` because it is the smallest included target.

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs,llm]"
```

Success means `.venv/bin/os-param-tuning --help` prints the CLI help.

## 2. Check The Host

```bash
.venv/bin/os-param-tuning doctor
```

The doctor command reports missing host prerequisites. Install `sysbench` before
running the smoke config:

```bash
sudo apt-get update
sudo apt-get install -y sysbench
```

## 3. Run Fixed Sysbench Smoke

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_fixed.json
```

Success means:

- `results/sysbench_cpu_fixed/optimization_history_sysbench_cpu_*.json` exists
- `results/sysbench_cpu_fixed/sysbench_cpu_windows/continuous_sysbench.log`
  exists
- every tuning iteration has a non-null `throughput` metric

## 4. Inspect Results

```bash
jq '.history[] | {iteration, reward, parameters, throughput: .metrics.throughput}' \
  results/sysbench_cpu_fixed/optimization_history_sysbench_cpu_*.json
```

Read [Reading Results](reading-results.md) for more `jq` commands and examples.

## 5. Try One Tuner

For a no-API LLM plumbing check, use replay:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_replay.json
```

For a live LLM call, set your own provider key first:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_single.json
```

Read [Safety and Restore](safety-and-restore.md) before expanding parameter
ranges or moving to a less disposable host.
