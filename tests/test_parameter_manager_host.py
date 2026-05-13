import os
import subprocess

import pytest

from barebones_optimizer.parameter_manager import ParameterManager


pytestmark = pytest.mark.host_mutation


def test_can_read_latency_with_host_permissions():
    if os.geteuid() != 0:
        result = subprocess.run(["sudo", "-n", "true"], capture_output=True, check=False)
        if result.returncode != 0:
            pytest.skip("requires root or passwordless sudo")

    manager = ParameterManager()
    value = manager.get_parameter("latency_ns")
    assert value is None or isinstance(value, int)
