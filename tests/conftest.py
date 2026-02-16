# tests/conftest.py
import pytest

from reposense_mcp.cache import default_cache


@pytest.fixture(autouse=True)
def _clear_global_cache_between_tests():
    # default_cache() is a process-wide singleton, so clear it to avoid cross-test pollution.
    default_cache().clear()
    yield
    default_cache().clear()