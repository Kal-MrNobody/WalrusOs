"""
Tests for Sprint 3 — EventMesh.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_event_mesh.py -v
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

from walrusos.core.models.memory import MemoryEvent
from walrusos.runtime.event_bus import EventMesh

# ── Helpers ────────────────────────────────────────────────────────────────────

# Fixed UUIDs so str(STREAM_UUID) == STREAM_ID consistently
STREAM_UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
STREAM_ID   = str(STREAM_UUID)

STREAM2_UUID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
STREAM2_ID   = str(STREAM2_UUID)


def make_event(event_id: str = "e1", stream_uuid: uuid.UUID = STREAM_UUID) -> MemoryEvent:
    """Build a minimal valid MemoryEvent for testing."""
    return MemoryEvent(
        id=event_id,
        stream_id=stream_uuid,
        parent_id="genesis",
        epoch=0,
        content_blob_id=f"blob-{event_id}",
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_subscribe_and_receive() -> None:
    """Callback fires when publish_event targets the subscribed stream."""
    mesh = EventMesh()
    received: list[MemoryEvent] = []

    await mesh.subscribe("agent1", STREAM_ID, lambda e: received.append(e))
    await mesh.publish_event(make_event("e1"))

    assert len(received) == 1
    assert received[0].id == "e1"


@pytest.mark.asyncio
async def test_stream_subscribe_no_callback_poll() -> None:
    """Queue mode: subscribe with no callback, retrieve via poll()."""
    mesh = EventMesh()

    await mesh.subscribe("agent1", STREAM_ID, callback=None)
    await mesh.publish_event(make_event("e1"))

    polled = mesh.poll("agent1", STREAM_ID)
    assert len(polled) == 1
    assert polled[0].id == "e1"


@pytest.mark.asyncio
async def test_topic_subscribe_exact() -> None:
    """Exact topic match fires the callback with the data dict."""
    mesh = EventMesh()
    received: list[dict] = []

    await mesh.subscribe_topic("agent1", "task.completed", lambda d: received.append(d))
    await mesh.emit("task.completed", {"task_id": "t1"})

    assert len(received) == 1
    assert received[0]["task_id"] == "t1"
    assert received[0]["topic"] == "task.completed"


@pytest.mark.asyncio
async def test_topic_subscribe_wildcard() -> None:
    """Wildcard 'memory.*' matches all memory.* topics."""
    mesh = EventMesh()
    received: list[dict] = []

    await mesh.subscribe_topic("agent1", "memory.*", lambda d: received.append(d))
    await mesh.emit("memory.created",         {"event_id": "e1"})
    await mesh.emit("memory.created.stream1", {"event_id": "e2"})

    assert len(received) == 2
    topics = {r["topic"] for r in received}
    assert "memory.created" in topics
    assert "memory.created.stream1" in topics


@pytest.mark.asyncio
async def test_topic_wildcard_star() -> None:
    """'*' matches any topic."""
    mesh = EventMesh()
    received: list[dict] = []

    await mesh.subscribe_topic("agent1", "*", lambda d: received.append(d))
    await mesh.emit("anything.here", {"x": 1})

    assert len(received) == 1


@pytest.mark.asyncio
async def test_topic_no_match() -> None:
    """'task.*' does NOT fire for 'memory.created'."""
    mesh = EventMesh()
    received: list[dict] = []

    await mesh.subscribe_topic("agent1", "task.*", lambda d: received.append(d))
    await mesh.emit("memory.created", {})

    assert len(received) == 0


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    """After unsubscribe(), no further events are delivered."""
    mesh = EventMesh()
    received: list[MemoryEvent] = []

    await mesh.subscribe("agent1", STREAM_ID, lambda e: received.append(e))
    await mesh.unsubscribe("agent1", STREAM_ID)
    await mesh.publish_event(make_event("e1"))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_multiple_subscribers_same_stream() -> None:
    """Both agent-a and agent-b receive the event."""
    mesh = EventMesh()
    received_a: list[MemoryEvent] = []
    received_b: list[MemoryEvent] = []

    await mesh.subscribe("agent-a", STREAM_ID, lambda e: received_a.append(e))
    await mesh.subscribe("agent-b", STREAM_ID, lambda e: received_b.append(e))
    await mesh.publish_event(make_event("e1"))

    assert len(received_a) == 1
    assert len(received_b) == 1
    assert received_a[0].id == "e1"
    assert received_b[0].id == "e1"


# ── _matches static method ────────────────────────────────────────────────────

def test_matches_exact() -> None:
    assert EventMesh._matches("task.completed", "task.completed") is True
    assert EventMesh._matches("task.completed", "task.created")   is False


def test_matches_wildcard() -> None:
    assert EventMesh._matches("task.*", "task.completed") is True
    assert EventMesh._matches("task.*", "task.created")   is True
    assert EventMesh._matches("task.*", "memory.created") is False


def test_matches_star() -> None:
    assert EventMesh._matches("*", "anything") is True
