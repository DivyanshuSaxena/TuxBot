#!/usr/bin/env python3
"""GAP Benchmark Suite graph kernels.

One long-lived kernel run covers the whole session and each optimizer window
counts the trials that finished inside it. Generating and building the graph
costs far more than a trial -- 81s against 12s at scale 27 -- so it happens
once, before the first window, rather than once per window.
"""

import logging
import os
import re
import shutil
import signal
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from ..benchmark import BenchmarkInterface, BenchmarkMetrics
from .benchmark_registry import BenchmarkInfo, BenchmarkType

logger = logging.getLogger(__name__)

TRIAL_RE = re.compile(r"^Trial Time:\s+([0-9.]+)")
WINDOW_TRIALS = "gapbs_trials.txt"

# Kernels that take a source vertex and the ones that do not; all take -g/-n.
KERNELS = ("bc", "bfs", "cc", "cc_sv", "pr", "pr_spmv", "sssp", "tc")

# -r is parsed by every kernel (it is CLApp-level) but only these three read
# it. Passing it to the others is accepted and silently ignored, which would
# make a config look pinned when it is not.
SOURCE_KERNELS = ("bc", "bfs", "sssp")

# -t exists only on CLPageRank, so passing it to any other kernel is an
# unrecognized option and the process exits instead of running.
TOLERANCE_KERNELS = ("pr", "pr_spmv")


