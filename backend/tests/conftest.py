import pytest
from lock_util import acquire_lock, release_lock


@pytest.fixture(scope="session", autouse=True)
def backend_test_lock():
    acquire_lock()
    yield
    release_lock()
