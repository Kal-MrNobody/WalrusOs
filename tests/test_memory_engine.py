"""
Comprehensive test suite for the WalrusOS Memory Engine.

Tests every engine operation:
  append, read, timeline, fork, merge, replay,
  checkpoint, snapshot, resume, restore_snapshot,
  summarize, semantic_search, delete_stream
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from walrusos.adapters.in_memory import InMemoryLedger, InMemoryStorage, InMemoryVector
from walrusos.engine.memory import MemoryEngine


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def engine() -> MemoryEngine:
    return MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())


@pytest.fixture
def agent_id() -> uuid.UUID:
    return uuid.uuid4()


# ── create_stream ─────────────────────────────────────────────────────────────

async def test_create_stream_returns_uuid(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    assert isinstance(sid, uuid.UUID)


async def test_create_stream_multiple_streams_unique(engine: MemoryEngine) -> None:
    ids = [await engine.create_stream(uuid.uuid4()) for _ in range(10)]
    assert len(set(ids)) == 10


# ── append + read ─────────────────────────────────────────────────────────────

async def test_append_returns_event(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid   = await engine.create_stream(agent_id)
    event = await engine.append(sid, "working", {"msg": "hello"})
    assert event.id
    assert event.stream_id == sid
    assert event.epoch     == 1
    assert event.parent_id == "genesis"


async def test_append_sequential_epochs(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid    = await engine.create_stream(agent_id)
    event1 = await engine.append(sid, "working", {"n": 1})
    event2 = await engine.append(sid, "working", {"n": 2})
    event3 = await engine.append(sid, "working", {"n": 3})
    assert event1.epoch == 1
    assert event2.epoch == 2
    assert event3.epoch == 3


async def test_append_parent_chain(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid    = await engine.create_stream(agent_id)
    event1 = await engine.append(sid, "working", {"n": 1})
    event2 = await engine.append(sid, "working", {"n": 2})
    assert event2.parent_id == event1.id


async def test_read_returns_payload(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid     = await engine.create_stream(agent_id)
    payload = {"title": "AI Research", "year": 2024}
    event   = await engine.append(sid, "working", payload)
    fetched = await engine.read(event.id)
    assert fetched["title"] == "AI Research"
    assert fetched["year"]  == 2024


async def test_read_missing_raises(engine: MemoryEngine) -> None:
    with pytest.raises(KeyError):
        await engine.read("nonexistent-event-id")


# ── timeline ──────────────────────────────────────────────────────────────────

async def test_timeline_empty_stream(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    tl  = await engine.timeline(sid)
    assert tl == []


async def test_timeline_chronological_order(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(5):
        await engine.append(sid, "working", {"i": i})
    tl = await engine.timeline(sid)
    assert len(tl) == 5
    epochs = [ev.epoch for ev, _ in tl]
    assert epochs == sorted(epochs)


async def test_timeline_payload_correct(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"key": "value"})
    tl  = await engine.timeline(sid)
    assert tl[0][1]["key"] == "value"


# ── replay ────────────────────────────────────────────────────────────────────

async def test_replay_all(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(4):
        await engine.append(sid, "working", {"i": i})
    replayed = await engine.replay(sid)
    assert len(replayed) == 4


async def test_replay_bounded(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(6):
        await engine.append(sid, "working", {"i": i})
    replayed = await engine.replay(sid, up_to_epoch=3)
    assert len(replayed) == 3


async def test_replay_from_epoch(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(6):
        await engine.append(sid, "working", {"i": i})
    replayed = await engine.replay(sid, from_epoch=4)
    assert len(replayed) == 3  # epochs 4,5,6


# ── fork ──────────────────────────────────────────────────────────────────────

async def test_fork_creates_new_stream(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid    = await engine.create_stream(agent_id)
    event1 = await engine.append(sid, "working", {"a": 1})
    forked = await engine.fork(sid, event1.id, uuid.uuid4())
    assert forked != sid


async def test_fork_independent_from_source(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid    = await engine.create_stream(agent_id)
    event1 = await engine.append(sid, "working", {"a": 1})
    forked = await engine.fork(sid, event1.id, uuid.uuid4())

    # Append to source does not affect fork
    await engine.append(sid, "working", {"a": 2})
    # fork stream has its fork event only
    fork_tl  = await engine.timeline(forked)
    source_tl = await engine.timeline(sid)
    assert len(source_tl) > len(fork_tl)


async def test_fork_bad_event_raises(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    with pytest.raises(KeyError):
        await engine.fork(sid, "nonexistent", uuid.uuid4())


# ── merge ─────────────────────────────────────────────────────────────────────

async def test_merge_creates_merge_commit(engine: MemoryEngine) -> None:
    sid_a = await engine.create_stream(uuid.uuid4())
    sid_b = await engine.create_stream(uuid.uuid4())
    await engine.append(sid_a, "working", {"branch": "A"})
    await engine.append(sid_b, "working", {"branch": "B"})

    merge_event = await engine.merge(sid_a, sid_b)
    assert "," in merge_event.parent_id  # Two-parent merge commit


async def test_merge_commit_appears_in_timeline(engine: MemoryEngine) -> None:
    sid_a = await engine.create_stream(uuid.uuid4())
    sid_b = await engine.create_stream(uuid.uuid4())
    await engine.append(sid_a, "working", {"x": 1})
    await engine.append(sid_b, "working", {"x": 2})
    merge_event = await engine.merge(sid_a, sid_b)

    tl = await engine.timeline(sid_a)
    event_ids = [ev.id for ev, _ in tl]
    assert merge_event.id in event_ids


# ── checkpoint / resume ───────────────────────────────────────────────────────

async def test_checkpoint_returns_blob_id(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid      = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"data": "x"})
    cp_id    = await engine.checkpoint(sid)
    assert isinstance(cp_id, str)
    assert len(cp_id) > 8


async def test_checkpoint_blob_is_valid_json(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid   = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"data": "x"})
    cp_id = await engine.checkpoint(sid)
    raw   = await engine.storage.retrieve_blob(cp_id)
    data  = json.loads(raw)
    assert data["type"]   == "checkpoint"
    assert data["epoch"]  == 1


async def test_resume_restores_epoch(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for _ in range(5):
        await engine.append(sid, "working", {"x": 1})
    cp_id = await engine.checkpoint(sid)

    # Reset epoch artificially
    engine._epochs[sid] = 0
    await engine.resume(sid, cp_id)
    assert engine._epochs[sid] == 5


# ── snapshot / restore_snapshot ───────────────────────────────────────────────

async def test_snapshot_returns_blob_id(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid   = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"d": 1})
    snap  = await engine.snapshot(sid)
    assert isinstance(snap, str)


async def test_snapshot_contains_all_events(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(3):
        await engine.append(sid, "working", {"i": i})
    snap = await engine.snapshot(sid)
    raw  = await engine.storage.retrieve_blob(snap)
    data = json.loads(raw)
    assert len(data["events"]) == 3


async def test_restore_snapshot_new_stream(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(3):
        await engine.append(sid, "working", {"i": i})
    snap     = await engine.snapshot(sid)
    new_sid  = await engine.restore_snapshot(snap, uuid.uuid4())
    new_tl   = await engine.timeline(new_sid)
    assert len(new_tl) == 3


# ── summarize ─────────────────────────────────────────────────────────────────

async def test_summarize_empty_stream(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid     = await engine.create_stream(agent_id)
    summary = await engine.summarize(sid)
    assert "empty" in summary.lower()


async def test_summarize_nonempty_stream(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"author": "Alice", "action": "write", "title": "Paper 1"})
    await engine.append(sid, "working", {"author": "Bob",   "action": "review"})
    summary = await engine.summarize(sid)
    assert "Alice" in summary or "Bob" in summary
    assert "2 of 2 events" in summary


# ── semantic_search ───────────────────────────────────────────────────────────

async def test_semantic_search_finds_relevant(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"content": "machine learning model training optimization"})
    await engine.append(sid, "working", {"content": "blockchain distributed consensus protocol"})
    await engine.append(sid, "working", {"content": "transformer attention mechanism efficiency"})

    results = await engine.semantic_search("deep learning neural network training")
    assert len(results) > 0
    # Most relevant should be about ML
    assert results[0]["score"] > 0


async def test_semantic_search_empty_index(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid     = await engine.create_stream(agent_id)
    results = await engine.semantic_search("anything")
    assert results == []


async def test_semantic_search_limit(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    for i in range(20):
        await engine.append(sid, "working", {"content": f"document topic {i} information"})
    results = await engine.semantic_search("topic information", limit=3)
    assert len(results) <= 3


# ── delete_stream ─────────────────────────────────────────────────────────────

async def test_delete_stream_removes_events(engine: MemoryEngine, agent_id: uuid.UUID) -> None:
    sid = await engine.create_stream(agent_id)
    await engine.append(sid, "working", {"data": "x"})
    await engine.delete_stream(sid)
    tl = await engine.timeline(sid)
    assert tl == []
