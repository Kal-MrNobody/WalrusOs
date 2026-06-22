"""
Global test configuration for WalrusOS.

Sets WALRUSOS_USE_MOCKS=1 for the entire unit test suite so that
WalrusOS() uses InMemory adapters (no network, no SQLite, no pysui).

Integration tests override this by reading WALRUS_INTEGRATION=1 /
SUI_INTEGRATION=1 from the environment.
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

import pytest

# ── Force mock mode for all unit tests ───────────────────────────────────────
# This ensures `WalrusOS()` (default use_mocks=False) still uses InMemory
# adapters in the test suite. Integration tests set their own env vars.
os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")


# ── Event loop ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Shared event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Mock WalrusOS client fixture ─────────────────────────────────────────────
@pytest.fixture
async def mock_client() -> AsyncGenerator[None, None]:
    """Yields nothing — placeholder for tests that need a live client."""
    yield
