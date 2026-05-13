# SemaTune OS Parameter Reference

This page is an operator reference for parameters understood by
`ParameterManager`. A config can tune any subset of these names through
`parameter_ranges` and `parameters_to_tune`.

The tables below are conservative documentation, not universal tuning advice.
Hardware, kernel version, firmware, CPU driver, and workload shape all matter.
Read [Safety and Restore](safety-and-restore.md) before expanding ranges.

Restore behavior means the current SemaTune implementation behavior, not what
Linux could theoretically support. Scheduler debugfs parameters are the best
supported for original-value snapshots. Many sysfs and sysctl parameters should
be treated as manual/best-effort restore unless you have recorded host values
outside the run.

## Scheduler Knobs

| Parameter | Why it matters | Linux interface, unit, scope | Getter and restore | Prerequisites and common failure | Safe starting range and interactions |
| --- | --- | --- | --- | --- | --- |
| `latency_ns` | Sets the target CFS period over which runnable tasks should get CPU time. | `debugfs`; ns; global. | Getter supported through scheduler debugfs; automatic best-effort restore on normal exit. | Needs mounted `debugfs` and scheduler files. Failure usually means missing `/sys/kernel/debug/sched/*` or permission denied. | Example: `12000000` to `48000000`. Tune with `min_granularity_ns` and `wakeup_granularity_ns`; keep `min_granularity_ns <= latency_ns`. |
| `min_granularity_ns` | Controls the minimum CFS slice and can trade context-switch overhead against latency. | `debugfs`; ns; global. | Getter supported; automatic best-effort restore on normal exit. | Needs mounted `debugfs`; missing path on unsupported kernels. | Example: `1000000` to `10000000`. Tune with `latency_ns` and `wakeup_granularity_ns`; avoid values larger than `latency_ns`. |
| `wakeup_granularity_ns` | Controls how easily waking tasks preempt running tasks. | `debugfs`; ns; global. | Getter supported; automatic best-effort restore on normal exit. | Needs mounted `debugfs`; permission issue if not root. | Example: `1000000` to `8000000`. Tune with `latency_ns` and `min_granularity_ns`; too high can hurt interactive latency. |
| `migration_cost_ns` | Influences how expensive CFS considers moving tasks across CPUs. | `debugfs`; ns; global. | Getter supported; automatic best-effort restore on normal exit. | Needs mounted `debugfs`; missing path on unsupported kernels. | Example: `100000` to `5000000`. Interacts with core pinning and workload locality. |
| `sched_autogroup_enabled` | Enables scheduler autogrouping, which can change how interactive groups receive CPU. | `sysctl kernel.sched_autogroup_enabled`; boolean; global. | No per-run getter in current restore path; manual/best-effort. | Missing sysctl on kernels without autogroup support. | Example: `[true, false]` only on isolated hosts. Interacts with scheduler knobs and process grouping. |
| `sched_cfs_bandwidth_slice_us` | Controls CFS bandwidth controller slice size for quota-managed workloads. | `sysctl kernel.sched_cfs_bandwidth_slice_us`; us; global. | Manual/best-effort. | Missing sysctl or permission denied. | Example: `1000` to `10000`. Relevant with cgroups CPU quota. |

## CPU Frequency, Power, and Idle-State Knobs

| Parameter | Why it matters | Linux interface, unit, scope | Getter and restore | Prerequisites and common failure | Safe starting range and interactions |
| --- | --- | --- | --- | --- | --- |
| `scaling_governor` | Selects the CPU-frequency governor and changes frequency response policy. | `sysfs cpufreq`; categorical; per-policy/per-core syntax. | Manual/best-effort. | Needs `/sys/devices/system/cpu/cpufreq/policy*/scaling_governor`; unsupported governor is common. | Start with `performance`, `powersave`, or `schedutil` if present. Interacts with `scaling_min_freq`, `scaling_max_freq`, and `epp`. |
| `scaling_min_freq` | Sets minimum CPU frequency floor. | `sysfs cpufreq`; kHz; per-policy/per-core syntax. | Manual/best-effort. | Missing cpufreq path, driver rejects value, or min above max. | Use host policy limits from `scaling_available_frequencies` when present. Tune with `scaling_max_freq`. |
| `scaling_max_freq` | Sets maximum CPU frequency ceiling. | `sysfs cpufreq`; kHz; per-policy/per-core syntax. | Manual/best-effort. | Missing cpufreq path, driver rejects value, or max below min. | Use host policy limits. Tune with `scaling_min_freq`; avoid contradictory min/max. |
| `epp` | Sets Energy-Performance Preference for drivers that expose it. | `sysfs cpufreq energy_performance_preference`; categorical; per-policy/per-core syntax. | Manual/best-effort. | Missing EPP path or governor/driver does not permit the value. | Try `performance`, `balance_performance`, `balance_power`, `power`. Interacts with governor and Intel P-state. |
| `min_perf_pct` | Sets Intel P-state minimum performance percentage. | `intel_pstate`; percent; effectively global despite core argument. | Manual/best-effort. | Needs `/sys/devices/system/cpu/intel_pstate/min_perf_pct`; unavailable on non-Intel-P-state hosts. | Example: `0` to `80`. Must stay `<= max_perf_pct`; tune with `max_perf_pct`, `turbo`, and `cstate_max`. |
| `max_perf_pct` | Sets Intel P-state maximum performance percentage. | `intel_pstate`; percent; effectively global despite core argument. | Manual/best-effort. | Needs Intel P-state; driver may reject values. | Example: `50` to `100`. Must stay `>= min_perf_pct`; tune with `min_perf_pct`, `turbo`, and `cstate_max`. |
| `turbo` | Enables or disables turbo boost. | `intel_pstate no_turbo`; boolean; global. | Manual/best-effort. | Missing Intel P-state path or firmware policy blocks turbo. | Try `[true, false]`. Interacts with `min_perf_pct`, `max_perf_pct`, power, thermals, and `cstate_max`. |
| `pmqos` | Sets latency tolerance for CPU idle behavior. | PM QoS/sysfs paths; us; per-core. | Manual/best-effort. | Missing PM QoS path or permission issue. | Start with `0` or modest values. Interacts with `cstate_max` and latency-sensitive workloads. |
| `cstate_max` | Limits deepest CPU idle state and can trade latency against power. | `sysfs cpuidle state*/disable`; categorical; per-core. | Manual/best-effort; reset by enabling idle states. | Missing cpuidle paths or unavailable C-state name. | Try `unlimited`, `C1`, `C6` before aggressive settings. Interacts with `turbo`, `min_perf_pct`, and `max_perf_pct`. |

