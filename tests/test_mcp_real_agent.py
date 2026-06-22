"""
Sprint 7 — Tests for the REAL MCP agent connection path.

These tests verify that when an external AI tool connects to the WalrusOS
MCP server, it is registered in presence, its tool calls produce activity,
and the session is cleaned up on shutdown.

All bridge HTTP is monkeypatched — no real network. Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_mcp_real_agent.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

import pytest

from walrusos.mcp import server as mcp_server


# ── Fixture: reset module state and capture bridge HTTP ───────────────────────

@pytest.fixture
def fake_bridge(monkeypatch):
    """Replace the bridge POST helpers with in-memory recorders."""
    calls = {
        "session_start":     [],
        "session_heartbeat": [],
        "session_end":       [],
    }

    async def _fake_start():
        calls["session_start"].append({
            "agent_id":     mcp_server._AGENT_ID,
            "agent_name":   mcp_server._AGENT_NAME,
            "workspace_id": str(mcp_server.workspace.workspace_id),
            "framework":    mcp_server._FRAMEWORK,
            "capabilities": mcp_server._capabilities_for_framework(mcp_server._FRAMEWORK),
            "tools":        mcp_server._TOOLS_EXPOSED,
        })
        return "fake-session-token-123"

    async def _fake_heartbeat(
        status=None,
        memory_writes_delta=0,
        memory_reads_delta=0,
        tasks_delta=0,
    ):
        calls["session_heartbeat"].append({
            "status":              status,
            "memory_writes_delta": memory_writes_delta,
            "memory_reads_delta":  memory_reads_delta,
            "tasks_delta":         tasks_delta,
        })

    async def _fake_end():
        calls["session_end"].append({"agent_id": mcp_server._AGENT_ID})

    monkeypatch.setattr(mcp_server, "_post_session_start",     _fake_start)
    monkeypatch.setattr(mcp_server, "_post_session_heartbeat", _fake_heartbeat)
    monkeypatch.setattr(mcp_server, "_post_session_end",       _fake_end)

    # Reset module agent state — each test starts clean
    mcp_server._agent_state.update({
        "registered":     False,
        "session_token":  None,
        "heartbeat_task": None,
        "register_lock":  None,
    })
    return calls


# ── Part A — Server registers itself as a live agent ─────────────────────────

class TestMCPRegistration:
    async def test_registers_agent_on_first_tool_call(self, fake_bridge):
        await mcp_server.call_tool("memory_append", {"content": "hello"})
        assert len(fake_bridge["session_start"]) == 1
        sent = fake_bridge["session_start"][0]
        assert sent["agent_name"] == mcp_server._AGENT_NAME
        assert sent["framework"]  == mcp_server._FRAMEWORK

    async def test_registers_only_once(self, fake_bridge):
        """Concurrent / repeated tool calls must not double-register."""
        await mcp_server.call_tool("memory_append", {"content": "one"})
        await mcp_server.call_tool("memory_append", {"content": "two"})
        await mcp_server.call_tool("memory_search", {"query": "one"})
        assert len(fake_bridge["session_start"]) == 1

    async def test_registers_explicitly(self, fake_bridge):
        await mcp_server._ensure_agent_session()
        assert mcp_server._agent_state["registered"] is True
        assert mcp_server._agent_state["session_token"] == "fake-session-token-123"
        assert len(fake_bridge["session_start"]) == 1


# ── Part A — Capabilities by framework ───────────────────────────────────────

class TestCapabilitiesMapping:
    def test_claude_code_capabilities(self):
        caps = mcp_server._capabilities_for_framework("claude-code")
        names = {c["name"] for c in caps}
        assert "code_generation" in names
        assert "code_review"     in names

    def test_cursor_capabilities(self):
        caps  = mcp_server._capabilities_for_framework("cursor")
        names = {c["name"] for c in caps}
        assert "code_generation" in names
        assert "file_editing"    in names

    def test_unknown_framework_gets_general(self):
        caps  = mcp_server._capabilities_for_framework("totally-unknown")
        names = {c["name"] for c in caps}
        assert "general" in names


# ── Part A/B — Tool calls send activity heartbeats ────────────────────────────

class TestToolActivity:
    async def test_memory_append_sends_write_activity(self, fake_bridge):
        await mcp_server.call_tool("memory_append", {"content": "hello"})
        beats = fake_bridge["session_heartbeat"]
        # Find the activity beat for the append tool — status "working" with writes_delta=1
        write_beats = [b for b in beats if b["memory_writes_delta"] == 1]
        assert len(write_beats) >= 1
        assert write_beats[0]["status"] == "working"

    async def test_memory_search_sends_thinking_status(self, fake_bridge):
        # Register & write first so search has something to hit
        await mcp_server.call_tool("memory_append", {"content": "indexed"})
        baseline = len(fake_bridge["session_heartbeat"])
        await mcp_server.call_tool("memory_search", {"query": "indexed"})
        new_beats = fake_bridge["session_heartbeat"][baseline:]
        thinking = [b for b in new_beats if b["status"] == "thinking" and b["memory_reads_delta"] == 1]
        assert len(thinking) >= 1

    async def test_task_complete_increments_tasks(self, fake_bridge):
        await mcp_server.call_tool("agent_status", {})
        baseline = len(fake_bridge["session_heartbeat"])
        # We don't need a real task_id to exercise the heartbeat path —
        # the tool will return "Task not found" but activity fires first.
        await mcp_server.call_tool("task_complete", {"task_id": "nonexistent"})
        new_beats = fake_bridge["session_heartbeat"][baseline:]
        assert any(b["tasks_delta"] == 1 for b in new_beats)


# ── Part A — Presence failure does not break tool calls ──────────────────────

class TestPresenceFailureSwallowed:
    async def test_failing_bridge_does_not_break_tool(self, monkeypatch):
        """Even if the bridge raises, memory_append must still return a result."""
        async def _raise(*a, **kw):
            raise ConnectionError("bridge unreachable")

        monkeypatch.setattr(mcp_server, "_post_session_start",     _raise)
        monkeypatch.setattr(mcp_server, "_post_session_heartbeat", _raise)
        monkeypatch.setattr(mcp_server, "_post_session_end",       _raise)

        mcp_server._agent_state.update({
            "registered":     False,
            "session_token":  None,
            "heartbeat_task": None,
            "register_lock":  None,
        })

        result = await mcp_server.call_tool("memory_append", {"content": "still works"})
        assert len(result) == 1
        assert "Saved" in result[0].text or "Blob" in result[0].text


# ── Part A/B — Shutdown unregisters ──────────────────────────────────────────

class TestShutdown:
    async def test_shutdown_calls_session_end(self, fake_bridge):
        await mcp_server._ensure_agent_session()
        assert mcp_server._agent_state["registered"] is True
        await mcp_server._shutdown_agent_session()
        assert len(fake_bridge["session_end"]) == 1
        assert mcp_server._agent_state["registered"] is False
        assert mcp_server._agent_state["session_token"] is None

    async def test_shutdown_is_idempotent(self, fake_bridge):
        await mcp_server._ensure_agent_session()
        await mcp_server._shutdown_agent_session()
        # Second call should not raise; session_end may or may not be re-called
        # but state must remain clean.
        await mcp_server._shutdown_agent_session()
        assert mcp_server._agent_state["registered"] is False


# ── Part C — connect command writes valid config ─────────────────────────────

class TestConnectWriteMergesConfig:
    def test_merges_into_existing_config(self, tmp_path, monkeypatch):
        """If a config already has another MCP server, we must keep it."""
        from walrusos.cli.cmd_connect import _write_json_merge, _mcp_entry

        cfg = tmp_path / "claude_desktop_config.json"
        existing = {
            "mcpServers": {
                "other-server": {"command": "other", "args": ["run"]}
            },
            "theme": "dark",
        }
        cfg.write_text(json.dumps(existing))

        _write_json_merge(
            cfg,
            {"mcpServers": {"walrusos": _mcp_entry("claude-code")}},
        )

        data = json.loads(cfg.read_text())
        assert "other-server" in data["mcpServers"]
        assert "walrusos"     in data["mcpServers"]
        assert data["theme"] == "dark"

    def test_generated_config_has_env(self):
        from walrusos.cli.cmd_connect import _mcp_entry
        entry = _mcp_entry("claude-code")
        assert "env" in entry
        env = entry["env"]
        assert env["WALRUSOS_MCP_AGENT_NAME"] == "Claude Code"
        assert env["WALRUSOS_MCP_FRAMEWORK"]  == "claude-code"
        assert env["WALRUSOS_USE_MOCKS"]      == "0"

    def test_cursor_entry_uses_cursor_framework(self):
        from walrusos.cli.cmd_connect import _mcp_entry
        entry = _mcp_entry("cursor")
        assert entry["env"]["WALRUSOS_MCP_AGENT_NAME"] == "Cursor"
        assert entry["env"]["WALRUSOS_MCP_FRAMEWORK"]  == "cursor"

    def test_creates_config_when_missing(self, tmp_path):
        from walrusos.cli.cmd_connect import _write_json_merge, _mcp_entry

        cfg = tmp_path / "subdir" / "config.json"  # parent doesn't exist
        _write_json_merge(
            cfg,
            {"mcpServers": {"walrusos": _mcp_entry("claude-code")}},
        )
        assert cfg.exists()
        data = json.loads(cfg.read_text())
        assert "walrusos" in data["mcpServers"]
