#!/usr/bin/env python3
"""RocksDB db_bench benchmark.

One long-lived db_bench runs for the whole session and each optimizer window
reads the slice of its interval CSV that landed inside the window. Relaunching
per window would reset page placement every iteration, which is the state a NUMA
tuning run is trying to measure.
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List

from ..benchmark import BenchmarkInterface, BenchmarkMetrics
from .benchmark_registry import BenchmarkInfo, BenchmarkType

logger = logging.getLogger(__name__)

# Written by --report_interval_seconds; header is "secs_elapsed,interval_qps".
WINDOW_CSV = "db_bench_intervals.csv"


class DbBenchBenchmark(BenchmarkInterface):
    """RocksDB db_bench against a pre-built database."""

    def __init__(self, config):
        super().__init__(config)

        self.benchmark_info: BenchmarkInfo = BenchmarkType.from_string(config.benchmark).value
        self.binary = getattr(config, 'db_bench_binary', '~/rocksdb/db_bench')
        self.db_path = os.path.expanduser(getattr(config, 'db_bench_db', '/mydata/rocksdb'))
        self.benchmarks = getattr(config, 'db_bench_benchmarks', 'readwhilewriting')
        self.threads = getattr(config, 'db_bench_threads', 32)
        self.cache_size = getattr(config, 'db_bench_cache_size', 1048576)
        self.report_interval = getattr(config, 'db_bench_report_interval', 1)

        self.window_output_dir = os.path.join(
            self.results_dir, f"{self.benchmark_info.name}_windows"
        )
        os.makedirs(self.window_output_dir, exist_ok=True)
        self.report_file = os.path.join(self.window_output_dir, "db_bench_report.csv")
        self._continuous_log_file = os.path.join(
            self.window_output_dir, "continuous_db_bench.log"
        )

        self.continuous_process = None
        self._continuous_command: List[str] = []
        self._continuous_log_handle = None

    # ------------------------------------------------------------------ setup

    def _resolve_binary(self) -> str:
        """Locate db_bench, by path or on PATH."""
        candidate = os.path.expanduser(self.binary)
        if os.path.sep in candidate:
            if not os.path.isfile(candidate):
                raise FileNotFoundError(
                    f"db_bench not found at {candidate}. Build it with "
                    f"'make db_bench' in the RocksDB checkout, or set db_bench_binary."
                )
            return candidate
        found = shutil.which(candidate)
        if not found:
            raise FileNotFoundError(
                f"db_bench '{candidate}' is not on PATH. Set db_bench_binary to its path."
            )
        return found

    def _build_command(self, duration: int) -> List[str]:
        return [
            self._resolve_binary(),
            f"--benchmarks={self.benchmarks}",
            f"--db={self.db_path}",
            "--use_existing_db=1",
            "--compression_type=none",
            f"--threads={self.threads}",
            f"--duration={duration}",
            f"--cache_size={self.cache_size}",
            "--histogram=1",
            f"--report_interval_seconds={self.report_interval}",
            f"--report_file={self.report_file}",
        ]

    def _run_seconds(self) -> int:
        """How long the continuous process must live to outlast every window.

        Each iteration costs a window plus the settle wait plus tuner think
        time, and an LLM round trip is the unpredictable part -- so this is
        deliberately generous. db_bench exiting mid-run fails the run.
        """
        windows = (
            getattr(self.config, "max_iterations", 1)
            + getattr(self.config, "post_tuning_windows", 0)
        )
        per_window = (
            getattr(self.config, "window_duration", 1)
            + getattr(self.config, "settle_seconds", 0)
            + 60
        )
        return windows * per_window + 300

    def _ensure_continuous_process(self) -> None:
        """Start the long-running db_bench if it is not already up."""
        if self.continuous_process and self.continuous_process.poll() is None:
            return

        if self.continuous_process is not None:
            raise RuntimeError(
                f"Continuous db_bench exited before the run completed with return code "
                f"{self.continuous_process.returncode}. See {self._continuous_log_file}."
            )

        if not os.path.isdir(self.db_path):
            raise FileNotFoundError(
                f"db_bench database {self.db_path} does not exist. It is a fixture "
                f"built once with --benchmarks=fillseq, not by this run."
            )

        stale = self._foreign_db_bench_pids()
        if stale:
            raise RuntimeError(
                f"db_bench is already running on {self.db_path} (pids {stale}). "
                f"A leftover from an earlier run competes for the same database "
                f"and the throughput would still look plausible, so this stops "
                f"rather than measuring it. Kill it and re-run."
            )

        cmd = self._wrap_with_taskset(self._build_command(self._run_seconds()))
        self._continuous_command = cmd

        # Straight to a file rather than PIPE: db_bench is chatty and an
        # undrained pipe would block it.
        self._continuous_log_handle = open(
            self._continuous_log_file, "a", encoding="utf-8", buffering=1
        )
        self._continuous_log_handle.write(
            f"\n{'=' * 80}\n"
            f"Started continuous db_bench at {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
            f"Command: {' '.join(cmd)}\n"
            f"{'=' * 80}\n"
        )

        self.continuous_process = subprocess.Popen(
            cmd,
            stdout=self._continuous_log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        logger.info("Continuous db_bench started with PID %s", self.continuous_process.pid)
        logger.info("Continuous db_bench log: %s", self._continuous_log_file)

    def _foreign_db_bench_pids(self):
        """Any db_bench on this database that is not the one we started."""
        try:
            found = subprocess.run(
                ["pgrep", "-f", f"db_bench.*--db={self.db_path}"],
                capture_output=True, text=True,
            ).stdout.split()
        except (OSError, ValueError):
            return []
        ours = self.continuous_process.pid if self.continuous_process else None
        return [int(pid) for pid in found if int(pid) not in (ours, os.getpid())]

    def pre_execute(self) -> bool:
        """Start db_bench and wait for it to report, so window 1 is not startup."""
        self._resolve_binary()
        self._ensure_continuous_process()

        deadline = time.time() + 120
        while time.time() < deadline:
            if self.continuous_process.poll() is not None:
                raise RuntimeError(
                    f"db_bench exited during warm-up with return code "
                    f"{self.continuous_process.returncode}. See {self._continuous_log_file}"
                )
            if self._read_report_rows():
                logger.info("db_bench is reporting intervals; warm-up complete")
                return True
            time.sleep(0.5)

        raise RuntimeError(
            f"db_bench produced no interval report within 120s. "
            f"See {self._continuous_log_file}"
        )

    def cleanup(self) -> None:
        """Stop db_bench. The database is a shared fixture and is left alone."""
        # The whole group, not the leader: db_bench is started in its own
        # session, and a leftover would compete with the next run's database.
        if self.continuous_process and self.continuous_process.poll() is None:
            self._signal_group(signal.SIGTERM)
            try:
                self.continuous_process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                logger.warning("db_bench ignored SIGTERM; killing it")
                self._signal_group(signal.SIGKILL)
                try:
                    self.continuous_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.error(
                        "db_bench pid %s survived SIGKILL", self.continuous_process.pid
                    )
        if self._continuous_log_handle:
            self._continuous_log_handle.close()
            self._continuous_log_handle = None

    def _signal_group(self, sig) -> None:
        """Signal db_bench's process group, falling back to the leader."""
        pid = self.continuous_process.pid
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

    # ----------------------------------------------------------------- window

    def _read_report_rows(self) -> List[Dict[str, float]]:
        """Read every interval row db_bench has written so far."""
        rows: List[Dict[str, float]] = []
        try:
            with open(self.report_file, encoding="utf-8") as handle:
                handle.readline()  # header
                for line in handle:
                    fields = line.strip().split(",")
                    if len(fields) < 2:
                        continue
                    try:
                        rows.append({
                            "secs_elapsed": int(fields[0]),
                            "interval_qps": float(fields[1]),
                        })
                    except ValueError:
                        continue
        except FileNotFoundError:
            pass
        return rows

    def execute_window(self, window_number: int, duration: int) -> BenchmarkMetrics:
        self._ensure_continuous_process()

        window_dir = os.path.join(self.window_output_dir, f"window_{window_number}")
        os.makedirs(window_dir, exist_ok=True)

        start_index = len(self._read_report_rows())
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
                f"Continuous db_bench exited during window {window_number} with return "
                f"code {self.continuous_process.returncode}. See {self._continuous_log_file}"
            )

        self.finalize_perf_metrics(window_number, perf_info)
        time.sleep(0.5)

        rows = self._read_report_rows()[start_index:]
        if not rows:
            raise RuntimeError(
                f"No db_bench interval reports captured for window {window_number}. "
                f"See {self._continuous_log_file}"
            )

        window_csv = os.path.join(window_dir, WINDOW_CSV)
        with open(window_csv, "w", encoding="utf-8") as handle:
            handle.write("secs_elapsed,interval_qps\n")
            for row in rows:
                handle.write(f"{row['secs_elapsed']},{row['interval_qps']}\n")

        metrics = self.parse_results(window_dir)
        metrics.extra_metrics["continuous_log_file"] = self._continuous_log_file
        self._populate_system_metrics(
            metrics, window_number, window_start_time, window_end_time
        )
        logger.info(
            "db_bench window %s: %.0f ops/sec over %s intervals",
            window_number, metrics.throughput, len(rows),
        )
        return metrics

    def parse_results(self, output_dir: str) -> BenchmarkMetrics:
        """Average the window's interval throughput.

        The interval CSV carries no latency, and db_bench prints its histogram
        only when it exits -- so a continuous run has per-window throughput but
        no per-window latency, and latency_avg/latency_p95 stay 0.
        """
        path = os.path.join(output_dir, WINDOW_CSV)
        if not os.path.exists(path):
            raise FileNotFoundError(f"No db_bench interval output at {path}")

        qps: List[float] = []
        with open(path, encoding="utf-8") as handle:
            handle.readline()
            for line in handle:
                fields = line.strip().split(",")
                if len(fields) >= 2:
                    try:
                        qps.append(float(fields[1]))
                    except ValueError:
                        continue

        if not qps:
            raise ValueError(f"No interval rows parsed from {path}")

        metrics = BenchmarkMetrics()
        metrics.throughput = sum(qps) / len(qps)
        metrics.goodput = metrics.throughput
        metrics.extra_metrics.update({
            "intervals": len(qps),
            "interval_qps_min": min(qps),
            "interval_qps_max": max(qps),
            "db_bench_benchmarks": self.benchmarks,
            "db_bench_threads": self.threads,
        })
        return metrics
