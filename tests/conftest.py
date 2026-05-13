import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-host-mutation",
        action="store_true",
        default=False,
        help="run tests that require root/sudo and mutate host OS parameters",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-host-mutation"):
        return
    skip_host = pytest.mark.skip(reason="needs --run-host-mutation")
    for item in items:
        if "host_mutation" in item.keywords:
            item.add_marker(skip_host)
