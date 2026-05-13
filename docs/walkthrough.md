# Walkthrough: One SemaTune Run

This walkthrough uses `sysbench_cpu` because it is small, fast, and does not
need a database. The same control-loop structure applies to TPCC and to custom
targets you add later.

## 1. Install And Check The Host

Create a virtual environment and install SemaTune:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs,llm]"
```

Install the host package used by this walkthrough:

```bash
sudo apt-get update
sudo apt-get install -y sysbench
```

Run the doctor command:

```bash
.venv/bin/os-param-tuning doctor
```

The command reports missing host prerequisites. It does not make the machine
safe for final experiments by itself; use a quiet dedicated host when collecting
numbers you intend to compare.

Success means:

- Python dependencies import without errors.
- `sysbench --version` works.
- Doctor output names missing optional pieces without crashing.

If `sysbench` is missing, install it before continuing. If doctor reports
missing TPCC pieces, you can ignore those for this sysbench walkthrough.

## 2. Read The Config

Open `config/examples/sysbench_cpu_fixed.json`. The important pieces are:

- `benchmark: "sysbench_cpu"` selects the target adapter.
- `tuner_type: "fixed"` makes this a baseline run.
- `optimization_metric: "throughput"` and `optimization_goal: "maximize"` tell
  SemaTune how to score each window.
- `parameter_ranges` declares the OS knobs that a real tuner would be allowed
  to change.
- `fixed_parameters` declares values to apply before the run.
- `window_duration`, `max_iterations`, and `post_tuning_windows` control run
  length.

The target-specific sysbench fields live in the same JSON:

- `sysbench_threads`
- `sysbench_cpu_max_prime`
- `sysbench_interval_reporting`
- `sysbench_report_interval`
- `sysbench_continuous_duration`

Success means you can explain which metric is being optimized, which parameter
can change, and where outputs will be written. If those are unclear, stop and
read [Configuration Recipes](config-recipes.md).

## 3. Run A Baseline

Run the fixed config with `sudo`, preserving the project root:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_fixed.json
```

During the run, SemaTune starts one live sysbench process with
`--report-interval`, observes per-window output, and records each window. The
default tuning mode is `outside-of-window`: SemaTune measures a window, makes a
decision after it, applies accepted changes, and then measures the next window.

Expected duration is roughly `max_iterations * window_duration`, plus startup
and cleanup. Success means:

- `results/sysbench_cpu_fixed/optimization_history_sysbench_cpu_*.json` exists
- `results/sysbench_cpu_fixed/sysbench_cpu_windows/continuous_sysbench.log`
  exists
- every tuning iteration has a non-null `throughput` metric

If the command fails before window 1, check `sysbench` installation and sudo
environment preservation. If it fails after a window starts, inspect the
continuous sysbench log.

## 4. Inspect The Outputs

Look under the configured `results_dir`. A sysbench CPU run writes:

- `optimization_history_<benchmark>_<timestamp>.json`
- `sysbench_cpu_windows/continuous_sysbench.log`
- `sysbench_cpu_windows/window_<n>/sysbench_intervals.json`
- `sysbench_cpu_windows/window_<n>/sysbench_interval.log`

The optimization history is the easiest way to see the control loop. For each
iteration, inspect the current parameters, observed metrics, tuner response, and
score. The continuous sysbench log shows the raw live interval stream.

Use:

```bash
jq '.history[] | {iteration, reward, parameters, throughput: .metrics.throughput}' \
  results/sysbench_cpu_fixed/optimization_history_sysbench_cpu_*.json
```

Success means each entry has an `iteration`, `reward`, `parameters`, and
`throughput`. A missing metric usually means a parser/config metric-name
mismatch.

## 5. Try A Tuner

For a no-API LLM plumbing check, use replay:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_replay.json
```

Success means the run completes without `GEMINI_API_KEY` or
`OPENROUTER_API_KEY`.

For a live LLM-backed run, set your own provider key:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
```

Then run:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_single.json
```

After the run, inspect:

```text
<results_dir>/llm_api_logs/llm_responses.jsonl
```

That file has one compact record per LLM call. The adjacent `.txt` files contain
the full prompt, response, parsed parameter proposal, and raw SDK
representation. These logs are intentionally private run artifacts.

Expected LLM output:

- `llm_api_logs/llm_responses.jsonl` exists for live LLM calls
- each record includes `provider`, `model`, `agent`, and `response_text`
- optimization history includes `llm_justification` or `tuner_timing`

If the key is set in your shell but missing under `sudo`, use
`sudo --preserve-env=...` as shown in the examples.

## 6. Map The Walkthrough To A Custom Target

When adding your own target, keep the same shape:

- Prepare the target once.
- Measure or drive one window at a time.
- Return direct metrics, proxy metrics, or both.
- Let SemaTune own parameter application.
- Write target outputs under `results_dir`.
- Add a small example config and parser tests.

The detailed adapter contract is in [Extending SemaTune](extending.md).
Read [Safety and Restore](safety-and-restore.md) before using wider parameter
ranges or long-running experiments.