## Networking Knobs

| Parameter | Why it matters | Linux interface, unit, scope | Getter and restore | Prerequisites and common failure | Safe starting range and interactions |
| --- | --- | --- | --- | --- | --- |
| `busy_poll` | Allows socket busy polling, trading CPU for lower network latency. | `sysctl net.core.busy_poll`; us; global with optional IRQ affinity side effect. | Manual/best-effort. | Missing sysctl, permission denied, or NIC/driver does not benefit. | Example: `0` to `100`. Tune with `napi_busy_poll` and `busy_read`; start at `0` for CPU-bound workloads. |
| `napi_busy_poll` | Alias for `busy_poll` in SemaTune configs. | `sysctl net.core.busy_poll`; us; global alias. | Manual/best-effort. | Same as `busy_poll`. | Do not tune separately from `busy_poll`; they target the same sysctl. |
| `busy_read` | Allows receive-side busy read polling. | `sysctl net.core.busy_read`; us; global with optional IRQ affinity side effect. | Manual/best-effort. | Missing sysctl, high CPU usage, or no benefit on driver. | Example: `0` to `100`. Tune with `busy_poll`/`napi_busy_poll`. |
| `netdev_budget` | Sets packets processed per NAPI poll cycle. | `sysctl net.core.netdev_budget`; packets; global. | Manual/best-effort. | Missing sysctl or permission denied. | Example: `100` to `1000`. Tune with `netdev_budget_usecs` for network-heavy targets. |
| `netdev_budget_usecs` | Sets time budget per NAPI poll cycle. | `sysctl net.core.netdev_budget_usecs`; us; global. | Manual/best-effort. | Missing sysctl or permission denied. | Example: `1000` to `10000`. Tune with `netdev_budget`. |
| `somaxconn` | Controls maximum listen backlog. | `sysctl net.core.somaxconn`; count; global. | Manual/best-effort. | Missing sysctl or app backlog lower than OS limit. | Example: `128` to `4096`. Interacts with server listen backlog and connection load. |
| `netdev_max_backlog` | Controls incoming packet backlog before protocol processing. | `sysctl net.core.netdev_max_backlog`; packets; global. | Manual/best-effort. | Missing sysctl or memory pressure. | Example: `1000` to `10000`. Interacts with NAPI budget under packet bursts. |
| `rmem_default` | Default receive socket buffer size. | `sysctl net.core.rmem_default`; bytes; global. | Manual/best-effort. | Must not exceed effective max on some hosts. | Example: `212992` to `4194304`. Tune with `rmem_max`; keep default `<= max`. |
| `wmem_default` | Default send socket buffer size. | `sysctl net.core.wmem_default`; bytes; global. | Manual/best-effort. | Must not exceed effective max on some hosts. | Example: `212992` to `4194304`. Tune with `wmem_max`; keep default `<= max`. |
| `rmem_max` | Maximum receive socket buffer size. | `sysctl net.core.rmem_max`; bytes; global. | Manual/best-effort. | Memory pressure or permission issue. | Example: `4194304` to `67108864`. Tune with `rmem_default`. |
| `wmem_max` | Maximum send socket buffer size. | `sysctl net.core.wmem_max`; bytes; global. | Manual/best-effort. | Memory pressure or permission issue. | Example: `4194304` to `67108864`. Tune with `wmem_default`. |
| `tcp_fin_timeout` | Controls FIN-WAIT-2 timeout. | `sysctl net.ipv4.tcp_fin_timeout`; seconds; global. | Manual/best-effort. | Missing sysctl or unsafe value for workload. | Example: `15` to `60`. Relevant for connection-heavy services. |
| `tcp_tw_reuse` | Controls TIME-WAIT socket reuse mode. | `sysctl net.ipv4.tcp_tw_reuse`; bit/mode `0`, `1`, `2`; global. | Manual/best-effort. | Kernel semantics vary; value rejected on some versions. | Keep conservative. Interacts with connection churn and correctness expectations. |
| `tcp_mtu_probing` | Controls TCP path MTU probing. | `sysctl net.ipv4.tcp_mtu_probing`; mode `0`, `1`, `2`; global. | Manual/best-effort. | Missing sysctl or network path assumptions. | Try only when MTU black holes are relevant. |
| `tcp_timestamps` | Enables TCP timestamps. | `sysctl net.ipv4.tcp_timestamps`; boolean `0/1`; global. | Manual/best-effort. | Missing sysctl or policy restriction. | Usually leave enabled unless testing a specific network path. |
| `tcp_sack` | Enables selective acknowledgments. | `sysctl net.ipv4.tcp_sack`; boolean `0/1`; global. | Manual/best-effort. | Missing sysctl or policy restriction. | Usually leave enabled; changing can hurt lossy networks. |
| `tcp_window_scaling` | Enables TCP window scaling. | `sysctl net.ipv4.tcp_window_scaling`; boolean `0/1`; global. | Manual/best-effort. | Missing sysctl or policy restriction. | Usually leave enabled; interacts with socket buffer sizes. |
| `tcp_fastopen` | Controls TCP Fast Open mode bitmask. | `sysctl net.ipv4.tcp_fastopen`; bitmask; global. | Manual/best-effort. | Kernel/app support and middlebox behavior. | Treat as workload-specific; verify correctness. |
| `tcp_congestion_control` | Selects TCP congestion-control algorithm. | `sysctl net.ipv4.tcp_congestion_control`; categorical; global. | Manual/best-effort. | Algorithm not loaded or unavailable. | Try only installed algorithms such as `cubic`, `reno`, or `bbr`; interacts with network path. |

