"""
Tests for Sprint 4 — Agent Registry & Integration Helpers.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_agent_registry.py -v
"""
from __future__ import annotations

import asyncio
import contextlib
import os

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

from walrusos.client import WalrusOS
from walrusos.runtime.registry import (
    AgentCapability,
    AgentRegistration,
    AgentRegistry,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def registry() -> AgentRegistry:
    """Fresh AgentRegistry for each test."""
    return AgentRegistry()


@pytest.fixture
def runtime() -> WalrusOS:
    return WalrusOS(use_mocks=True)


@pytest.fixture
def mock_httpx():
    """Patch httpx so no real network calls are made."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(
        return_value={"session_token": "test-token", "status": "connected"}
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.get  = AsyncMock(return_value=mock_resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__  = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=ctx):
        yield mock_client


# ── AgentRegistry unit tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_agent(registry: AgentRegistry) -> None:
    """register() stores a registration keyed by agent_id."""
    reg = AgentRegistration(
        agent_id="a1",
        agent_name="Claude",
        framework="claude-code",
        workspace_id="ws1",
        capabilities=[AgentCapability(name="code_generation", languages=["python"])],
    )
    await registry.register(reg)

    stored = registry.get("a1")
    assert stored is not None
    assert stored.agent_name == "Claude"
    assert stored.framework  == "claude-code"


@pytest.mark.asyncio
async def test_unregister_agent(registry: AgentRegistry) -> None:
    """unregister() removes the agent; get() returns None afterwards."""
    reg = AgentRegistration(
        agent_id="a1", agent_name="Claude",
        framework="claude-code", workspace_id="ws1",
    )
    await registry.register(reg)
    await registry.unregister("a1")
    assert registry.get("a1") is None


@pytest.mark.asyncio
async def test_find_by_capability(registry: AgentRegistry) -> None:
    """find_by_capability() returns only agents that have the capability."""
    await registry.register(AgentRegistration(
        agent_id="a1", agent_name="Claude", framework="claude-code", workspace_id="ws1",
        capabilities=[AgentCapability(name="code_generation"), AgentCapability(name="code_review")],
    ))
    await registry.register(AgentRegistration(
        agent_id="a2", agent_name="Gemini", framework="gemini", workspace_id="ws1",
        capabilities=[AgentCapability(name="research")],
    ))

    matches = registry.find_by_capability("code_generation")
    assert len(matches) == 1
    assert matches[0].agent_name == "Claude"


def test_find_by_capability_no_match(registry: AgentRegistry) -> None:
    """find_by_capability() returns empty list when no agent has that capability."""
    matches = registry.find_by_capability("nonexistent_capability")
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_find_by_framework(registry: AgentRegistry) -> None:
    """find_by_framework() filters by framework string."""
    await registry.register(AgentRegistration(
        agent_id="a1", agent_name="Claude", framework="claude-code", workspace_id="ws1",
    ))
    await registry.register(AgentRegistration(
        agent_id="a2", agent_name="Cursor", framework="cursor", workspace_id="ws1",
    ))

    claude_agents = registry.find_by_framework("claude-code")
    assert len(claude_agents) == 1
    assert claude_agents[0].agent_name == "Claude"


@pytest.mark.asyncio
async def test_list_all(registry: AgentRegistry) -> None:
    """list_all() returns all registered agents."""
    for i in range(3):
        await registry.register(AgentRegistration(
            agent_id=f"a{i}", agent_name=f"Agent{i}",
            framework="custom", workspace_id="ws1",
        ))
    assert len(registry.list_all()) == 3


# ── connect_* helper tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_claude_code_helper(runtime: WalrusOS, mock_httpx) -> None:
    """connect_claude_code() registers with framework='claude-code' and code_generation."""
    from walrusos.integrations.connect import connect_claude_code

    ws    = runtime.workspace("test-connect-claude")
    agent = await connect_claude_code(ws)

    # Cancel background heartbeat
    if agent._heartbeat_task:
        agent._heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await agent._heartbeat_task

    assert agent._framework == "claude-code"

    # Verify POST body contains capabilities
    assert mock_httpx.post.call_count >= 1
    call_body = mock_httpx.post.call_args_list[0].kwargs["json"]
    cap_names  = [c["name"] for c in call_body.get("capabilities", [])]
    assert "code_generation" in cap_names
    assert call_body["framework"] == "claude-code"


@pytest.mark.asyncio
async def test_connect_cursor_helper(runtime: WalrusOS, mock_httpx) -> None:
    """connect_cursor() registers with framework='cursor'."""
    from walrusos.integrations.connect import connect_cursor

    ws    = runtime.workspace("test-connect-cursor")
    agent = await connect_cursor(ws)

    if agent._heartbeat_task:
        agent._heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await agent._heartbeat_task

    assert agent._framework == "cursor"
    call_body = mock_httpx.post.call_args_list[0].kwargs["json"]
    assert call_body["framework"] == "cursor"


@pytest.mark.asyncio
async def test_discover_via_workspace(runtime: WalrusOS, mock_httpx) -> None:
    """workspace.discover() makes GET /agent/discover and returns a list."""
    mock_httpx.get.return_value.json = MagicMock(return_value=[
        {"agent_name": "Claude Code", "framework": "claude-code", "capabilities": []}
    ])

    ws      = runtime.workspace("test-discover")
    results = await ws.discover(capability="code_review")

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["agent_name"] == "Claude Code"
