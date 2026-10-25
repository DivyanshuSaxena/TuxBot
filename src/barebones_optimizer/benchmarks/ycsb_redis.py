#!/usr/bin/env python3
"""Redis driven by YCSB from a second machine.

redis-server runs on this node for the whole session and one YCSB client on a
second node offers a fixed target load across every window. YCSB's status
thread closes an HdrHistogram interval every second and, with
hdrhistogram.fileoutput, appends it to one <OP>.hdr log per operation on the
client. The logs are fetched incrementally over ssh at each window boundary, so
a window is the sum of the interval histograms that landed inside it: exact
percentiles, as mutilate's per-thread histograms give memcached.
"""

import base64
import logging
import math
import os
import shlex
import signal
import struct
import subprocess
import time
import zlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..benchmark import BenchmarkInterface, BenchmarkMetrics
from .benchmark_registry import BenchmarkInfo, BenchmarkType

logger = logging.getLogger(__name__)

WINDOW_FILE = "ycsb_intervals.txt"
# For pgrep/pkill -f; the bracket keeps the pattern from matching the remote
# shell whose own command line carries it.
YCSB_CLIENT_PATTERN = "'[s]ite.ycsb.Client'"
# Far past any run: maxexecutiontime is what ends it. YCSB parses it as an int.
OPERATION_COUNT = 2_000_000_000

# HdrHistogram's V2 encoding (HistogramEncoding / ZigZagEncoding in the Java
# library). The low byte's high nibble carries the word size, so cookies are
# compared with it masked off.
COMPRESSED_COOKIE = 0x1C849304
ENCODING_COOKIE = 0x1C849303
COOKIE_MASK = ~0xF0
HEADER = struct.Struct(">iiiiqqd")

# (lowest, highest + 1) of one HdrHistogram bucket, in recorded units (us).
Bucket = Tuple[int, int]


def _zigzag_varints(data: bytes):
    """HdrHistogram's LEB128: 7 bits a byte for eight bytes, a full ninth."""
    pos = 0
    while pos < len(data):
        value = shift = 0
        for i in range(9):
            byte = data[pos]
            pos += 1
            if i == 8:
                value |= byte << 56
                break
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        yield (value >> 1) ^ -(value & 1)


def decode_histogram(encoded: str) -> Dict[Bucket, int]:
    """One base64 compressed histogram from a .hdr log, as bucket counts."""
    raw = base64.b64decode(encoded)
    cookie, length = struct.unpack(">ii", raw[:8])
    if cookie & COOKIE_MASK != COMPRESSED_COOKIE & COOKIE_MASK:
        raise ValueError(f"not a compressed V2 histogram (cookie {cookie:#x})")
    payload = zlib.decompress(raw[8:8 + length])
    cookie, size, offset, digits, lowest, _highest, _ratio = HEADER.unpack_from(payload)
    if cookie & COOKIE_MASK != ENCODING_COOKIE & COOKIE_MASK:
        raise ValueError(f"not a V2 histogram payload (cookie {cookie:#x})")
    if offset:
        raise ValueError("shifted histograms (normalizing index offset) are not supported")

    # The bucket layout follows from the precision and the lowest value alone.
    sub_count_mag = math.ceil(math.log2(2 * 10 ** digits))
    half_mag = max(sub_count_mag, 1) - 1
    half = 1 << half_mag
    unit_mag = int(math.floor(math.log2(lowest)))

    buckets: Dict[Bucket, int] = {}
    index = 0
    for value in _zigzag_varints(payload[HEADER.size:HEADER.size + size]):
        if value < 0:
            index -= value
            continue
        if value:
            bucket = (index >> half_mag) - 1
            sub = (index & (half - 1)) + half
            if bucket < 0:
                sub -= half
                bucket = 0
            lo = sub << (bucket + unit_mag)
            key = (lo, lo + (1 << (bucket + unit_mag)))
            buckets[key] = buckets.get(key, 0) + value
        index += 1
    return buckets


def histogram_percentile(buckets: Dict[Bucket, int], pct: float) -> float:
    """HdrHistogram's getValueAtPercentile: the highest equivalent value."""
    total = sum(buckets.values())
    if total == 0:
        return 0.0
    target = max(1, int(pct / 100.0 * total + 0.5))
    seen = 0
    for (lo, hi), count in sorted(buckets.items()):
        seen += count
        if seen >= target:
            return float(lo if pct == 0 else hi - 1)
    return float(max(hi for _, hi in buckets) - 1)


