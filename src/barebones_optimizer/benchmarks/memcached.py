#!/usr/bin/env python3
"""Memcached driven by mutilate from a second machine.

memcached runs on this node for the whole session and one mutilate on the
client offers a fixed load across every window. mutilate is started over ssh
with --report_interval, a local patch that prints each client thread's
cumulative counts and latency histogram once a second; the lines stream back
over the ssh session, and a window is the difference between the last line of
each thread before it opened and the last before it closed.
"""

import logging
import os
import shlex
import signal
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional

from ..benchmark import BenchmarkInterface, BenchmarkMetrics
from .benchmark_registry import BenchmarkInfo, BenchmarkType

logger = logging.getLogger(__name__)

INTERVAL_TAG = "MUTILATE_INTERVAL"
WINDOW_FILE = "mutilate_intervals.txt"
# mutilate's LogHistogramSampler: bin i holds latencies in [POW^i, POW^(i+1)) us.
HIST_POW = 1.1


class IntervalLine:
    """One cumulative report of one mutilate thread."""

    __slots__ = ("ts", "thread", "gets", "sets", "misses", "bins", "raw")

    def __init__(self, ts, thread, gets, sets, misses, bins, raw=""):
        self.ts = ts
        self.thread = thread
        self.gets = gets
        self.sets = sets
        self.misses = misses
        self.bins = bins
        self.raw = raw

    @classmethod
    def parse(cls, line: str) -> Optional["IntervalLine"]:
        fields = line.split()
        if len(fields) < 6 or fields[0] != INTERVAL_TAG:
            return None
        try:
            bins: Dict[int, int] = {}
            for token in fields[6:]:
                index, count = token[1:].split(":")
                bins[int(index)] = bins.get(int(index), 0) + int(count)
            return cls(float(fields[1]), int(fields[2]), int(fields[3]),
                       int(fields[4]), int(fields[5]), bins, line.rstrip("\n"))
        except ValueError:
            return None


def histogram_percentile(bins: Dict[int, int], pct: float) -> float:
    """mutilate's own get_nth(), interpolating inside the bin, in us."""
    total = sum(bins.values())
    if total == 0:
        return 0.0
    target = total * pct / 100.0
    seen = 0
    for index in sorted(bins):
        count = bins[index]
        seen += count
        if seen > target:
            left = target - (seen - count)
            lo, hi = HIST_POW ** index, HIST_POW ** (index + 1)
            return lo + left / count * (hi - lo)
    return HIST_POW ** (max(bins) + 1)


def histogram_mean(bins: Dict[int, int]) -> float:
    total = sum(bins.values())
    if total == 0:
        return 0.0
    return sum(HIST_POW ** (i + 0.5) * n for i, n in bins.items()) / total


def window_stats(start: Dict[int, IntervalLine],
                 end: Dict[int, IntervalLine]) -> Dict[str, float]:
    """Difference two per-thread snapshots into one window's numbers.

    A thread with no line before the window opened is left out rather than
    counted from zero, which would charge its whole history to this window.
    """
    bins: Dict[int, int] = {}
    requests = gets = misses = 0
    qps = 0.0
    threads = 0
    for thread, last in end.items():
        first = start.get(thread)
        if first is None or last.ts <= first.ts:
            continue
        threads += 1
        d_gets = last.gets - first.gets
        d_reqs = d_gets + last.sets - first.sets
        gets += d_gets
        requests += d_reqs
        misses += last.misses - first.misses
        qps += d_reqs / (last.ts - first.ts)
        for index, count in last.bins.items():
            delta = count - first.bins.get(index, 0)
            if delta:
                bins[index] = bins.get(index, 0) + delta
    return {
        "threads": threads,
        "requests": requests,
        "achieved_qps": qps,
        "miss_ratio": misses / gets if gets else 0.0,
        "latency_avg": histogram_mean(bins),
        "latency_p50": histogram_percentile(bins, 50),
        "latency_p95": histogram_percentile(bins, 95),
        "latency_p99": histogram_percentile(bins, 99),
        "latency_p999": histogram_percentile(bins, 99.9),
    }


