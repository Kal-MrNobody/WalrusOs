"""
Tests for the InMemory adapters — Storage, Ledger, and Vector.
"""
from __future__ import annotations

import uuid
import pytest

from walrusos.adapters.in_memory import InMemoryStorage, InMemoryLedger, InMemoryVector
from walrusos.core.models.memory import MemoryEvent


# ── InMemoryStorage ───────────────────────────────────────────────────────────

async def test_storage_store_and_retrieve() -> None:
    s = InMemoryStorage()
    blob_id = await s.store_blob(b"hello world", "text/plain")
    assert isinstance(blob_id, str)
    raw = await s.retrieve_blob(blob_id)
    assert raw == b"hello world"


async def test_storage_content_addressed() -> None:
    """Same payload → same blob_id (content-addressed)."""
    s = InMemoryStorage()
    id1 = await s.store_blob(b"same data", "text/plain")
    id2 = await s.store_blob(b"same data", "text/plain")
    assert id1 == id2


async def test_storage_different_payloads_different_ids() -> None:
    s = InMemoryStorage()
    id1 = await s.store_blob(b"data1", "text/plain")
    id2 = await s.store_blob(b"data2", "text/plain")
    assert id1 != id2


async def test_storage_retrieve_missing_raises() -> None:
    s = InMemoryStorage()
    with pytest.raises(KeyError):
        await s.retrieve_blob("nonexistent")


async def test_storage_delete_removes_blob() -> None:
    s = InMemoryStorage()
    blob_id = await s.store_blob(b"to-delete", "text/plain")
    await s.delete_blob(blob_id)
    with pytest.raises(KeyError):
        await s.retrieve_blob(blob_id)


async def test_storage_delete_nonexistent_no_error() -> None:
    s = InMemoryStorage()
    await s.delete_blob("nonexistent")  # Should not raise


async def test_storage_metadata() -> None:
    s = InMemoryStorage()
    blob_id = await s.store_blob(b"meta test", "application/json")
    meta = await s.blob_metadata(blob_id)
    assert meta["mime_type"]  == "application/json"
    assert meta["size_bytes"] == 9
    assert "created_at" in meta


async def test_storage_metadata_missing_raises() -> None:
    s = InMemoryStorage()
    with pytest.raises(KeyError):
        await s.blob_metadata("no-such-blob")


# ── InMemoryLedger ────────────────────────────────────────────────────────────

def _make_event(stream_id: uuid.UUID, parent: str = "genesis", epoch: int = 1) -> MemoryEvent:
    return MemoryEvent(
        id=str(uuid.uuid4()),
        stream_id=stream_id,
        parent_id=parent,
        epoch=epoch,
        class_type="working",          # internal wire field — use memory_type= in the SDK
        content_blob_id="blob-" + str(uuid.uuid4()),
    )


async def test_ledger_create_stream() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    assert isinstance(sid, uuid.UUID)


async def test_ledger_get_head_empty() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    head   = await ledger.get_head(sid)
    assert head is None


async def test_ledger_append_and_get_head() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    event  = _make_event(sid)
    await ledger.append_event(sid, event)
    head = await ledger.get_head(sid)
    assert head == event.id


async def test_ledger_append_advances_head() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    e1     = _make_event(sid, "genesis", 1)
    e2     = _make_event(sid, e1.id,    2)
    await ledger.append_event(sid, e1)
    await ledger.append_event(sid, e2)
    head = await ledger.get_head(sid)
    assert head == e2.id


async def test_ledger_list_events_order() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    e1     = _make_event(sid, "genesis", 1)
    e2     = _make_event(sid, e1.id,    2)
    e3     = _make_event(sid, e2.id,    3)
    for e in (e1, e2, e3):
        await ledger.append_event(sid, e)
    events = await ledger.list_events(sid)
    assert [ev.id for ev in events] == [e1.id, e2.id, e3.id]


async def test_ledger_get_event() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    event  = _make_event(sid)
    await ledger.append_event(sid, event)
    fetched = await ledger.get_event(event.id)
    assert fetched is not None
    assert fetched.id == event.id


async def test_ledger_get_event_missing() -> None:
    ledger = InMemoryLedger()
    assert await ledger.get_event("no-such-id") is None


async def test_ledger_delete_stream() -> None:
    ledger = InMemoryLedger()
    sid    = await ledger.create_stream(uuid.uuid4())
    event  = _make_event(sid)
    await ledger.append_event(sid, event)
    await ledger.delete_stream(sid)
    events = await ledger.list_events(sid)
    assert events == []
    assert await ledger.get_event(event.id) is None


# ── InMemoryVector ────────────────────────────────────────────────────────────

async def test_vector_search_empty() -> None:
    v = InMemoryVector()
    assert await v.search("anything") == []


async def test_vector_upsert_and_search() -> None:
    v = InMemoryVector()
    await v.upsert("doc1", "machine learning neural network", {})
    await v.upsert("doc2", "blockchain decentralized storage", {})
    await v.upsert("doc3", "transformer attention mechanism", {})

    results = await v.search("deep learning neural network")
    assert len(results) > 0
    assert results[0]["doc_id"] == "doc1"
    assert results[0]["score"]  > 0


async def test_vector_search_limit() -> None:
    v = InMemoryVector()
    for i in range(10):
        await v.upsert(f"doc{i}", f"topic {i} data information", {})
    results = await v.search("topic data", limit=3)
    assert len(results) <= 3


async def test_vector_search_scores_descending() -> None:
    v = InMemoryVector()
    await v.upsert("a", "cat dog bird animal pet", {})
    await v.upsert("b", "car truck vehicle road transport", {})
    results = await v.search("cat bird pet animal", limit=5)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


async def test_vector_delete_removes_from_index() -> None:
    v = InMemoryVector()
    await v.upsert("doc1", "unique special keyword", {})
    results_before = await v.search("unique special keyword")
    assert any(r["doc_id"] == "doc1" for r in results_before)

    await v.delete("doc1")
    results_after = await v.search("unique special keyword")
    assert not any(r["doc_id"] == "doc1" for r in results_after)


async def test_vector_upsert_idempotent() -> None:
    """Re-indexing the same doc_id should update, not duplicate."""
    v = InMemoryVector()
    await v.upsert("doc1", "original text content", {})
    await v.upsert("doc1", "updated text content new",  {})
    # Only one entry in the index
    assert len(v._index) == 1
    assert "updated" in v._index["doc1"]["text"]


async def test_vector_metadata_preserved() -> None:
    v = InMemoryVector()
    await v.upsert("doc1", "metadata test", {"stream_id": "abc", "epoch": 3})
    results = await v.search("metadata test")
    assert results[0]["metadata"]["epoch"] == 3