class GapbsBenchmark(BenchmarkInterface):
    """A GAPBS kernel run continuously over a generated graph."""

    def __init__(self, config):
        super().__init__(config)

        self.benchmark_info: BenchmarkInfo = BenchmarkType.from_string(config.benchmark).value
        self.gapbs_dir = os.path.expanduser(getattr(config, 'gapbs_dir', '~/gapbs'))
        # The benchmark name carries the default kernel (gapbs -> bc,
        # gapbs_pr -> pr); gapbs_kernel overrides it.
        self.kernel = (getattr(config, 'gapbs_kernel', None)
                       or self.benchmark_info.base_command[0])
        self.scale = getattr(config, 'gapbs_scale', 27)
        self.iterations = getattr(config, 'gapbs_iterations', 1)
        self.trials = getattr(config, 'gapbs_trials', 100000)
        self.source = getattr(config, 'gapbs_source', -1)
        self.graph_file = os.path.expanduser(
            getattr(config, 'gapbs_graph_file', '') or ''
        )
        self.tolerance = getattr(config, 'gapbs_tolerance', None)

        if self.kernel not in KERNELS:
            raise ValueError(
                f"Unknown GAPBS kernel '{self.kernel}'. Known kernels: {', '.join(KERNELS)}"
            )

        self.window_output_dir = os.path.join(
            self.results_dir, f"{self.benchmark_info.name}_windows"
        )
        os.makedirs(self.window_output_dir, exist_ok=True)
        self._continuous_log_file = os.path.join(
            self.window_output_dir, "continuous_gapbs.log"
        )

        self.continuous_process = None
        self._continuous_command: List[str] = []
        self._continuous_log_handle = None

    # ------------------------------------------------------------------ setup

    def _resolve_binary(self) -> str:
        path = os.path.join(self.gapbs_dir, self.kernel)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"GAPBS kernel not found at {path}. Build it with 'make' in the "
                f"gapbs checkout, or set gapbs_dir."
            )
        return path

    def _build_command(self) -> List[str]:
        cmd = [self._resolve_binary()]

        # GAPBS's Builder takes -f over -g, so pass one or the other. A
        # serialized graph is byte-identical run to run and skips the ~81s
        # generation at scale 27.
        if self.graph_file:
            if not os.path.isfile(self.graph_file):
                raise FileNotFoundError(
                    f"gapbs_graph_file {self.graph_file} does not exist. Build "
                    f"it with 'converter -g <scale> -b <file>' in the gapbs "
                    f"checkout, or unset gapbs_graph_file to generate instead."
                )
            cmd += ["-f", self.graph_file]
        else:
            cmd += ["-g", str(self.scale)]

        # -n is deliberately large: the process must outlast every window and is
        # killed at cleanup, so overestimating costs nothing while running out
        # mid-run fails the run.
        cmd += [
            "-i", str(self.iterations),
            "-n", str(self.trials),
        ]

        # Without -r, GAPBS advances one source vertex per trial from a
        # kRandSeed-seeded sequence, so trials do different amounts of work and
        # per-window latency carries that spread. Pinning the source makes every
        # trial identical. Note the kernel takes the given source as-is, without
        # the non-zero-out-degree check the random path applies.
        if self.source >= 0:
            if self.kernel in SOURCE_KERNELS:
                cmd += ["-r", str(self.source)]
            else:
                logger.warning(
                    "gapbs_source is set but %s takes no source vertex; "
                    "every trial already does the same work", self.kernel
                )

        # -t 0 never satisfies the early-exit test, so a trial runs exactly
        # gapbs_iterations passes. Left unset, PageRank stops when its error
        # falls under the tolerance, and that error is a float reduction over a
        # dynamic schedule -- reproducible to within its last bits, but not
        # guaranteed to break on the same iteration every trial.
        if self.tolerance is not None:
            if self.kernel in TOLERANCE_KERNELS:
                cmd += ["-t", str(self.tolerance)]
            else:
                logger.warning(
                    "gapbs_tolerance is set but %s takes no -t; ignoring",
                    self.kernel
                )

        # GAPBS prints through std::cout, which block-buffers into a file. A
        # trial line is ~40 bytes, so without this a window sees no trial until
        # ~100 of them have accumulated -- which at scale 27 is hours.
        if shutil.which("stdbuf"):
            return ["stdbuf", "-oL"] + cmd
        logger.warning(
            "stdbuf not found; GAPBS trial lines may be buffered and windows "
            "may report no trials"
        )
        return cmd

    def _foreign_kernel_pids(self) -> List[int]:
        """Any run of this kernel that is not the one we started."""
        try:
            found = subprocess.run(
                ["pgrep", "-f", f"{self.gapbs_dir}/{self.kernel} -"],
                capture_output=True, text=True,
            ).stdout.split()
        except (OSError, ValueError):
            return []
        ours = self.continuous_process.pid if self.continuous_process else None
        return [int(pid) for pid in found if int(pid) not in (ours, os.getpid())]

    def _ensure_continuous_process(self) -> None:
        if self.continuous_process and self.continuous_process.poll() is None:
            return

        if self.continuous_process is not None:
            raise RuntimeError(
                f"GAPBS exited before the run completed with return code "
                f"{self.continuous_process.returncode}. See {self._continuous_log_file}. "
                f"Raise gapbs_trials for longer runs."
            )

        stale = self._foreign_kernel_pids()
        if stale:
            raise RuntimeError(
                f"{self.kernel} is already running (pids {stale}). A leftover from "
                f"an earlier run competes for the same machine and the trial rate "
                f"would still look plausible. Kill it and re-run."
            )

        cmd = self._wrap_with_taskset(self._build_command())
        self._continuous_command = cmd

        self._continuous_log_handle = open(
            self._continuous_log_file, "a", encoding="utf-8", buffering=1
        )
        self._continuous_log_handle.write(
            f"\n{'=' * 80}\n"
            f"Started continuous GAPBS at {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
            f"Command: {' '.join(cmd)}\n"
            f"{'=' * 80}\n"
        )

        self.continuous_process = subprocess.Popen(
            cmd,
            stdout=self._continuous_log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        logger.info("Continuous GAPBS started with PID %s", self.continuous_process.pid)

    def pre_execute(self) -> bool:
        """Start the kernel and wait out graph generation and build.

        A window that opened during those would measure them rather than the
        traversal, and they cost several times what a trial does.
        """
        self._resolve_binary()
        self._ensure_continuous_process()

        deadline = time.time() + 1800
        while time.time() < deadline:
            if self.continuous_process.poll() is not None:
                raise RuntimeError(
                    f"GAPBS exited during graph build with return code "
                    f"{self.continuous_process.returncode}. See {self._continuous_log_file}"
                )
            if self._read_trials():
                logger.info("GAPBS completed its first trial; graph is built")
                return True
            time.sleep(1.0)

        raise RuntimeError(
            f"GAPBS completed no trial within 1800s. Lower gapbs_scale, or see "
            f"{self._continuous_log_file}"
        )

    def get_target_pid(self):
        if self.continuous_process and self.continuous_process.poll() is None:
            return self.continuous_process.pid
        return None

    def _signal_group(self, sig) -> None:
        pid = self.continuous_process.pid
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

    def cleanup(self) -> None:
        if self.continuous_process and self.continuous_process.poll() is None:
            self._signal_group(signal.SIGTERM)
            try:
                self.continuous_process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                logger.warning("GAPBS ignored SIGTERM; killing it")
                self._signal_group(signal.SIGKILL)
                try:
                    self.continuous_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.error(
                        "GAPBS pid %s survived SIGKILL", self.continuous_process.pid
                    )
        if self._continuous_log_handle:
            self._continuous_log_handle.close()
            self._continuous_log_handle = None

    # ----------------------------------------------------------------- window

    def _read_trials(self) -> List[float]:
        """Every per-trial time the kernel has printed so far, in seconds."""
        trials: List[float] = []
        try:
            with open(self._continuous_log_file, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = TRIAL_RE.match(line.strip())
                    if match:
                        trials.append(float(match.group(1)))
        except FileNotFoundError:
            pass
        return trials

    def execute_window(self, window_number: int, duration: int) -> BenchmarkMetrics:
        self._ensure_continuous_process()

        window_dir = os.path.join(self.window_output_dir, f"window_{window_number}")
        os.makedirs(window_dir, exist_ok=True)

        start_index = len(self._read_trials())
        window_start_time = self.start_system_measurement(window_number, duration)
        perf_info = self.collect_perf_metrics(window_number, duration)

        deadline = time.time() + duration
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            if self.continuous_process.poll() is not None:
                break
            time.sleep(min(0.25, remaining))

        window_end_time = time.time()
        if self.continuous_process.poll() is not None:
            raise RuntimeError(
                f"GAPBS exited during window {window_number} with return code "
                f"{self.continuous_process.returncode}. See {self._continuous_log_file}. "
                f"Raise gapbs_trials for longer runs."
            )

        self.finalize_perf_metrics(window_number, perf_info)
        time.sleep(0.5)

        trials = self._read_trials()[start_index:]
        elapsed = window_end_time - window_start_time
        with open(os.path.join(window_dir, WINDOW_TRIALS), "w", encoding="utf-8") as handle:
            handle.write(f"window_seconds {elapsed:.3f}\n")
            for value in trials:
                handle.write(f"{value}\n")

        metrics = self.parse_results(window_dir)
        metrics.extra_metrics["continuous_log_file"] = self._continuous_log_file
        self._populate_system_metrics(
            metrics, window_number, window_start_time, window_end_time
        )
        logger.info(
            "GAPBS window %s: %s trials, %.4f trials/sec",
            window_number, len(trials), metrics.throughput,
        )
        return metrics

    def parse_results(self, output_dir: str) -> BenchmarkMetrics:
        """Trials completed per second, plus their mean time.

        A window can legitimately contain zero completed trials when one trial
        takes longer than the window, so throughput is 0 rather than an error.
        The system metrics still describe the window, which is why the objective
        may be one of those instead.
        """
        path = os.path.join(output_dir, WINDOW_TRIALS)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No GAPBS trial output at {path}")

        elapsed = 0.0
        trials: List[float] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("window_seconds "):
                    elapsed = float(line.split()[1])
                else:
                    trials.append(float(line))

        metrics = BenchmarkMetrics()
        if elapsed > 0:
            metrics.throughput = len(trials) / elapsed
            metrics.goodput = metrics.throughput
        if trials:
            metrics.latency_avg = 1000.0 * sum(trials) / len(trials)
        metrics.extra_metrics.update({
            "trials": len(trials),
            "window_seconds": elapsed,
            "trial_time_min_s": min(trials) if trials else None,
            "trial_time_max_s": max(trials) if trials else None,
            "gapbs_kernel": self.kernel,
            "gapbs_scale": self.scale,
            "gapbs_source": self.source,
            "gapbs_tolerance": self.tolerance,
            "gapbs_graph_file": self.graph_file or None,
        })
        return metrics
