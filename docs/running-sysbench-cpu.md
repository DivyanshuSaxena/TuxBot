# Running Sysbench CPU

`sysbench_cpu` is the smallest included target. Use it to verify host setup,
learn the SemaTune output layout, and test tuners before moving to a larger
application target.
Read [Safety and Restore](safety-and-restore.md) before widening parameter
ranges.

Smoke run:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_fixed.json
```

Single-loop LLM run:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_single.json
```

OpenRouter single-loop LLM run:

```bash
export OPENROUTER_API_KEY="<your OpenRouter API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,OPENROUTER_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_openrouter.json
```

Dual-loop LLM run:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_dual.json
```

Gemma 4 single-loop and dual-loop LLM smoke runs:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_single_gemma4.json

sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_dual_gemma4.json
```

The Gemma 4 examples run `max_iterations: 5` tuning windows followed by
`post_tuning_windows: 5` stable windows.

## Live Interval Reporting

`sysbench_cpu` uses interval reporting by default. SemaTune starts one long
`sysbench cpu --report-interval=1` process for the whole run and reads each
measured window from the live interval stream. It does not restart sysbench
between tuning iterations.

The default `tuning_mode` is `outside-of-window`: measure a window, ask the
tuner after that window, apply the new parameters, then measure the next window.
The sysbench workload keeps running while the tuner responds, so parameter
changes happen against a live process.

Output locations:

- `results/<run>/sysbench_cpu_windows/continuous_sysbench.log`: complete live
  sysbench stream
- `results/<run>/sysbench_cpu_windows/window_<n>/sysbench_intervals.json`:
  parsed interval records and the aggregate metrics used for scoring
- `results/<run>/sysbench_cpu_windows/window_<n>/sysbench_interval.log`: raw
  interval lines for that window

For long LLM runs, increase `sysbench_continuous_duration` in the config so the
single sysbench process outlives tuner latency and all post-tuning windows.

If the run reports that `sysbench` is missing, install it with:

```bash
sudo apt-get install -y sysbench
```

Bayesian or MLOS runs require optional tuner extras:

```bash
pip install -e ".[tuners]"
.venv/bin/os-param-tuning run --config config/examples/sysbench_cpu_bayesian.json
.venv/bin/os-param-tuning run --config config/examples/sysbench_cpu_mlos.json
```

Q-learning runs without extra dependencies; DQN needs PyTorch:

```bash
.venv/bin/os-param-tuning run --config config/examples/sysbench_cpu_qlearning.json
pip install -e ".[dqn]"
.venv/bin/os-param-tuning run --config config/examples/sysbench_cpu_dqn.json
```

Tune `pin_to_cores`, `sysbench_threads`, and `window_duration` to match your
host before collecting final results.

If the console script is unavailable, the module fallback is:

```bash
.venv/bin/python -m barebones_optimizer.main run --config config/examples/sysbench_cpu_fixed.json
```
