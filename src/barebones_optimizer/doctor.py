#!/usr/bin/env python3
"""Host prerequisite checks for reproducible v1 runs."""

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def _run(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    except Exception as exc:
        return False, str(exc)
    output = (result.stdout or result.stderr).strip()
    return result.returncode == 0, output


def _check_binary(name: str, version_args: list[str] | None = None) -> tuple[bool, str]:
    path = shutil.which(name)
    if not path:
        return False, "not found"
    if not version_args:
        return True, path
    ok, version = _run(version_args)
    return ok, version.splitlines()[0] if version else path


def _parse_java_major_version(version_text: str) -> int | None:
    match = re.search(r'version "([^"]+)"', version_text)
    if not match:
        return None
    parts = match.group(1).split(".")
    if not parts:
        return None
    if parts[0] == "1" and len(parts) > 1:
        return int(parts[1]) if parts[1].isdigit() else None
    return int(parts[0]) if parts[0].isdigit() else None


def _check_java_21() -> tuple[bool, str]:
    path = shutil.which("java")
    if not path:
        return False, "not found; install with sudo apt-get install -y openjdk-21-jdk"
    ok, version = _run(["java", "-version"])
    first_line = version.splitlines()[0] if version else path
    major = _parse_java_major_version(version)
    if not ok or major is None:
        return False, first_line
    if major < 21:
        return False, f"{first_line}; install with sudo apt-get install -y openjdk-21-jdk"
    return True, first_line


def collect_checks() -> list[tuple[str, bool, str]]:
    checks = []
    checks.append(("OS", platform.system() == "Linux", platform.platform()))
    checks.append(("Python >= 3.10", tuple(map(int, platform.python_version_tuple()[:2])) >= (3, 10), platform.python_version()))

    for name, version_args in [
        ("git", ["git", "--version"]),
        ("sysbench", ["sysbench", "--version"]),
        ("psql", ["psql", "--version"]),
        ("perf", ["perf", "--version"]),
    ]:
        ok, detail = _check_binary(name, version_args)
        checks.append((name, ok, detail))
    java_ok, java_detail = _check_java_21()
    checks.append(("Java >= 21", java_ok, java_detail))

    checks.append(("sudo available", shutil.which("sudo") is not None, shutil.which("sudo") or "not found"))
    checks.append(("/proc/sys writable via sudo", os.geteuid() == 0 or shutil.which("sudo") is not None, "requires root or sudo"))

    rapl = Path("/sys/class/powercap")
    checks.append(("RAPL powercap present", rapl.exists(), str(rapl)))

    benchbase_jar = Path("deps/benchbase/target/benchbase-postgres/benchbase.jar")
    checks.append(("BenchBase jar", benchbase_jar.exists(), str(benchbase_jar)))
    return checks


def run_doctor() -> int:
    checks = collect_checks()
    failed = False
    for name, ok, detail in checks:
        status = "OK" if ok else "MISSING"
        print(f"{status:8} {name}: {detail}")
        failed = failed or not ok

    if failed:
        print("\nDoctor found missing prerequisites. See docs/installation.md for setup steps.")
        return 1
    print("\nDoctor checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_doctor())
