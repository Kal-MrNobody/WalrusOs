"""
Sui Testnet Integration Tests.

Tests real pysui wallet loading and PTB construction.
Skipped unless SUI_INTEGRATION=1 and a configured Sui wallet exists.

Usage:
    SUI_INTEGRATION=1 pytest tests/integration/test_sui.py -v

Note:
    PTB execution tests require a deployed Move package (package_id in config).
    Wallet loading tests work with any configured Sui wallet.
"""
from __future__ import annotations

import os
import pytest

SUI_INTEGRATION = os.environ.get("SUI_INTEGRATION", "").lower() in ("1", "true")
pytestmark = pytest.mark.skipif(
    not SUI_INTEGRATION,
    reason="Set SUI_INTEGRATION=1 to run against real Sui testnet",
)


@pytest.fixture
def identity():
    from walrusos.adapters.sui import SuiIdentityAdapter
    return SuiIdentityAdapter(
        rpc_url="https://fullnode.testnet.sui.io:443"
    )


def test_identity_adapter_loads(identity):
    """SuiIdentityAdapter initialises without raising."""
    from walrusos.adapters.sui import SuiIdentityAdapter
    adapter = SuiIdentityAdapter()
    # Should not raise
    assert isinstance(adapter.is_connected, bool)
    assert isinstance(adapter.active_address, str)


def test_wallet_detection(identity):
    """
    If pysui is configured, active_address should be a valid Sui address.
    """
    if not identity.is_connected:
        pytest.skip("No pysui wallet configured — skipping wallet detection test")

    addr = identity.active_address
    assert addr.startswith("0x"), f"Expected 0x prefix, got: {addr}"
    assert len(addr) == 66, f"Expected 66-char address, got: {len(addr)}"


def test_login_returns_address(identity):
    """login() returns the active address string."""
    if not identity.is_connected:
        pytest.skip("No pysui wallet configured")

    address = identity.login()
    assert address.startswith("0x")


@pytest.mark.asyncio
async def test_create_workspace_ptb(identity):
    """
    Execute create_workspace PTB on Sui testnet.
    Requires: deployed package_id in config.
    """
    if not identity.is_connected:
        pytest.skip("No pysui wallet configured")

    from walrusos.config import load_config
    cfg = load_config()
    if not cfg.package_id or cfg.package_id == "0x0":
        pytest.skip("WALRUSOS_PACKAGE_ID not set — deploy with: python scripts/deploy_walrusos.py")

    obj_id = await identity.create_workspace("integration-test-ws", cfg.package_id)
    assert obj_id.startswith("0x"), f"Expected Sui object ID, got: {obj_id}"


@pytest.mark.asyncio
async def test_sui_ledger_adapter_create_stream():
    """
    SuiLedgerAdapter.create_stream stores a record in SQLite and
    (if package available) creates a Sui MemoryStream object.
    """
    import uuid
    import tempfile
    import os
    from walrusos.adapters.sui import SuiIdentityAdapter, SuiLedgerAdapter

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        identity = SuiIdentityAdapter()
        ledger   = SuiLedgerAdapter(
            identity   = identity,
            package_id = None,  # SQLite-only mode
            db_path    = db_path,
        )

        agent_id  = uuid.uuid4()
        stream_id = await ledger.create_stream(agent_id)
        assert isinstance(stream_id, uuid.UUID)

        # Head should be None (no events yet)
        head = await ledger.get_head(stream_id)
        assert head is None


@pytest.mark.asyncio
async def test_sui_ledger_append_and_retrieve():
    """SuiLedgerAdapter persists events to SQLite correctly."""
    import uuid
    import tempfile
    import os
    from walrusos.adapters.sui import SuiIdentityAdapter, SuiLedgerAdapter
    from walrusos.core.models.memory import MemoryEvent

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path  = os.path.join(tmpdir, "test.db")
        identity = SuiIdentityAdapter()
        ledger   = SuiLedgerAdapter(
            identity   = identity,
            package_id = None,
            db_path    = db_path,
        )

        stream_id = await ledger.create_stream(uuid.uuid4())
        event = MemoryEvent(
            id=               "abcdef123456",
            stream_id=        stream_id,
            parent_id=        "genesis",
            epoch=            1,
            memory_type=       "semantic",
            content_blob_id=  "walrus_blob_42",
        )
        await ledger.append_event(stream_id, event)

        retrieved = await ledger.get_event("abcdef123456")
        assert retrieved is not None
        assert retrieved.content_blob_id == "walrus_blob_42"

        head = await ledger.get_head(stream_id)
        assert head == "abcdef123456"

        events = await ledger.list_events(stream_id)
        assert len(events) == 1
        assert events[0].epoch == 1


@pytest.mark.asyncio
async def test_sqlite_ledger_epoch_persists_across_restarts():
    """
    Epoch counter in SQLiteLedger survives process restarts
    (simulated by creating two separate SQLiteLedger instances on same DB).
    """
    import uuid
    import tempfile
    import os
    from walrusos.adapters.sqlite_ledger import SQLiteLedger
    from walrusos.core.models.memory import MemoryEvent

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path   = os.path.join(tmpdir, "test.db")
        agent_id  = uuid.uuid4()

        # First instance
        ledger1   = SQLiteLedger(db_path)
        stream_id = await ledger1.create_stream(agent_id)

        for i in range(1, 4):
            ev = MemoryEvent(
                id=              f"event_{i}",
                stream_id=       stream_id,
                parent_id=       f"event_{i-1}" if i > 1 else "genesis",
                epoch=           i,
                memory_type=      "episodic",
                content_blob_id= f"blob_{i}",
            )
            await ledger1.append_event(stream_id, ev)

        # Simulate restart — new instance, same DB
        ledger2 = SQLiteLedger(db_path)
        epoch   = await ledger2.get_epoch_counter(stream_id)
        assert epoch == 3, f"Expected epoch=3 after restart, got {epoch}"

        events = await ledger2.list_events(stream_id)
        assert len(events) == 3
        assert events[-1].epoch == 3
