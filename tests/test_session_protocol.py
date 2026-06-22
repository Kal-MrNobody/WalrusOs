"""
Tests for Sprint 2 — Agent Session Protocol.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_session_protocol.py -v
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

from walrusos.client import WalrusOS
from walrusos.core.models.session import AgentSession, SessionActivity
from walrusos.runtime.presence import PresenceStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store() -> PresenceStore:
    """Fresh PresenceStore for each test."""
    return PresenceStore()


@pytest.fixture
def runtime() -> WalrusOS:
    return WalrusOS(use_mocks=True)


@pytest.fixture
def mock_httpx():
    """
    Patch httpx.AsyncClient so bridge calls never hit the network.
    Yields the mock client instance whose .post attribute records all calls.
    """
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(
        return_value={"session_token": "test-session-token", "status": "connected"}
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=ctx):
        yield mock_client


# ── PresenceStore unit tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_presence_store_register(store: PresenceStore) -> None:
    """register() creates a session in the store."""
    session = await store.register(
        agent_id="agent-001",
        agent_name="Alice",
        workspace_id="ws-1",
        framework="claude-code",
    )

    assert session.agent_id == "agent-001"
    assert session.agent_name == "Alice"
    assert session.workspace_id == "ws-1"
    assert session.framework == "claude-code"
    assert session.status == "online"

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].agent_id == "agent-001"


@pytest.mark.asyncio
async def test_presence_store_heartbeat(store: PresenceStore) -> None:
    """heartbeat() updates last_heartbeat and counters."""
    from datetime import datetime, timedelta

    await store.register("agent-002", "Bob", "ws-1")

    # Wind back the clock so the update is detectable
    session = store.get_session("agent-002")
    session.last_heartbeat = datetime.utcnow() - timedelta(seconds=5)
    before = session.last_heartbeat

    updated = await store.heartbeat(
        "agent-002",
        status="thinking",
        memory_writes_delta=2,
    )

    assert updated.status == "thinking"
    assert updated.memory_writes == 2
    assert updated.last_heartbeat > before


@pytest.mark.asyncio
async def test_presence_store_heartbeat_unknown_agent(store: PresenceStore) -> None:
    """heartbeat() raises KeyError for an unregistered agent."""
    with pytest.raises(KeyError):
        await store.heartbeat("nonexistent-agent")


@pytest.mark.asyncio
async def test_presence_store_unregister(store: PresenceStore) -> None:
    """unregister() removes the session from the store."""
    await store.register("agent-003", "Charlie", "ws-1")
    assert len(store.list_sessions()) == 1

    await store.unregister("agent-003")
    assert len(store.list_sessions()) == 0


# ── AgentSession model tests ──────────────────────────────────────────────────

def test_activity_log_capped_at_20() -> None:
    """activity_log never exceeds 20 entries."""
    session = AgentSession(agent_id="a", agent_name="X", workspace_id="ws")

    for i in range(25):
        session.log("write_memory", f"entry {i}")

    assert len(session.activity_log) == 20
    # Most recent entries are kept
    assert session.activity_log[-1].detail == "entry 24"


def test_session_is_stale_after_30s() -> None:
    """is_stale returns True when last_heartbeat is >30s ago."""
    from datetime import datetime, timedelta

    session = AgentSession(agent_id="a", agent_name="X", workspace_id="ws")
    session.last_heartbeat = datetime.utcnow() - timedelta(seconds=35)

    assert session.is_stale is True


def test_session_not_stale_recent() -> None:
    """is_stale returns False for a freshly-created session."""
    session = AgentSession(agent_id="a", agent_name="X", workspace_id="ws")
    assert session.is_stale is False


# ── Broadcast tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_fires_on_register(store: PresenceStore) -> None:
    """Subscribing to the store fires a callback on register."""
    received: list[str] = []
    store.subscribe(lambda msg: received.append(msg))

    await store.register("agent-004", "Delta", "ws-2")

    assert len(received) == 1
    data = json.loads(received[0])
    assert data["type"] == "agent_joined"
    assert data["agent_name"] == "Delta"


# ── SDK integration tests (mock httpx) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_go_online_calls_session_start(runtime: WalrusOS, mock_httpx) -> None:
    """go_online() POSTs to /agent/session/start with correct agent details."""
    ws    = runtime.workspace("test-go-online")
    agent = ws.agent("OnlineAgent")

    await agent.go_online(framework="claude-code")

    # Clean up background heartbeat task
    if agent._heartbeat_task:
        agent._heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await agent._heartbeat_task

    assert mock_httpx.post.call_count >= 1
    first_call = mock_httpx.post.call_args_list[0]
    url  = first_call.args[0]
    body = first_call.kwargs["json"]

    assert "session/start" in url
    assert body["agent_id"]   == str(agent.agent_id)
    assert body["framework"]  == "claude-code"
    assert body["agent_name"] == agent.agent_name


@pytest.mark.asyncio
async def test_go_offline_calls_session_end(runtime: WalrusOS, mock_httpx) -> None:
    """go_offline() cancels the heartbeat and POSTs to /agent/session/end."""
    ws    = runtime.workspace("test-go-offline")
    agent = ws.agent("OfflineAgent")

    await agent.go_online()
    await agent.go_offline()

    assert agent._session_token is None
    assert agent._heartbeat_task is None

    # Should have at least: POST /start  +  POST /end
    assert mock_httpx.post.call_count >= 2

    last_call = mock_httpx.post.call_args_list[-1]
    url = last_call.args[0]
    assert "session/end" in url


@pytest.mark.asyncio
async def test_context_manager_lifecycle(runtime: WalrusOS, mock_httpx) -> None:
    """async with agent.session() calls go_online on enter and go_offline on exit."""
    ws    = runtime.workspace("test-ctx-lifecycle")
    agent = ws.agent("CtxAgent")

    async with agent.session("custom task") as a:
        assert a is agent
        assert a._session_token is not None

    assert agent._session_token is None


# ── Framework detection ───────────────────────────────────────────────────────

def test_detect_framework_claude_code(monkeypatch) -> None:
    """_detect_framework() returns 'claude-code' when CLAUDE_CODE env var is set."""
    from walrusos.sdk.agent import AgentClient

    monkeypatch.setenv("CLAUDE_CODE", "1")
    result = AgentClient._detect_framework()
    assert result == "claude-code"