class MemcachedBenchmark(BenchmarkInterface):
    """Memcached under a fixed mutilate load from a remote client."""

    def __init__(self, config):
        super().__init__(config)

        self.benchmark_info: BenchmarkInfo = BenchmarkType.from_string(config.benchmark).value
        get = lambda name, default: getattr(config, name, default)
        self.binary = get("memcached_binary", "memcached")
        self.cpus = get("memcached_cpus", None)
        self.threads = get("memcached_threads", 4)
        self.memory_mb = get("memcached_memory_mb", 8192)
        self.port = get("memcached_port", 11211)
        self.client = get("mutilate_client_host", "node1")
        self.mutilate = get("mutilate_binary", "~/mutilate/mutilate")
        self.server_ip = get("mutilate_server_ip", "10.10.1.1")
        self.qps = get("mutilate_qps", 0)
        self.client_threads = get("mutilate_threads", None)
        self.connections = get("mutilate_connections", 8)
        self.depth = get("mutilate_depth", 1)
        self.keysize = get("mutilate_keysize", "fb_key")
        self.valuesize = get("mutilate_valuesize", "fb_value")
        self.iadist = get("mutilate_iadist", "fb_ia")
        self.update = get("mutilate_update", 0.0)
        self.records = get("mutilate_records", 1000000)

        self.window_output_dir = os.path.join(
            self.results_dir, f"{self.benchmark_info.name}_windows"
        )
        os.makedirs(self.window_output_dir, exist_ok=True)
        self._mutilate_log = os.path.join(self.window_output_dir, "continuous_mutilate.log")
        self._memcached_log = os.path.join(self.window_output_dir, "memcached.log")

        self.memcached_process = None
        self.mutilate_process = None
        self._handles = []
        self._read_pos = 0
        self._partial = ""
        self._latest: Dict[int, IntervalLine] = {}
        self._window_lines: List[str] = []

    # ------------------------------------------------------------------ setup

    def _as_user(self, cmd: List[str]) -> List[str]:
        """Run as the invoking user: the client trusts that user's key, not root's."""
        user = os.environ.get("SUDO_USER")
        if os.geteuid() == 0 and user:
            return ["sudo", "-u", user] + cmd
        return cmd

    def _ssh(self, remote: str, **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(
            self._as_user(["ssh", "-o", "BatchMode=yes", self.client, remote]),
            capture_output=True, text=True, **kwargs,
        )

    def _mutilate_args(self) -> List[str]:
        args = [
            self.mutilate, "-s", f"{self.server_ip}:{self.port}",
            "-K", str(self.keysize), "-V", str(self.valuesize),
            "-i", str(self.iadist), "-u", str(self.update),
            "-r", str(self.records), "-c", str(self.connections),
            "-d", str(self.depth),
        ]
        args += ["-T", str(self.client_threads) if self.client_threads else "$(nproc)"]
        return args

    def _remote_command(self, extra: List[str]) -> str:
        quoted = [a if a == "$(nproc)" else shlex.quote(a) for a in self._mutilate_args()]
        quoted[0] = self.mutilate
        return " ".join(quoted + [shlex.quote(a) for a in extra])

    def _run_seconds(self) -> int:
        """Long enough to outlast every window, as db_bench's continuous run is."""
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

    def _memcached_command(self) -> List[str]:
        cmd = [self.binary, "-t", str(self.threads), "-m", str(self.memory_mb),
               "-c", "16384", "-p", str(self.port), "-U", "0", "-l", "0.0.0.0"]
        if os.geteuid() == 0:
            cmd += ["-u", os.environ.get("SUDO_USER") or "nobody"]
        if self.cpus:
            cmd = ["taskset", "-c", str(self.cpus)] + cmd
        return cmd

    def _port_in_use(self) -> bool:
        out = subprocess.run(["ss", "-Hltn", f"sport = :{self.port}"],
                             capture_output=True, text=True).stdout
        return bool(out.strip())

    def _open_log(self, path: str, command: List[str]):
        handle = open(path, "a", encoding="utf-8", buffering=1)
        handle.write(
            f"\n{'=' * 80}\n"
            f"Started at {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
            f"Command: {' '.join(command)}\n"
            f"{'=' * 80}\n"
        )
        self._handles.append(handle)
        return handle

    def _start_memcached(self) -> None:
        if self._port_in_use():
            raise RuntimeError(
                f"Port {self.port} is already listening. A leftover memcached "
                f"would be measured in place of this one; stop it and re-run."
            )
        cmd = self._memcached_command()
        self.memcached_process = subprocess.Popen(
            cmd, stdout=self._open_log(self._memcached_log, cmd),
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        deadline = time.time() + 10
        while not self._port_in_use():
            if self.memcached_process.poll() is not None or time.time() > deadline:
                raise RuntimeError(f"memcached did not start. See {self._memcached_log}")
            time.sleep(0.1)
        logger.info("memcached pid %s on CPUs %s, port %s",
                    self.memcached_process.pid, self.cpus or "all", self.port)

    def _start_mutilate(self) -> None:
        stale = self._ssh("pgrep -x mutilate").stdout.split()
        if stale:
            raise RuntimeError(
                f"mutilate is already running on {self.client} (pids {stale}); "
                f"its load would add to this run's. Kill it and re-run."
            )
        preload = self._ssh(self._remote_command(["--loadonly"]), timeout=900)
        if preload.returncode != 0:
            raise RuntimeError(f"mutilate preload failed: {preload.stderr.strip()}")

        remote = self._remote_command([
            "--noload", "-q", str(self.qps), "-t", str(self._run_seconds()),
            "--report_interval", "1",
        ])
        cmd = self._as_user(["ssh", "-o", "BatchMode=yes",
                             "-o", "ServerAliveInterval=15", self.client, remote])
        self.mutilate_process = subprocess.Popen(
            cmd, stdout=self._open_log(self._mutilate_log, cmd),
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        logger.info("mutilate on %s offering %s QPS, log %s",
                    self.client, self.qps or "peak", self._mutilate_log)

    def pre_execute(self) -> bool:
        """Start both ends and wait until every client thread has reported twice."""
        self._start_memcached()
        self._start_mutilate()

        deadline = time.time() + 120
        seen: Dict[int, int] = {}
        while time.time() < deadline:
            self._check_alive("warm-up")
            for line in self._advance():
                seen[line.thread] = seen.get(line.thread, 0) + 1
            if seen and min(seen.values()) >= 2 and max(seen.values()) >= 3:
                logger.info("mutilate is reporting from %s threads", len(seen))
                return True
            time.sleep(0.5)
        raise RuntimeError(f"mutilate produced no interval reports within 120s. "
                           f"See {self._mutilate_log}")

    def get_target_pid(self):
        if self.memcached_process and self.memcached_process.poll() is None:
            return self.memcached_process.pid
        return None

    def cleanup(self) -> None:
        for proc in (self.mutilate_process, self.memcached_process):
            if proc and proc.poll() is None:
                self._signal_group(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self._signal_group(proc, signal.SIGKILL)
        if self.mutilate_process is not None:
            try:
                self._ssh("pkill -x mutilate", timeout=30)
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning("Could not stop mutilate on %s: %s", self.client, exc)
        for handle in self._handles:
            handle.close()
        self._handles = []

    @staticmethod
    def _signal_group(proc, sig) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(proc.pid, sig)
            except ProcessLookupError:
                pass

    # ----------------------------------------------------------------- window

    def _check_alive(self, when: str) -> None:
        for name, proc, log in (("memcached", self.memcached_process, self._memcached_log),
                                ("mutilate", self.mutilate_process, self._mutilate_log)):
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"{name} exited during {when} with return code "
                                   f"{proc.returncode}. See {log}")

    def _advance(self) -> List[IntervalLine]:
        """Parse the complete lines appended to the log since the last call."""
        try:
            with open(self._mutilate_log, encoding="utf-8", errors="replace") as handle:
                handle.seek(self._read_pos)
                chunk = handle.read()
                self._read_pos = handle.tell()
        except FileNotFoundError:
            return []
        text = self._partial + chunk
        lines = text.split("\n")
        self._partial = lines.pop()
        parsed = []
        for raw in lines:
            line = IntervalLine.parse(raw)
            if line is not None:
                self._latest[line.thread] = line
                self._window_lines.append(line.raw)
                parsed.append(line)
        return parsed

    def _memcached_cpu_ticks(self) -> Optional[int]:
        pid = self.get_target_pid()
        if pid is None:
            return None
        try:
            with open(f"/proc/{pid}/stat") as handle:
                fields = handle.read().rsplit(")", 1)[1].split()
            return int(fields[11]) + int(fields[12])
        except (OSError, IndexError, ValueError):
            return None

    def execute_window(self, window_number: int, duration: int) -> BenchmarkMetrics:
        self._check_alive(f"window {window_number}")
        window_dir = os.path.join(self.window_output_dir, f"window_{window_number}")
        os.makedirs(window_dir, exist_ok=True)

        self._advance()
        start = dict(self._latest)
        self._window_lines = []
        ticks_start, t_start = self._memcached_cpu_ticks(), time.time()
        window_start_time = self.start_system_measurement(window_number, duration)
        perf_info = self.collect_perf_metrics(window_number, duration)

        deadline = time.time() + duration
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            self._check_alive(f"window {window_number}")
            time.sleep(min(0.25, remaining))
        window_end_time = time.time()

        self.finalize_perf_metrics(window_number, perf_info)
        self._advance()
        end = dict(self._latest)
        ticks_end, t_end = self._memcached_cpu_ticks(), time.time()

        with open(os.path.join(window_dir, WINDOW_FILE), "w", encoding="utf-8") as handle:
            baseline = [line.raw for line in start.values()]
            handle.write("\n".join(baseline + self._window_lines) + "\n")

        metrics = self.metrics_from(window_stats(start, end))
        if ticks_start is not None and ticks_end is not None:
            metrics.extra_metrics["memcached_cpu_cores"] = (
                (ticks_end - ticks_start) / os.sysconf("SC_CLK_TCK") / (t_end - t_start)
            )
        metrics.extra_metrics["continuous_log_file"] = self._mutilate_log
        self._populate_system_metrics(metrics, window_number, window_start_time, window_end_time)
        logger.info(
            "memcached window %s: %.0f QPS (offered %s), p50 %.1fus p99 %.1fus",
            window_number, metrics.throughput, self.qps or "peak",
            metrics.extra_metrics["latency_p50"], metrics.extra_metrics["latency_p99"],
        )
        return metrics

    def metrics_from(self, stats: Dict[str, float]) -> BenchmarkMetrics:
        if not stats["requests"]:
            raise RuntimeError(f"No mutilate requests completed in the window. "
                               f"See {self._mutilate_log}")
        metrics = BenchmarkMetrics()
        metrics.throughput = stats["achieved_qps"]
        metrics.goodput = stats["achieved_qps"] * (1 - stats["miss_ratio"])
        metrics.latency_avg = stats["latency_avg"]
        metrics.latency_p95 = stats["latency_p95"]
        metrics.extra_metrics.update({
            "latency_p50": stats["latency_p50"],
            "latency_p99": stats["latency_p99"],
            "latency_p999": stats["latency_p999"],
            "offered_qps": self.qps,
            "qps_ratio": stats["achieved_qps"] / self.qps if self.qps else 1.0,
            "miss_ratio": stats["miss_ratio"],
            "mutilate_threads": stats["threads"],
            "requests": stats["requests"],
        })
        return metrics

    def parse_results(self, output_dir: str) -> BenchmarkMetrics:
        """Re-score a window from its saved lines, which open with each thread's baseline."""
        path = os.path.join(output_dir, WINDOW_FILE)
        first: Dict[int, IntervalLine] = {}
        last: Dict[int, IntervalLine] = {}
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                line = IntervalLine.parse(raw)
                if line is not None:
                    first.setdefault(line.thread, line)
                    last[line.thread] = line
        return self.metrics_from(window_stats(first, last))