def histogram_mean(buckets: Dict[Bucket, int]) -> float:
    """HdrHistogram's getMean: each count at its bucket's median value."""
    total = sum(buckets.values())
    if total == 0:
        return 0.0
    return sum((lo + ((hi - lo) >> 1)) * n for (lo, hi), n in buckets.items()) / total


class HdrInterval:
    """One interval line of one operation's .hdr log."""

    __slots__ = ("op", "start", "length", "buckets", "raw")

    def __init__(self, op, start, length, buckets, raw=""):
        self.op = op
        self.start = start
        self.length = length
        self.buckets = buckets
        self.raw = raw

    @classmethod
    def parse(cls, op: str, line: str) -> Optional["HdrInterval"]:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith('"'):
            return None
        fields = line.split(",")
        if fields[0].startswith("Tag="):
            fields = fields[1:]
        if len(fields) != 4:
            return None
        try:
            return cls(op, float(fields[0]), float(fields[1]),
                       decode_histogram(fields[3]), line)
        except (ValueError, struct.error, zlib.error):
            return None

    @classmethod
    def parse_saved(cls, line: str) -> Optional["HdrInterval"]:
        """A window file line: the operation, a space, the .hdr line."""
        op, _, rest = line.partition(" ")
        return cls.parse(op, rest) if rest else None


def window_stats(intervals: List[HdrInterval]) -> Dict[str, float]:
    """Merge one window's interval histograms into its numbers.

    Throughput is summed per operation over that operation's own span: each
    .hdr file keeps its own clock, and an operation's intervals tile its span.
    """
    buckets: Dict[Bucket, int] = {}
    per_op: Dict[str, List[HdrInterval]] = {}
    for interval in intervals:
        per_op.setdefault(interval.op, []).append(interval)
        for key, count in interval.buckets.items():
            buckets[key] = buckets.get(key, 0) + count

    qps = 0.0
    counts: Dict[str, int] = {}
    for op, items in per_op.items():
        count = sum(sum(i.buckets.values()) for i in items)
        span = max(i.start + i.length for i in items) - min(i.start for i in items)
        counts[op] = count
        if span > 0:
            qps += count / span
    return {
        "requests": sum(counts.values()),
        "op_counts": counts,
        "achieved_qps": qps,
        "latency_avg": histogram_mean(buckets),
        "latency_p50": histogram_percentile(buckets, 50),
        "latency_p95": histogram_percentile(buckets, 95),
        "latency_p99": histogram_percentile(buckets, 99),
        "latency_p999": histogram_percentile(buckets, 99.9),
    }


