# tests/conftest.py
import pytest
from fastmcp.client import Client

import reposense_mcp.cache as cache_mod
import reposense_mcp.server as server_mod
from reposense_mcp.cache import default_cache
from reposense_mcp.server import mcp


@pytest.fixture
async def mcp_client():
    async with Client(transport=mcp) as client:
        yield client


@pytest.fixture(autouse=True)
def _clear_global_cache_between_tests():
    # hard reset cache singleton
    default_cache().clear()
    cache_mod._default_cache = None  # reset "first call wins" singleton

    # reset process-wide github clients so they don't leak across tests
    server_mod._gh_cached = None
    server_mod._gh_nocache = None

    # also clear optional override hooks
    server_mod.github_client = None
    server_mod.github_client_nocache = None

    yield

    if cache_mod._default_cache is not None:
        cache_mod._default_cache.clear()
    cache_mod._default_cache = None
