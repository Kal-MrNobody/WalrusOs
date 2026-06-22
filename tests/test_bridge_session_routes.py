"""
Regression tests for the bridge's agent/session/presence/registry routes.

Hits the actual FastAPI routes via TestClient. Covers the post-restart
heartbeat auto-recover bug (heartbeat for unknown agent returned 404; should
return 200 + register a minimal session so the live MCP agent doesn't drop
off the dashboard after a bridge restart).
"""
from __future__ import annotations

import os

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _import_bridge():
    """Import the bridge module + reset shared state. Returns (app, presence,
    registry)."""
    # The bridge module is at dashboard/walrusos_bridge.py — make sure the
    # dashboard dir is importable.
    import sys
    from pathlib import Path
    dashboard_dir = Path(__file__).resolve().parents[1] / "dashboard"
    if str(dashboard_dir) not in sys.path:
        sys.path.insert(0, str(dashboard_dir))

    import walrusos_bridge  # type: ignore
    from walrusos.runtime.presence import get_presence_store
    from walrusos.runtime.registry  import get_registry

    presence = get_presence_store()
    registry = get_registry()
    # Drain any cross-test pollution
    presence._sessions.clear()
    registry._agents.clear()
    return walrusos_bridge.app, presence, registry


@pytest.fixture
def client():
    app, _presence, _registry = _import_bridge()
    return TestClient(app)


# ── The bug under test: heartbeat for unknown agent auto-recovers ────────────

class TestHeartbeatAutoRecover:
    def test_heartbeat_for_unknown_agent_returns_200_and_recovers(self, client):
        """When the bridge restarts after a client has already started its
        session, the client's next heartbeat arrives for an agent the bridge
        has never heard of. The handler must auto-recover (register a minimal
        session) and return 200 — NOT 404 — so the live MCP agent stays
        visible on the dashboard."""
        agent_id      = "agent-after-restart-001"
        session_token = "client-side-token-xyz"

        resp = client.post(
            "/agent/session/heartbeat",
            json={
                "session_token":       session_token,
                "agent_id":            agent_id,
                "status":              "idle",
                "memory_writes_delta": 0,
                "memory_reads_delta":  0,
                "tasks_delta":         0,
            },
        )
        assert resp.status_code == 200, (
            f"Heartbeat for unknown agent should auto-recover (200), "
            f"got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body.get("ok")        is True
        assert body.get("recovered") is True, (
            "Response must flag that the agent was auto-recovered"
        )
        assert "last_heartbeat" in body

        # Confirm the agent now appears in presence — this is what makes the
        # dashboard's Connected Agents panel show the live MCP agent again.
        presence_resp = client.get("/agent/presence")
        assert presence_resp.status_code == 200
        sessions = presence_resp.json()
        ids = {s["agent_id"] for s in sessions}
        assert agent_id in ids, (
            f"Auto-recovered agent {agent_id} must show in /agent/presence, "
            f"got: {ids}"
        )

    def test_heartbeat_for_known_agent_does_not_flag_recover(self, client):
        """Normal flow: /agent/session/start first, then heartbeat. The
        response's `recovered` flag must be False."""
        client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-normal-flow",
                "agent_name":   "Alice",
                "workspace_id": "ws-1",
                "framework":    "claude-code",
                "capabilities": [],
                "tools":        [],
            },
        )
        resp = client.post(
            "/agent/session/heartbeat",
            json={
                "session_token": "tok-normal",
                "agent_id":      "agent-normal-flow",
                "status":        "working",
                "memory_writes_delta": 1,
                "memory_reads_delta":  0,
                "tasks_delta":         0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body.get("recovered", False) is False

    def test_repeated_heartbeats_after_recover_still_200(self, client):
        """After auto-recover, subsequent heartbeats from the same client must
        succeed without re-recovering (the session now exists)."""
        agent_id = "agent-recover-then-repeat"
        for i in range(3):
            resp = client.post(
                "/agent/session/heartbeat",
                json={
                    "session_token":       "tok",
                    "agent_id":            agent_id,
                    "status":              "idle",
                    "memory_writes_delta": 0,
                    "memory_reads_delta":  0,
                    "tasks_delta":         0,
                },
            )
            assert resp.status_code == 200, f"iteration {i}: {resp.text}"
        # First should be recovered=True, later ones recovered=False
        # (already-registered branch); we don't strictly assert which iteration
        # was the recover, only that no call 404s.

    def test_heartbeat_after_session_end_recovers_again(self, client):
        """If the client posts a heartbeat after the session has been ended,
        the bridge must still auto-recover rather than 404."""
        client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-ended",
                "agent_name":   "Bob",
                "workspace_id": "ws-1",
                "framework":    "claude-code",
                "capabilities": [],
                "tools":        [],
            },
        )
        client.post(
            "/agent/session/end",
            json={"session_token": "tok-end", "agent_id": "agent-ended"},
        )
        # Now heartbeat — must recover and succeed
        resp = client.post(
            "/agent/session/heartbeat",
            json={
                "session_token":       "tok-after-end",
                "agent_id":            "agent-ended",
                "status":              "idle",
                "memory_writes_delta": 0,
                "memory_reads_delta":  0,
                "tasks_delta":         0,
            },
        )
        assert resp.status_code == 200
        assert resp.json().get("recovered") is True