class YcsbRedisBenchmark(BenchmarkInterface):
    """Redis under a fixed YCSB target load from a remote client."""

    def __init__(self, config):
        super().__init__(config)

        self.benchmark_info: BenchmarkInfo = BenchmarkType.from_string(config.benchmark).value
        get = lambda name, default: getattr(config, name, default)
        self.binary = get("redis_binary", "redis-server")
        self.cpus = get("redis_cpus", None)
        self.io_threads = get("redis_io_threads", 8)
        self.port = get("redis_port", 6379)
        self.client = get("ycsb_client_host", "node1")
        self.ycsb_home = get("ycsb_home", "~/YCSB")
        self.server_ip = get("ycsb_server_ip", "10.10.1.1")
        self.workload = get("ycsb_workload", "~/workloads/ycsb/workloada")
        self.target = get("ycsb_target", 0)
        self.target_after = get("ycsb_target_after", None)
        self.switch_window = get("load_switch_window", None)
        self.threads = get("ycsb_threads", 64)
        self.load_threads = get("ycsb_load_threads", 16)
        self.records = get("ycsb_records", 1000000)
        self.properties = dict(get("ycsb_properties", None) or {})
        self.hdr_dir = get("ycsb_hdr_dir", "/tmp/ycsb_hdr")

        self.window_output_dir = os.path.join(
            self.results_dir, f"{self.benchmark_info.name}_windows"
        )
        os.makedirs(self.window_output_dir, exist_ok=True)
        self._ycsb_log = os.path.join(self.window_output_dir, "continuous_ycsb.log")
        self._hdr_log = os.path.join(self.window_output_dir, "ycsb_hdr.log")
        self._redis_log = os.path.join(self.window_output_dir, "redis.log")

        self.redis_process = None
        self.ycsb_process = None
        self._handles = []
        self._hdr_handle = None
        # Bytes of each remote .hdr file already consumed, complete lines only.
        self._offsets: Dict[str, int] = {}

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

    @staticmethod
    def _quote(arg: str) -> str:
        """Quote for the client's shell, leaving a leading ~/ to expand there."""
        if arg.startswith("~/"):
            return "~/" + shlex.quote(arg[2:])
        return shlex.quote(arg)

    def _ycsb_command(self, phase: str, extra: Dict[str, object], threads: int,
                      tail: List[str] = ()) -> str:
        props = {
            "redis.host": self.server_ip,
            "redis.port": self.port,
            "recordcount": self.records,
            **self.properties,
            **extra,
        }
        args = ["./bin/ycsb", phase, "redis", "-s", "-P", self.workload]
        for key, value in props.items():
            args += ["-p", f"{key}={value}"]
        args += ["-threads", str(threads), *tail]
        return f"cd {self._quote(self.ycsb_home)} && " + " ".join(self._quote(a) for a in args)

    def _run_seconds(self) -> int:
        """Long enough to outlast every window, as db_bench's continuous run is."""
        windows = getattr(self.config, "total_windows", None) or (
            getattr(self.config, "max_iterations", 1)
            + getattr(self.config, "post_tuning_windows", 0)
        )
        per_window = (
            getattr(self.config, "window_duration", 1)
            + getattr(self.config, "settle_seconds", 0)
            + 60
        )
        return windows * per_window + 300

    def _redis_command(self) -> List[str]:
        # Persistence off: a background save would fork a copy of the dataset
        # mid-window and measure that instead of the knobs.
        cmd = [self.binary, "--port", str(self.port), "--bind", "0.0.0.0",
               "--protected-mode", "no", "--save", "", "--appendonly", "no",
               "--daemonize", "no"]
        if self.io_threads > 1:
            cmd += ["--io-threads", str(self.io_threads), "--io-threads-do-reads", "yes"]
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

    def _start_redis(self) -> None:
        if self._port_in_use():
            raise RuntimeError(
                f"Port {self.port} is already listening. A leftover redis-server "
                f"(or the packaged service) would be measured in place of this "
                f"one; stop it and re-run."
            )
        cmd = self._redis_command()
        self.redis_process = subprocess.Popen(
            cmd, stdout=self._open_log(self._redis_log, cmd),
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        deadline = time.time() + 10
        while not self._port_in_use():
            if self.redis_process.poll() is not None or time.time() > deadline:
                raise RuntimeError(f"redis-server did not start. See {self._redis_log}")
            time.sleep(0.1)
        logger.info("redis-server pid %s on CPUs %s, %s I/O threads, port %s",
                    self.redis_process.pid, self.cpus or "all", self.io_threads, self.port)

    def _load(self) -> None:
        """Fill the fresh server, and refuse to run on a partial key space."""
        cmd = self._ycsb_command("load", {}, self.load_threads)
        loaded = self._ssh(cmd, timeout=3600)
        out = loaded.stdout + loaded.stderr
        with open(os.path.join(self.window_output_dir, "ycsb_load.log"), "w",
                  encoding="utf-8") as handle:
            handle.write(out)
        ok = 0
        for line in out.splitlines():
            if line.startswith("[INSERT], Return=OK,"):
                ok = int(line.rsplit(",", 1)[1])
        if loaded.returncode != 0 or ok < self.records:
            raise RuntimeError(
                f"YCSB load inserted {ok} of {self.records} records "
                f"(exit {loaded.returncode}). See ycsb_load.log in {self.window_output_dir}")
        logger.info("YCSB loaded %s records into %s:%s", ok, self.server_ip, self.port)

    def _start_ycsb(self) -> None:
        stale = self._ssh(f"pgrep -f {YCSB_CLIENT_PATTERN}").stdout.split()
        if stale:
            raise RuntimeError(
                f"A YCSB client is already running on {self.client} (pids {stale}); "
                f"its load would add to this run's. Kill it and re-run."
            )
        tail = ["-target", str(self.target)] if self.target else []
        run = self._ycsb_command("run", {
            "operationcount": OPERATION_COUNT,
            "maxexecutiontime": self._run_seconds(),
            "status.interval": 1,
            "measurementtype": "hdrhistogram",
            "hdrhistogram.fileoutput": "true",
            "hdrhistogram.output.path": self.hdr_dir.rstrip("/") + "/",
        }, self.threads, tail)
        # Emptied before the launch, not by it: a fetch racing an asynchronous
        # rm would consume the last run's files and hold offsets past the end
        # of the new ones.
        hdr = shlex.quote(self.hdr_dir)
        cleared = self._ssh(f"rm -rf {hdr} && mkdir -p {hdr}", timeout=30)
        if cleared.returncode != 0:
            raise RuntimeError(f"Could not empty {self.hdr_dir} on {self.client}: "
                               f"{cleared.stderr.strip()}")
        self._offsets = {}
        cmd = self._as_user(["ssh", "-o", "BatchMode=yes",
                             "-o", "ServerAliveInterval=15", self.client, run])
        self.ycsb_process = subprocess.Popen(
            cmd, stdout=self._open_log(self._ycsb_log, cmd),
            stderr=subprocess.STDOUT, start_new_session=True,
        )
        logger.info("YCSB on %s offering %s ops/s with %s threads, log %s",
                    self.client, self.target or "peak", self.threads, self._ycsb_log)

    def pre_execute(self) -> bool:
        """Start both ends, load, and wait until every operation has reported twice."""
        self._start_redis()
        self._load()
        self._hdr_handle = open(self._hdr_log, "a", encoding="utf-8", buffering=1)
        self._handles.append(self._hdr_handle)
        self._start_ycsb()
        self._await_intervals("warm-up")
        return True

    def _await_intervals(self, when: str) -> None:
        deadline = time.time() + 180
        seen: Dict[str, int] = {}
        while time.time() < deadline:
            self._check_alive(when)
            for interval in self._fetch():
                seen[interval.op] = seen.get(interval.op, 0) + 1
            if seen and min(seen.values()) >= 2:
                logger.info("YCSB is reporting %s", ", ".join(sorted(seen)))
                return
            time.sleep(1.0)
        raise RuntimeError(f"YCSB wrote no interval histograms within 180s of {when}. "
                           f"See {self._ycsb_log}")

    def update_workload(self, iteration: int) -> None:
        """Step the target load at load_switch_window.

        YCSB takes -target once, at launch, so the step is a restart of the
        client at the window boundary against the same loaded server. The new
        run starts its .hdr files afresh, so the old run's unread intervals,
        which fell between windows, are dropped with them.
        """
        if self.switch_window is None or iteration != self.switch_window:
            return
        logger.info("Load step before window %s: %s -> %s ops/s",
                    iteration, self.target or "peak", self.target_after or "peak")
        self._stop_ycsb()
        self.target = self.target_after
        self._start_ycsb()
        self._await_intervals(f"the load step to {self.target or 'peak'} ops/s")
        seconds = getattr(self.config, "settle_seconds", 0)
        if seconds > 0:
            logger.info("Settling %ss after the load step", seconds)
            time.sleep(seconds)

    def get_target_pid(self):
        if self.redis_process and self.redis_process.poll() is None:
            return self.redis_process.pid
        return None

    @classmethod
    def _stop_process(cls, proc) -> None:
        if proc and proc.poll() is None:
            cls._signal_group(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                cls._signal_group(proc, signal.SIGKILL)

    def _stop_ycsb(self) -> None:
        """Stop the local ssh and the remote JVM it ran, which survives it."""
        self._stop_process(self.ycsb_process)
        if self.ycsb_process is None:
            return
        try:
            self._ssh(f"pkill -f {YCSB_CLIENT_PATTERN}", timeout=30)
            deadline = time.time() + 15
            while (time.time() < deadline
                   and self._ssh(f"pgrep -f {YCSB_CLIENT_PATTERN}").stdout.strip()):
                time.sleep(0.5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Could not stop YCSB on %s: %s", self.client, exc)

    def cleanup(self) -> None:
        self._stop_ycsb()
        self._stop_process(self.redis_process)
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
        for name, proc, log in (("redis-server", self.redis_process, self._redis_log),
                                ("YCSB", self.ycsb_process, self._ycsb_log)):
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"{name} exited during {when} with return code "
                                   f"{proc.returncode}. See {log}")

    def _fetch_script(self) -> str:
        cases = "".join(f"{shlex.quote(name)}) o={offset};; "
                        for name, offset in self._offsets.items())
        return (
            f"cd {shlex.quote(self.hdr_dir)} 2>/dev/null || exit 0; "
            f"for f in *.hdr; do [ -e \"$f\" ] || continue; "
            f"case \"$f\" in {cases}*) o=0;; esac; "
            f"[ \"$(stat -c %s \"$f\")\" -lt \"$o\" ] && o=0; "
            f"printf '@@BEGIN %s %s\\n' \"$f\" \"$o\"; tail -c +$((o+1)) \"$f\"; printf '\\n@@END\\n'; "
            f"done"
        )

    def _consume(self, output: str) -> List[HdrInterval]:
        """Parse a fetch, advancing each file's offset past its complete lines.

        Each file's section names the offset it was read from, which is the
        recorded one unless the file had shrunk below it and was read whole.
        """
        parsed = []
        for chunk in output.split("@@BEGIN ")[1:]:
            header, _, rest = chunk.partition("\n")
            name, _, start = header.rpartition(" ")
            start = int(start)
            end = rest.rfind("\n@@END")
            if end < 0:
                continue
            content = rest[:end]
            complete = content[:content.rfind("\n") + 1]
            self._offsets[name] = start + len(complete.encode())
            op = name[:-len(".hdr")]
            for raw in complete.splitlines():
                interval = HdrInterval.parse(op, raw)
                if interval is not None:
                    if self._hdr_handle is not None:
                        self._hdr_handle.write(f"{op} {interval.raw}\n")
                    parsed.append(interval)
        return parsed

    def _fetch(self) -> List[HdrInterval]:
        """Every interval the client has written since the last fetch.

        A failed fetch leaves the offsets alone, so the next one picks the
        missed lines up rather than losing them.
        """
        try:
            result = self._ssh(self._fetch_script(), timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("Fetching YCSB's histograms from %s timed out", self.client)
            return []
        if result.returncode != 0:
            logger.warning("Fetching YCSB's histograms failed: %s", result.stderr.strip())
            return []
        return self._consume(result.stdout)

    def _redis_cpu_ticks(self) -> Optional[int]:
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

        # Whatever landed before the window opened belongs to the settle period.
        self._fetch()
        ticks_start, t_start = self._redis_cpu_ticks(), time.time()
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
        intervals = self._fetch()
        ticks_end, t_end = self._redis_cpu_ticks(), time.time()

        with open(os.path.join(window_dir, WINDOW_FILE), "w", encoding="utf-8") as handle:
            handle.write("".join(f"{i.op} {i.raw}\n" for i in intervals))

        metrics = self.metrics_from(window_stats(intervals))
        if ticks_start is not None and ticks_end is not None:
            metrics.extra_metrics["redis_cpu_cores"] = (
                (ticks_end - ticks_start) / os.sysconf("SC_CLK_TCK") / (t_end - t_start)
            )
        metrics.extra_metrics["continuous_log_file"] = self._ycsb_log
        self._populate_system_metrics(metrics, window_number, window_start_time, window_end_time)
        logger.info(
            "redis window %s: %.0f ops/s (offered %s), p50 %.0fus p95 %.0fus p99 %.0fus",
            window_number, metrics.throughput, self.target or "peak",
            metrics.extra_metrics["latency_p50"], metrics.latency_p95,
            metrics.extra_metrics["latency_p99"],
        )
        return metrics

    def metrics_from(self, stats: Dict[str, float]) -> BenchmarkMetrics:
        if not stats["requests"]:
            raise RuntimeError(f"No YCSB operations completed in the window. "
                               f"See {self._ycsb_log}")
        metrics = BenchmarkMetrics()
        metrics.throughput = stats["achieved_qps"]
        metrics.goodput = stats["achieved_qps"]
        metrics.latency_avg = stats["latency_avg"]
        metrics.latency_p95 = stats["latency_p95"]
        metrics.extra_metrics.update({
            "latency_p50": stats["latency_p50"],
            "latency_p99": stats["latency_p99"],
            "latency_p999": stats["latency_p999"],
            "offered_qps": self.target,
            "qps_ratio": stats["achieved_qps"] / self.target if self.target else 1.0,
            "requests": stats["requests"],
            **{f"ops_{op.lower()}": n for op, n in stats["op_counts"].items()},
        })
        return metrics

    def parse_results(self, output_dir: str) -> BenchmarkMetrics:
        """Re-score a window from its saved interval lines."""
        intervals = []
        with open(os.path.join(output_dir, WINDOW_FILE), encoding="utf-8") as handle:
            for raw in handle:
                interval = HdrInterval.parse_saved(raw)
                if interval is not None:
                    intervals.append(interval)
        return self.metrics_from(window_stats(intervals))
