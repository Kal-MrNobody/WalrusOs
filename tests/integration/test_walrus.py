"""
Walrus Testnet Integration Tests.

These tests interact with the REAL Walrus testnet network.
They are skipped unless the WALRUS_INTEGRATION=1 environment variable is set.

Usage:
    WALRUS_INTEGRATION=1 pytest tests/integration/test_walrus.py -v

Requirements:
    - Internet access to Walrus testnet publisher/aggregator
    - No wallet required for Walrus (it uses SUI for payment but the
      testnet subsidises storage for free blobs)

What is tested:
    1. Round-trip: store_blob → retrieve_blob (compressed + encrypted)
    2. Large blob: chunked upload → reassembly
    3. blob_exists: HEAD request against the aggregator
    4. blob_metadata: cached metadata after upload
    5. shred_key: confirms blobs are unreadable after key destruction
    6. Error handling: retrieving a non-existent blob_id
"""
from __future__ import annotations

import os
import secrets
import pytest

INTEGRATION = os.environ.get("WALRUS_INTEGRATION", "").lower() in ("1", "true")
pytestmark = pytest.mark.skipif(
    not INTEGRATION,
    reason="Set WALRUS_INTEGRATION=1 to run against real Walrus testnet",
)


@pytest.fixture
def adapter():
    from walrusos.adapters.walrus import WalrusAdapter
    return WalrusAdapter(
        publisher_url  = "https://publisher.walrus-testnet.walrus.space",
        aggregator_url = "https://aggregator.walrus-testnet.walrus.space",
        epochs         = 1,  # Minimum epoch for testnet (cheaper)
    )


@pytest.mark.asyncio
async def test_roundtrip_small_blob(adapter):
    """Store a small JSON payload and retrieve it unchanged."""
    import json
    payload = json.dumps({"test": "walrus_roundtrip", "value": 42}).encode()
    blob_id = await adapter.store_blob(payload, mime_type="application/json")

    assert isinstance(blob_id, str)
    assert len(blob_id) > 0

    retrieved = await adapter.retrieve_blob(blob_id)
    parsed    = json.loads(retrieved.decode())
    assert parsed["test"]  == "walrus_roundtrip"
    assert parsed["value"] == 42


@pytest.mark.asyncio
async def test_roundtrip_binary_payload(adapter):
    """Store random binary bytes and retrieve them unchanged."""
    payload = secrets.token_bytes(1024)   # 1 KiB of random bytes
    blob_id = await adapter.store_blob(payload, mime_type="application/octet-stream")
    retrieved = await adapter.retrieve_blob(blob_id)
    assert retrieved == payload


@pytest.mark.asyncio
async def test_blob_exists_after_upload(adapter):
    """blob_exists returns True for a just-uploaded blob."""
    payload = b"exists_check"
    blob_id = await adapter.store_blob(payload)
    exists  = await adapter.blob_exists(blob_id)
    assert exists is True


@pytest.mark.asyncio
async def test_blob_exists_fake_id(adapter):
    """blob_exists returns False for a non-existent blob_id."""
    fake_id = "x" * 43  # Walrus blob_id length is ~43 chars (Base58)
    exists  = await adapter.blob_exists(fake_id)
    assert exists is False


@pytest.mark.asyncio
async def test_blob_metadata_cached(adapter):
    """blob_metadata returns locally cached metadata after upload."""
    payload = b"metadata test payload"
    blob_id = await adapter.store_blob(payload, mime_type="text/plain")
    meta    = await adapter.blob_metadata(blob_id)
    assert meta["blob_id"]   == blob_id
    assert meta["mime_type"] == "text/plain"
    assert meta["size_bytes"] == len(payload)
    assert "created_at" in meta


@pytest.mark.asyncio
async def test_retrieve_nonexistent_raises_key_error(adapter):
    """Retrieving a blob_id that doesn't exist raises KeyError."""
    with pytest.raises(KeyError, match="not found"):
        await adapter.retrieve_blob("nonexistent_blob_id_12345")


@pytest.mark.asyncio
async def test_shred_key_makes_blobs_unreadable(adapter):
    """After shred_key(), all decrypt attempts raise WalrusKeyDestroyedError."""
    from walrusos.adapters.walrus import WalrusKeyDestroyedError

    payload = b"secret data"
    blob_id = await adapter.store_blob(payload)

    adapter.shred_key()

    with pytest.raises(WalrusKeyDestroyedError):
        await adapter.retrieve_blob(blob_id)


@pytest.mark.asyncio
async def test_chunked_upload_large_blob(adapter):
    """Payloads > 4 MiB are chunked and reassembled correctly."""
    # 6 MiB payload (will be split into 2 chunks)
    payload = secrets.token_bytes(6 * 1024 * 1024)
    blob_id = await adapter.store_blob(payload, mime_type="application/octet-stream")

    assert blob_id.startswith("manifest:")  # chunked blobs use manifest prefix

    retrieved = await adapter.retrieve_blob(blob_id)
    assert retrieved == payload


@pytest.mark.asyncio
async def test_full_engine_roundtrip_on_walrus():
    """
    End-to-end test: MemoryEngine with real WalrusAdapter and InMemoryLedger.
    Verifies append → read → timeline with real Walrus storage.
    """
    import uuid
    from walrusos.adapters.walrus import WalrusAdapter
    from walrusos.adapters.in_memory import InMemoryLedger, InMemoryVector
    from walrusos.engine.memory import MemoryEngine

    engine = MemoryEngine(
        ledger  = InMemoryLedger(),
        storage = WalrusAdapter(epochs=1),
        vector  = InMemoryVector(),
    )

    agent_id  = uuid.uuid4()
    stream_id = await engine.create_stream(agent_id)

    ev1 = await engine.append(stream_id, "semantic", {
        "author": "test_agent",
        "title":  "Attention Is All You Need",
        "action": "paper_published",
    })
    ev2 = await engine.append(stream_id, "episodic", {
        "author": "test_agent",
        "action": "paper_reviewed",
        "notes":  "Transformer architecture. Revolutionary.",
    })

    # Read back individual events
    p1 = await engine.read(ev1.id)
    assert p1["title"]  == "Attention Is All You Need"

    p2 = await engine.read(ev2.id)
    assert p2["action"] == "paper_reviewed"

    # Timeline
    tl = await engine.timeline(stream_id)
    assert len(tl) == 2
    assert tl[0][1]["title"]  == "Attention Is All You Need"
    assert tl[1][1]["action"] == "paper_reviewed"

    # Semantic search
    results = await engine.semantic_search("Transformer attention mechanism")
    assert any("Attention" in r.get("content", "") for r in results)
