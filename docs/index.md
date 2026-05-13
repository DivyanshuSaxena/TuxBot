# SemaTune

SemaTune is a system-wide tuning framework for improving application
performance by changing operating-system parameters at runtime. It sits beside a
target application, measures behavior over repeated windows, chooses the next OS
configuration with a tuner, validates the proposed changes, applies them through
typed host-side actuators, and records the observed effect.

The framework is useful when an application is sensitive to scheduler, CPU
power, memory, I/O, or networking policy, but the best OS settings are not known
ahead of time. A SemaTune session can optimize a direct application objective,
such as p99 latency or throughput, or it can reason from proxy/system metrics
when the application objective is unavailable or too expensive to expose.

The current CLI command is `os-param-tuning`. The command name is kept for
compatibility; the project and documentation use the name SemaTune.

!!! warning "Use a clean, disposable host"

    SemaTune can change live Linux scheduler, CPU, memory, networking, and
    sysctl-style parameters with `sudo`. It is highly recommended to use a clean
    dedicated machine or disposable test host where you have sudo rights and can
    restore or reboot freely. Do not run SemaTune on your personal machine or an
    important shared host unless you fully accept the risk of degraded
    performance, unstable settings, or manual recovery.

## Use SemaTune When

- You have a long-running workload, service, or benchmark.
- You can measure behavior in repeated windows.
- You want to tune Linux scheduler, CPU, memory, networking, or sysctl-style
  parameters.
- You can run on a dedicated, isolated, or disposable host.

## Do Not Use SemaTune When

- You need sub-second production control.
- You cannot tolerate host-level parameter changes.
- You are tuning a multi-tenant production host without isolation.
- You cannot restore or reboot the machine if a run leaves the host in a bad
  state.

## Fastest Successful Path

Install SemaTune, run `.venv/bin/os-param-tuning doctor`, run the fixed `sysbench_cpu`
smoke config, inspect the result directory, then try one tuner. The
[Quick Start](quick-start.md) page gives the exact commands.

## Mental Model

A SemaTune run has five moving parts:

- **Target application**: the workload or service being tuned.
- **OS parameter surface**: the Linux knobs SemaTune is allowed to change.
- **Metrics**: direct application metrics and optional proxy system metrics.
- **Tuner**: the decision maker, such as fixed, LLM, Bayesian, MLOS,
  Q-learning, or DQN.
- **Validation and actuation**: the host-side boundary that checks proposed
  parameter values before writing them to the OS.

The included `sysbench_cpu` and TPCC targets are maintained examples of this
model. They are small enough to run and inspect, but the framework is designed
around extension: adding a new target means writing an adapter that prepares the
application, observes measurement windows, parses metrics, and cleans up.

## Where To Start

Start with [Quick Start](quick-start.md), then read
[Safety and Restore](safety-and-restore.md) before tuning anything beyond the
smoke examples. [How SemaTune Works](how-it-works.md) explains the control-loop
model, and [Direct And Proxy Metrics](direct-and-proxy-metrics.md) explains the
measurement choices. The [Walkthrough](walkthrough.md) uses `sysbench_cpu` to
show one run end to end.

After that:

- Use [Installation](installation.md) to prepare a host.
- Use [Included Targets](supported-benchmarks.md) for the maintained examples.
- Use [Configuration Reference](configuration.md) for every config field.
- Use [Extending SemaTune](extending.md) to add another target or tuner.

## Safety Model

SemaTune may change live Linux scheduler, CPU, networking, memory, and sysctl
parameters. Run it on a dedicated machine or isolated test host. Review the
config before starting a session, keep parameter ranges conservative for new
targets, and preserve `OS_PARAM_TUNING_ROOT` when running with `sudo`.