# ── Sanity: the other 5 session/presence/registry routes still work ───────────

class TestSessionAndPresenceRoutesIntact:
    """Confirms the heartbeat fix didn't collateral-damage the sibling routes."""

    def test_session_start_returns_token(self, client):
        resp = client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-start-test",
                "agent_name":   "StartTester",
                "workspace_id": "ws-x",
                "framework":    "gemini",
                "capabilities": [{"name": "research"}],
                "tools":        ["memory_append"],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("status") == "connected"
        assert "session_token" in body

    def test_session_end_returns_ok(self, client):
        client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-end-test",
                "agent_name":   "EndTester",
                "workspace_id": "ws-x",
                "framework":    "custom",
                "capabilities": [],
                "tools":        [],
            },
        )
        resp = client.post(
            "/agent/session/end",
            json={"session_token": "tok-end-test", "agent_id": "agent-end-test"},
        )
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

    def test_presence_lists_registered_session(self, client):
        client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-presence-test",
                "agent_name":   "PresenceTester",
                "workspace_id": "ws-presence",
                "framework":    "gemini",
                "capabilities": [],
                "tools":        [],
            },
        )
        resp = client.get("/agent/presence")
        assert resp.status_code == 200
        names = [s["agent_name"] for s in resp.json()]
        assert "PresenceTester" in names

    def test_registry_lists_registered_capabilities(self, client):
        client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-registry-test",
                "agent_name":   "RegistryTester",
                "workspace_id": "ws-reg",
                "framework":    "gemini",
                "capabilities": [
                    {"name": "research"},
                    {"name": "code_review"},
                ],
                "tools":        [],
            },
        )
        resp = client.get("/agent/registry")
        assert resp.status_code == 200
        entries = resp.json()
        entry = next(
            (e for e in entries if e["agent_name"] == "RegistryTester"), None,
        )
        assert entry is not None
        cap_names = {c["name"] for c in entry["capabilities"]}
        assert "research" in cap_names
        assert "code_review" in cap_names

    def test_discover_filters_by_capability(self, client):
        client.post(
            "/agent/session/start",
            json={
                "agent_id":     "agent-discover-test",
                "agent_name":   "DiscoverTester",
                "workspace_id": "ws-disc",
                "framework":    "gemini",
                "capabilities": [{"name": "unique-discover-cap"}],
                "tools":        [],
            },
        )
        resp = client.get(
            "/agent/discover", params={"capability": "unique-discover-cap"},
        )
        assert resp.status_code == 200
        names = [a["agent_name"] for a in resp.json()]
        assert "DiscoverTester" in names