## VM, Memory, and NUMA Knobs

| Parameter | Why it matters | Linux interface, unit, scope | Getter and restore | Prerequisites and common failure | Safe starting range and interactions |
| --- | --- | --- | --- | --- | --- |
| `vm_swappiness` | Controls aggressiveness of swapping anonymous memory. | `sysctl vm.swappiness`; percent-like score; global. | Manual/best-effort. | Missing sysctl is rare; permission denied if not root. | Example: `1` to `100`. Depends on memory pressure and swap availability. |
| `vm_dirty_ratio` | Max dirty-memory percentage before writers are throttled. | `sysctl vm.dirty_ratio`; percent; global. | Manual/best-effort. | Value must be above background ratio. | Example: `10` to `40`. Tune with `vm_dirty_background_ratio`; keep background `< dirty`. |
| `vm_dirty_background_ratio` | Dirty-memory percentage where background writeback starts. | `sysctl vm.dirty_background_ratio`; percent; global. | Manual/best-effort. | Value must be below dirty ratio. | Example: `5` to `20`. Tune with `vm_dirty_ratio`. |
| `vm_dirty_expire_centisecs` | Age at which dirty data becomes old enough for writeback. | `sysctl vm.dirty_expire_centisecs`; centiseconds; global. | Manual/best-effort. | Permission issue or unsafe extreme values. | Example: `1000` to `30000`. Interacts with writeback interval and storage behavior. |
| `vm_dirty_writeback_centisecs` | Periodic writeback wakeup interval. | `sysctl vm.dirty_writeback_centisecs`; centiseconds; global. | Manual/best-effort. | Permission issue or unsafe extreme values. | Example: `100` to `5000`. Tune with `vm_dirty_expire_centisecs`. |
| `zone_reclaim_mode` | Controls NUMA zone reclaim behavior. | `sysctl vm.zone_reclaim_mode`; bitmask; global. | Manual/best-effort. | NUMA behavior varies by host; value can hurt latency. | Try `0` first; use other bitmask values only with NUMA-specific reasoning. |
| `numa_balancing` | Enables automatic NUMA memory balancing. | `sysctl kernel.numa_balancing`; boolean; global. | Manual/best-effort. | Missing sysctl on unsupported kernels. | Try `[true, false]` for NUMA hosts; interacts with pinning and memory locality. |

## Important Interactions

- `latency_ns`, `min_granularity_ns`, and `wakeup_granularity_ns` should be
  tuned together; avoid semantically contradictory scheduler windows.
- `min_perf_pct` must not exceed `max_perf_pct`.
- `cstate_max`, `turbo`, `min_perf_pct`, and `max_perf_pct` jointly shape
  latency, power, and thermal behavior.
- `busy_poll`, `napi_busy_poll`, and `busy_read` can burn CPU for lower network
  latency; `napi_busy_poll` is an alias for `busy_poll`.
- `rmem_default`/`rmem_max` and `wmem_default`/`wmem_max` should be constrained
  so defaults do not exceed maxima.
- `vm_dirty_background_ratio` should remain lower than `vm_dirty_ratio`.
