import os

import pytest
from lock_util import acquire_lock, release_lock


def pytest_addoption(parser):
    parser.addoption(
        "--run-stress",
        action="store_true",
        default=os.getenv("RUN_STRESS_TESTS", "").strip().lower() in ("1", "true", "yes"),
        help="Run stress and performance tests that require an otherwise idle stack (or set RUN_STRESS_TESTS=1)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-stress"):
        return
    skip_stress = pytest.mark.skip(
        reason="requires an idle stack; opt in with RUN_STRESS_TESTS=1 or --run-stress"
    )
    for item in items:
        if item.get_closest_marker("stress") is not None:
            item.add_marker(skip_stress)


@pytest.fixture(scope="session", autouse=True)
def backend_test_lock():
    acquire_lock()
    yield
    release_lock()
