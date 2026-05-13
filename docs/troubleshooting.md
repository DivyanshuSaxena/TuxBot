# Troubleshooting

This page uses symptom -> cause -> diagnostic -> fix. Start here when doctor,
target setup, metrics, or LLM calls fail.

## Quick Table

| Symptom | Likely cause | Diagnostic command | Fix |
| --- | --- | --- | --- |
| `sysbench` not found | Package missing | `command -v sysbench` | `sudo apt-get install -y sysbench` |
| No perf metrics | `perf` unavailable or blocked | `perf stat true` | Install matching `linux-tools`; check kernel perf permissions. |
| RAPL power metrics missing | CPU/kernel lacks powercap or permission | `ls /sys/class/powercap` | Run without power metrics or use supported hardware/kernel. |
| Scheduler path missing | `debugfs` not mounted or kernel lacks files | `ls /sys/kernel/debug/sched` | `sudo mount -t debugfs none /sys/kernel/debug` |
| CPU frequency path missing | cpufreq driver unavailable | `ls /sys/devices/system/cpu/cpufreq` | Remove cpufreq params or load/use supported driver. |
| Governor rejected | Governor not available for policy | `cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors` | Use an available governor. |
| `GEMINI_API_KEY` missing under `sudo` | Environment not preserved | `sudo --preserve-env=GEMINI_API_KEY env \| grep GEMINI` | Add the key to `--preserve-env`. |
| `OPENROUTER_API_KEY` missing under `sudo` | Environment not preserved | `sudo --preserve-env=OPENROUTER_API_KEY env \| grep OPENROUTER` | Add the key to `--preserve-env`. |
| BenchBase jar missing | Submodule not built | `ls deps/benchbase/target/benchbase-postgres/benchbase.jar` | Build BenchBase with PostgreSQL profile. |
| PostgreSQL connection failure | DB/user/password/service mismatch | `PGPASSWORD=password psql -h localhost -U admin -d benchbase -c 'select 1;'` | Re-run `sudo scripts/setup_tpcc_postgres.sh`. |
| BenchBase timeout | DB load issue, slow host, too-short timeout | Inspect `benchbase_windows/window_<n>/` logs | Increase `benchbase_timeout_buffer_seconds`; verify DB health. |
| Sysbench ends early | Continuous duration too short or process failed | Inspect `sysbench_cpu_windows/continuous_sysbench.log` | Increase `sysbench_continuous_duration`; check sysbench stderr. |
| Missing metric in history | Parser did not emit it | `jq '.history[0].metrics' results/<run>/optimization_history_*.json` | Fix parser/config metric name before changing tuner. |
| Optional tuner import error | Extra dependency missing | Read traceback for `smac`, `mlos`, or `torch` | Install `.[bayesian]`, `.[mlos]`, `.[dqn]`, or `.[tuners]`. |

## Missing `sysbench`

```bash
sudo apt-get install -y sysbench
command -v sysbench
sysbench --version
```

If `taskset: failed to execute sysbench` appears, the package is missing inside
the environment used by `sudo`.

## `perf` Metrics Missing

```bash
perf stat true
sudo perf stat true
```

If these fail, install matching kernel tools:

```bash
sudo apt-get install -y linux-tools-common linux-tools-generic linux-tools-$(uname -r)
```

Some hosts restrict perf through kernel settings. SemaTune can still run when
some system metrics are unavailable, but proxy-metric prompts will have less
context.

## RAPL Missing

```bash
ls /sys/class/powercap
find /sys/class/powercap -maxdepth 2 -name energy_uj
```

RAPL availability depends on CPU, kernel, firmware, and permissions. Missing
RAPL should not block target parsing unless your config depends on power as the
primary metric.

## Scheduler Debugfs Missing

```bash
ls /sys/kernel/debug/sched
sudo mount -t debugfs none /sys/kernel/debug
ls /sys/kernel/debug/sched
```

If scheduler files still do not exist, the kernel may not expose those debugfs
knobs. Remove scheduler parameters from the config or use a compatible kernel.

## CPU Frequency Path Missing

```bash
ls /sys/devices/system/cpu/cpufreq
for f in /sys/devices/system/cpu/cpufreq/policy*/scaling_available_governors; do
  echo "$f: $(cat "$f")"
done
```

If cpufreq is unavailable, remove `scaling_governor`, `scaling_min_freq`,
`scaling_max_freq`, and `epp` from the config. For Intel P-state controls,
check:

```bash
ls /sys/devices/system/cpu/intel_pstate
```

## LLM API Key Errors

Set only the key for the provider you use:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
export OPENROUTER_API_KEY="<your OpenRouter API key>"
```

Preserve it under `sudo`:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_single.json
```

Do not add real keys to JSON configs.

## BenchBase Jar Missing

```bash
git submodule update --init deps/benchbase
cd deps/benchbase
./mvnw -P postgres -DskipTests package
tar -xzf target/benchbase-postgres.tgz -C target
cd ../..
```

Then verify:

```bash
ls deps/benchbase/target/benchbase-postgres/benchbase.jar
```

## PostgreSQL Connection Failures

The TPCC XML expects `admin`/`password` on database `benchbase` at
`localhost:5432`.

```bash
sudo scripts/setup_tpcc_postgres.sh
PGPASSWORD=password psql -h localhost -U admin -d benchbase -c 'select 1;'
sudo systemctl is-active postgresql
```

If your host uses a non-systemd PostgreSQL service, start PostgreSQL with the
host's service manager, then rerun the `psql` check.

## Sysbench Continuous Duration Too Short

`sysbench_cpu` runs one live interval-reporting process by default. Long LLM
latency can outlive the process if `sysbench_continuous_duration` is too short.

Check:

```bash
tail -n 40 results/<run>/sysbench_cpu_windows/continuous_sysbench.log
```

Fix:

```json
{
  "sysbench_interval_reporting": true,
  "sysbench_continuous_duration": 3600
}
```

## Missing Metrics

Inspect the optimization history:

```bash
jq '.history[0].metrics' results/<run>/optimization_history_*.json
```

If a metric is not there, fix the target parser or use a metric that exists. For
LLM prompt metrics, also inspect:

```bash
jq '{iteration, response_text}' results/<run>/llm_api_logs/llm_responses.jsonl
```

## Optional Tuner Import Errors

```bash
pip install -e ".[bayesian]"
pip install -e ".[mlos]"
pip install -e ".[dqn]"
pip install -e ".[tuners]"
```

Base `pytest`, docs build, fixed runs, Q-learning, and replay should not require
SMAC, MLOS Core, or PyTorch.

## Last-Resort Restore

If a host is left in an unknown state, use [Safety and Restore](safety-and-restore.md)
for manual commands. On a disposable benchmark host, rebooting is often the
cleanest reset.
