# Safety and Restore

SemaTune changes live Linux system parameters. Treat every run as host-mutating
work, even when the target itself is a small benchmark.

Use a dedicated, isolated, or disposable host. Do not tune a shared production
machine unless you already have isolation, monitoring, and an out-of-band
restore path.

## What SemaTune Can Mutate

Depending on the config, SemaTune can write:

- CFS scheduler files under `/sys/kernel/debug/sched/`
- CPU-frequency and energy policy files under `/sys/devices/system/cpu/cpufreq/`
- Intel P-state files under `/sys/devices/system/cpu/intel_pstate/`
- CPU idle-state disable files under `/sys/devices/system/cpu/cpu*/cpuidle/`
- networking and VM sysctls through `sysctl -w`
- PM QoS files when available
- NIC interrupt affinity for some busy-polling paths

Only parameters named in `parameter_ranges` or `fixed_parameters` should be
touched by a normal run.

## Validation Boundary

Before applying a tuner proposal, SemaTune filters parameter names against the
active tunable set and validates values against configured ranges or categorical
domains. Fixed parameters are applied at startup and are not supposed to be
changed by the tuner.

Validation does not guarantee that a setting is safe for your host or workload.
A value can be syntactically valid and still cause poor latency, low throughput,
excessive power use, driver errors, or slow recovery. The validator is not a
kernel sandbox, a policy verifier, or a replacement for conservative ranges.

The documented examples use narrow parameter sets and short windows so that
installation and plumbing failures appear quickly.

## Original Values and Restore

Current restore is best-effort:

- Scheduler debugfs values such as `latency_ns`, `min_granularity_ns`,
  `wakeup_granularity_ns`, and `migration_cost_ns` can be snapshotted through
  the current getter path and restored on normal exit.
- Many sysfs, cpufreq, intel_pstate, idle-state, and sysctl values are applied
  through setters but are not guaranteed to have a per-run original-value
  snapshot in the current implementation.
- Some sysctl defaults can be discovered by helper code, but normal optimizer
  exit should still be treated as best-effort rather than a crash-proof rollback.

For serious experiments, record the values you care about before the run. A
reboot is often the cleanest restore path on a disposable benchmark host.

## Exit and Failure Cases

| Case | Expected behavior |
| --- | --- |
| Normal completion | Save optimization history, clean up target processes, then attempt best-effort parameter restore. |
| Ctrl-C or SIGTERM | Registered cleanup attempts to stop the target and finish optimizer cleanup. A second interrupt can stop cleanup early. |
| API failure | The optimizer saves history and attempts cleanup. Parameters already applied before the failure may require manual inspection. |
| Benchmark failure | The optimizer records the error path when possible, stops target processes, and attempts cleanup. |
| Process crash, host crash, `kill -9`, or power loss | No cleanup is guaranteed. Manually inspect/reset or reboot. |

## Why `sudo --preserve-env` Is Used

SemaTune needs root privileges for kernel and sysctl writes, but it also needs
the project virtualenv, repository root, and optional LLM credentials. The docs
use:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY,OPENROUTER_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_fixed.json
```

Use only the provider key you need. If an LLM key is missing under `sudo`, check:

```bash
sudo --preserve-env=GEMINI_API_KEY env | grep GEMINI
sudo --preserve-env=OPENROUTER_API_KEY env | grep OPENROUTER
```

## Manual Inspection

Scheduler:

```bash
sudo mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
sudo cat /sys/kernel/debug/sched/latency_ns
sudo cat /sys/kernel/debug/sched/min_granularity_ns
sudo cat /sys/kernel/debug/sched/wakeup_granularity_ns
sudo cat /sys/kernel/debug/sched/migration_cost_ns
```

CPU frequency and Intel P-state:

```bash
for f in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do echo "$f=$(cat "$f")"; done
for f in /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq; do echo "$f=$(cat "$f")"; done
for f in /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq; do echo "$f=$(cat "$f")"; done
cat /sys/devices/system/cpu/intel_pstate/min_perf_pct 2>/dev/null || true
cat /sys/devices/system/cpu/intel_pstate/max_perf_pct 2>/dev/null || true
cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || true
```

Networking and VM sysctls:

```bash
sysctl net.core.busy_poll net.core.busy_read net.core.netdev_budget
sysctl vm.swappiness vm.dirty_ratio vm.dirty_background_ratio
sysctl net.core.rmem_default net.core.rmem_max net.core.wmem_default net.core.wmem_max
```

Idle states:

```bash
find /sys/devices/system/cpu/cpu*/cpuidle -name disable -maxdepth 3 -print -exec cat {} \;
```

## Manual Reset Examples

These are conservative examples, not universal defaults for every host.

Scheduler:

```bash
sudo sh -c 'echo 24000000 > /sys/kernel/debug/sched/latency_ns'
sudo sh -c 'echo 3000000 > /sys/kernel/debug/sched/min_granularity_ns'
sudo sh -c 'echo 4000000 > /sys/kernel/debug/sched/wakeup_granularity_ns'
sudo sh -c 'echo 500000 > /sys/kernel/debug/sched/migration_cost_ns'
```

Intel P-state:

```bash
sudo sh -c 'echo 0 > /sys/devices/system/cpu/intel_pstate/min_perf_pct' 2>/dev/null || true
sudo sh -c 'echo 100 > /sys/devices/system/cpu/intel_pstate/max_perf_pct' 2>/dev/null || true
sudo sh -c 'echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo' 2>/dev/null || true
```

CPU idle states:

```bash
for f in /sys/devices/system/cpu/cpu*/cpuidle/state*/disable; do
  sudo sh -c "echo 0 > '$f'"
done
```

Common sysctls:

```bash
sudo sysctl -w net.core.busy_poll=0
sudo sysctl -w net.core.busy_read=0
sudo sysctl -w net.core.netdev_budget=300
sudo sysctl -w net.core.netdev_budget_usecs=8000
sudo sysctl -w vm.dirty_ratio=20
sudo sysctl -w vm.dirty_background_ratio=10
```

When in doubt on a disposable host, reboot and re-run `.venv/bin/os-param-tuning doctor`
before the next experiment.
