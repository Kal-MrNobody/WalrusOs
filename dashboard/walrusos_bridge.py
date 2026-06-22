"""
WalrusOS Dashboard Bridge
A lightweight FastAPI server that exposes the Python runtime to the Next.js dashboard.

P0 Fix 5: Removed use_mocks=True and all hardcoded fake data.
Every endpoint now reads from the real runtime (SQLite ledger for metadata,
Walrus for blob content, Sui event log for permissions).

Run: uvicorn dashboard.walrusos_bridge:app --reload --port 8787
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
from walrusos import WalrusOS
from walrusos.cli._state import get_runtime
from walrusos.runtime.presence import get_presence_store

logger = logging.getLogger(__name__)

app = FastAPI(title="WalrusOS Dashboard Bridge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singleton Runtime (production — reads config from ~/.walrusos/config.json) ─

def _build_runtime() -> WalrusOS:
    """
    Build a production WalrusOS runtime.
    Falls back to mock mode only if WALRUSOS_USE_MOCKS=1 is set (CI / dev).
    """
    return get_runtime()

runtime = _build_runtime()

# WebSocket subscriber list for live event broadcasting
_event_subscribers: list[WebSocket] = []

# ── Helper: access the underlying SQLite ledger ───────────────────────────────

def _get_sqlite():
    """Return the SQLiteLedger from the production runtime, or None."""
    try:
        ledger = runtime._engine.ledger
        # SuiLedgerAdapter wraps SQLiteLedger
        if hasattr(ledger, "_sqlite"):
            return ledger._sqlite
        # SQLiteLedger itself (e.g. in test mode)
        if hasattr(ledger, "_engine"):
            return ledger
    except Exception:
        pass
    return None


# ── Workspace Endpoints ───────────────────────────────────────────────────────

@app.get("/api/workspaces")
async def list_workspaces() -> list[dict[str, Any]]:
    """
    List workspaces inferred from SQLite — any stream whose agent_id maps to
    a deterministic UUID5 workspace is grouped under that workspace name.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import MemoryStreamRecord
    from sqlmodel import Session, select

    workspaces: dict[str, dict] = {}
    try:
        with Session(sqlite._engine) as session:
            records = session.exec(select(MemoryStreamRecord)).all()
        for r in records:
            # stream_id is a UUID5 derived from "<workspace>.stream.<name>"
            # We can't reverse it, so we show all known stream IDs grouped.
            ws_key = r.agent_id[:8]  # rough grouping by agent prefix
            if ws_key not in workspaces:
                workspaces[ws_key] = {
                    "id":         r.agent_id,
                    "name":       f"workspace-{ws_key}",
                    "streams":    0,
                    "created_at": r.created_at,
                }
            workspaces[ws_key]["streams"] += 1
    except Exception as exc:
        logger.warning("list_workspaces failed: %s", exc)

    return list(workspaces.values())


@app.post("/api/workspaces")
async def create_workspace(body: dict[str, str]) -> dict[str, Any]:
    name = body.get("name", "Unnamed")
    ws   = runtime.workspace(name)
    return {"id": str(ws.workspace_id), "name": name, "agents": 0, "streams": 0}


# ── Agent Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/workspaces/{workspace}/agents")
async def list_agents(workspace: str) -> list[dict[str, Any]]:
    """
    List persistent AgentIdentity records for this workspace.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import AgentIdentityRecord
    from sqlmodel import Session, select

    ws_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, workspace))
    result = []
    try:
        with Session(sqlite._engine) as session:
            agents = session.exec(
                select(AgentIdentityRecord).where(AgentIdentityRecord.workspace_id == ws_id)
            ).all()
            for a in agents:
                result.append({
                    "id":        a.agent_id,
                    "name":      a.agent_name,
                    "workspace": workspace,
                    "status":    a.status,
                    "execution_counter": a.execution_counter,
                    "memory_counter":    a.memory_counter,
                    "public_key":        a.public_key,
                    "reputation":        json.loads(a.reputation_json) if a.reputation_json else {},
                })
    except Exception as exc:
        logger.warning("list_agents failed: %s", exc)

    return result

@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict[str, Any]:
    """Return the full identity card for an agent."""
    sqlite = _get_sqlite()
    if sqlite is None:
        return {}

    from walrusos.adapters.sqlite_ledger import AgentIdentityRecord
    from sqlmodel import Session
    import json

    try:
        with Session(sqlite._engine) as session:
            a = session.get(AgentIdentityRecord, agent_id)
            if not a:
                return {}
            return {
                "id":           a.agent_id,
                "name":         a.agent_name,
                "workspace_id": a.workspace_id,
                "owner_wallet": a.owner_wallet,
                "public_key":   a.public_key,
                "trust_root":   a.trust_root,
                "status":       a.status,
                "capabilities": json.loads(a.capabilities_json),
                "execution_counter": a.execution_counter,
                "memory_counter":    a.memory_counter,
                "artifact_counter":  a.artifact_counter,
                "reputation":        json.loads(a.reputation_json),
                "metadata":          json.loads(a.metadata_json),
                "sui_object_id":     a.sui_object_id,
                "created_at":        a.created_at,
            }
    except Exception as exc:
        logger.warning("get_agent failed: %s", exc)
        return {}


@app.get("/api/workspaces/{workspace}/graph")
async def agent_graph(workspace: str) -> dict[str, Any]:
    agents = await list_agents(workspace)
    nodes  = [{"id": a["id"], "label": a["name"], "status": a["status"]} for a in agents]
    edges: list[dict] = []
    for i in range(len(nodes) - 1):
        edges.append({
            "source": nodes[i]["id"],
            "target": nodes[i + 1]["id"],
            "stream": "shared",
        })
    return {"nodes": nodes, "edges": edges}


# ── Memory Timeline Endpoints ─────────────────────────────────────────────────

@app.get("/api/streams")
async def list_streams() -> list[dict[str, Any]]:
    """List all MemoryStreams from SQLite with event counts."""
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import MemoryStreamRecord, MemoryEventRecord
    from sqlmodel import Session, select, func

    result = []
    try:
        with Session(sqlite._engine) as session:
            streams = session.exec(select(MemoryStreamRecord)).all()
            for s in streams:
                count = session.exec(
                    select(func.count(MemoryEventRecord.id)).where(  # type: ignore[arg-type]
                        MemoryEventRecord.stream_id == s.stream_id
                    )
                ).one()
                result.append({
                    "id":         s.stream_id,
                    "name":       s.stream_id[:12] + "…",
                    "events":     count,
                    "workspace":  "default",
                    "head":       s.head_event_id,
                    "epoch":      s.epoch_counter,
                    "created_at": s.created_at,
                })
    except Exception as exc:
        logger.warning("list_streams failed: %s", exc)

    return result


@app.get("/api/streams/{stream_id}/timeline")
async def get_timeline(stream_id: str) -> list[dict[str, Any]]:
    """
    Return the event timeline for a stream from SQLite.
    Blob content is NOT fetched here to keep the API fast — the client
    must call /api/events/{event_id} to retrieve full payload.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import MemoryEventRecord
    from sqlmodel import Session, select

    result = []
    try:
        with Session(sqlite._engine) as session:
            events = session.exec(
                select(MemoryEventRecord)
                .where(MemoryEventRecord.stream_id == stream_id)
                .order_by(MemoryEventRecord.epoch)
            ).all()
            for ev in events:
                result.append({
                    "id":             ev.id,
                    "epoch":          ev.epoch,
                    "class_type":     ev.class_type,
                    "parent_id":      ev.parent_id,
                    "content_blob_id": ev.content_blob_id,
                    "created_at":     ev.created_at,
                    "verified":       bool(getattr(ev, "signature", None)),
                })
    except Exception as exc:
        logger.warning("get_timeline failed: %s", exc)

    return result


# ── Artifact Endpoints ────────────────────────────────────────────────────────

@app.get("/api/artifacts")
async def list_artifacts() -> list[dict[str, Any]]:
    """
    List all known blobs from the SQLite blob_manifests table
    plus any content_blob_id values from the events table.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import BlobManifestRecord, MemoryEventRecord
    from sqlmodel import Session, select

    artifacts = []
    try:
        with Session(sqlite._engine) as session:
            # Manifests (chunked blobs > 4 MiB)
            manifests = session.exec(select(BlobManifestRecord)).all()
            for m in manifests:
                artifacts.append({
                    "id":         m.manifest_blob_id,
                    "name":       m.manifest_blob_id[:20] + "…",
                    "type":       m.mime_type,
                    "stream":     "chunked",
                    "size_kb":    round(m.original_size / 1024, 1),
                    "created_at": m.created_at,
                    "blob_id":    m.manifest_blob_id,
                })
            # Regular blobs referenced from events
            events = session.exec(select(MemoryEventRecord).limit(200)).all()
            seen = {m.manifest_blob_id for m in manifests}
            for ev in events:
                if ev.content_blob_id not in seen:
                    seen.add(ev.content_blob_id)
                    artifacts.append({
                        "id":         ev.content_blob_id,
                        "name":       ev.content_blob_id[:20] + "…",
                        "type":       f"event/{ev.class_type}",
                        "stream":     ev.stream_id[:8],
                        "size_kb":    None,
                        "created_at": ev.created_at,
                        "blob_id":    ev.content_blob_id,
                    })
    except Exception as exc:
        logger.warning("list_artifacts failed: %s", exc)

    return artifacts


# ── Search Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/search")
async def search(q: str = "") -> list[dict[str, Any]]:
    """Semantic search across the in-process vector index."""
    if not q:
        return []
    try:
        results = await runtime._engine.semantic_search(q, limit=10)
        return [
            {
                "id":        r.get("doc_id", ""),
                "stream":    r.get("metadata", {}).get("stream_id", ""),
                "score":     r.get("score", 0.0),
                "text":      r.get("text", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for r in results
        ]
    except Exception as exc:
        logger.warning("search failed: %s", exc)
        return []


# ── Permission Endpoints ──────────────────────────────────────────────────────

@app.get("/api/permissions")
async def list_permissions_endpoint() -> list[dict[str, Any]]:
    """
    List capability grants from the local SQLite `capabilities` table.

    Schema notes (the table stores less than the on-chain grant carries):
      Columns:  sui_object_id (PK), target_stream_id, verb_bitmask,
                valid_until_epoch, created_at
      Not stored: per-grant recipient agent_id, transaction_digest.

    What we surface:
      - `agent` / `agent_name` — best-effort: the OWNER of the target stream
        (recovered via memory_streams.agent_id → agent_identities.agent_name).
        The on-chain Capability is owned by the recipient, but the SQLite cache
        does not track that mapping.
      - `stream` / `stream_name` — the stream UUID; name resolves to the owner
        agent's name when available.
      - `verbs` — verb_bitmask decoded to lowercase strings matching the
        Permissions page's badge palette (read/write/publish/admin).
      - `granted_at` — the row's `created_at` (real, persisted).
      - `valid_until` — `valid_until_epoch == 0` is "never expires" per the
        delegate_capability convention; empty string when so, otherwise the
        explorer-style epoch number.
      - `capability_id` / `sui_object_url` — the Sui Capability OBJECT (not
        the tx digest, which is not cached). Pasting `sui_object_url` into a
        browser opens the on-chain capability object on Suiscan.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import (
        CapabilityRecord, MemoryStreamRecord, AgentIdentityRecord,
    )
    from sqlmodel import Session, select

    # Bitmask → verb name. Lowercase matches the frontend VERB_STYLE palette.
    VERBS: list[tuple[int, str]] = [
        (1, "read"),
        (2, "write"),
        (4, "admin"),
        (8, "publish"),
    ]

    result: list[dict[str, Any]] = []
    try:
        with Session(sqlite._engine) as session:
            agents = session.exec(select(AgentIdentityRecord)).all()
            agent_name_by_id: dict[str, str] = {
                a.agent_id: a.agent_name for a in agents
            }

            streams = session.exec(select(MemoryStreamRecord)).all()
            stream_owner_agent: dict[str, str] = {
                s.stream_id: agent_name_by_id.get(s.agent_id, "")
                for s in streams
            }

            caps = session.exec(select(CapabilityRecord)).all()
            for cap in caps:
                verbs = [name for (bit, name) in VERBS if (cap.verb_bitmask & bit) == bit]
                owner_name = stream_owner_agent.get(str(cap.target_stream_id), "")

                # epoch=0 → never expires
                if cap.valid_until_epoch == 0:
                    valid_until_str = ""
                    valid_until_label = "never"
                else:
                    valid_until_str   = str(cap.valid_until_epoch)
                    valid_until_label = f"epoch {cap.valid_until_epoch}"

                result.append({
                    # Existing Permission interface fields (keep the page working)
                    "id":          cap.sui_object_id,
                    "agent":       owner_name or "—",
                    "stream":      cap.target_stream_id,
                    "verbs":       verbs,
                    "granted_at":  cap.created_at,
                    "valid_until": valid_until_str,
                    # Additive — frontend can use these as it wants
                    "capability_id":     cap.sui_object_id,
                    "agent_name":        owner_name or "—",
                    "stream_name":       owner_name or cap.target_stream_id,
                    "bitmask":           cap.verb_bitmask,
                    "valid_until_label": valid_until_label,
                    "sui_object_url": (
                        f"https://suiscan.xyz/testnet/object/{cap.sui_object_id}"
                    ),
                })
    except Exception as exc:
        logger.warning("list_permissions failed: %s", exc)
        return []

    return result


@app.post("/api/permissions")
async def delegate_permission(body: dict[str, Any]) -> dict[str, Any]:
    """Delegate a Sui capability token via SuiIdentityAdapter."""
    try:
        identity = getattr(runtime, "_identity", None)
        if identity is None or not identity.is_connected:
            return {"error": "Sui wallet not connected"}

        cfg = runtime._config
        if not cfg.package_id:
            return {"error": "WALRUSOS_PACKAGE_ID not configured"}

        digest = await identity.delegate_capability(
            target_stream_address=body.get("stream_id", ""),
            bitmask=int(body.get("bitmask", 3)),
            recipient=body.get("recipient", ""),
            package_id=cfg.package_id,
            valid_until_epoch=int(body.get("valid_until_epoch", 0)),
        )
        return {"digest": digest, "granted_at": datetime.now(timezone.utc).isoformat(), **body}
    except Exception as exc:
        return {"error": str(exc)}


@app.delete("/api/permissions/{cap_id}")
async def revoke_permission(cap_id: str) -> dict[str, str]:
    """Revoke a Sui capability token (destroys the on-chain object)."""
    try:
        identity = getattr(runtime, "_identity", None)
        if identity is None or not identity.is_connected:
            return {"error": "Sui wallet not connected"}

        cfg = runtime._config
        if not cfg.package_id:
            return {"error": "WALRUSOS_PACKAGE_ID not configured"}

        digest = await identity.revoke_capability(cap_id, cfg.package_id)
        return {"status": "revoked", "id": cap_id, "digest": digest}
    except Exception as exc:
        return {"error": str(exc)}


# ── Stats Endpoint ───────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    """Aggregate counts for the overview dashboard."""
    sqlite = _get_sqlite()
    if sqlite is None:
        return {"agents": 0, "streams": 0, "events": 0, "blobs": 0, "sui_anchors": 0}

    from walrusos.adapters.sqlite_ledger import (
        AgentIdentityRecord, MemoryStreamRecord, ProtocolEventRecord, MemoryEventRecord,
    )
    from sqlmodel import Session, select, func

    try:
        with Session(sqlite._engine) as session:
            agents      = session.exec(select(func.count()).select_from(AgentIdentityRecord)).one()
            streams     = session.exec(select(func.count()).select_from(MemoryStreamRecord)).one()
            events      = session.exec(
                select(func.count()).select_from(ProtocolEventRecord).where(
                    ProtocolEventRecord.event_type == "MemoryAppended"
                )
            ).one()
            # Blobs: every MemoryAppended event written end-to-end has a Walrus blob.
            # Anchors: count the SAME set of events that also have a real Sui digest.
            # transaction_digest may be NULL (mock mode, not anchored) or "" (anchor
            # attempted but failed) — exclude both so we count only real anchors.
            blobs = session.exec(
                select(func.count()).select_from(ProtocolEventRecord)
                .where(ProtocolEventRecord.event_type == "MemoryAppended")
                .where(ProtocolEventRecord.blob_id.isnot(None))
                .where(ProtocolEventRecord.blob_id != "")
            ).one()
            sui_anchors = session.exec(
                select(func.count()).select_from(ProtocolEventRecord)
                .where(ProtocolEventRecord.event_type == "MemoryAppended")
                .where(ProtocolEventRecord.transaction_digest.isnot(None))
                .where(ProtocolEventRecord.transaction_digest != "")
            ).one()
        return {"agents": agents, "streams": streams, "events": events,
                "blobs": blobs, "sui_anchors": sui_anchors}
    except Exception as exc:
        logger.warning("get_stats failed: %s", exc)
        return {"agents": 0, "streams": 0, "events": 0, "blobs": 0, "sui_anchors": 0}


# ── All Agents (no workspace filter) ─────────────────────────────────────────

@app.get("/api/agents")
async def list_all_agents() -> list[dict[str, Any]]:
    """List every known agent across all workspaces."""
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import AgentIdentityRecord
    from sqlmodel import Session, select

    result = []
    try:
        with Session(sqlite._engine) as session:
            agents = session.exec(select(AgentIdentityRecord)).all()
            for a in agents:
                result.append({
                    "id":                a.agent_id,
                    "name":              a.agent_name,
                    "workspace_id":      a.workspace_id,
                    "status":            a.status,
                    "execution_counter": a.execution_counter,
                    "memory_counter":    a.memory_counter,
                    "artifact_counter":  a.artifact_counter,
                    "public_key":        a.public_key,
                    "trust_root":        a.trust_root,
                    "sui_object_id":     a.sui_object_id,
                    "created_at":        a.created_at,
                })
    except Exception as exc:
        logger.warning("list_all_agents failed: %s", exc)
    return result


# ── Activity Feed ─────────────────────────────────────────────────────────────

@app.get("/api/activity")
async def get_activity(limit: int = 20) -> list[dict[str, Any]]:
    """Recent protocol events with agent names + framework for the activity feed."""
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import ProtocolEventRecord, AgentIdentityRecord
    from sqlmodel import Session, select

    # Framework is session-state — pull from the in-process registry + presence
    # store. Both are keyed by agent_id. Falls back to "" when an event's agent
    # is offline / never went online.
    from walrusos.runtime.registry import get_registry as _get_registry
    from walrusos.runtime.presence  import get_presence_store as _get_presence
    framework_by_agent: dict[str, str] = {}
    try:
        for reg in _get_registry().list_all():
            framework_by_agent[reg.agent_id] = reg.framework
    except Exception:
        pass
    try:
        for sess in _get_presence().list_sessions():
            if sess.agent_id not in framework_by_agent:
                framework_by_agent[sess.agent_id] = sess.framework
    except Exception:
        pass

    result = []
    try:
        with Session(sqlite._engine) as session:
            agents      = session.exec(select(AgentIdentityRecord)).all()
            agent_names = {a.agent_id: a.agent_name for a in agents}

            events = session.exec(
                select(ProtocolEventRecord)
                .order_by(ProtocolEventRecord.timestamp.desc())
                .limit(limit)
            ).all()

            for ev in events:
                payload: dict = {}
                try:
                    payload = json.loads(ev.payload_json)
                except Exception:
                    pass

                agent_name = agent_names.get(
                    ev.agent_id or "",
                    payload.get("author", "Unknown"),
                )
                framework = framework_by_agent.get(ev.agent_id or "", "")
                result.append({
                    "id":          ev.event_id,
                    "event_type":  ev.event_type,
                    "agent_id":    ev.agent_id or "",
                    "agent_name":  agent_name,
                    "framework":   framework,
                    "workspace_id": ev.workspace_id,
                    "stream_id":   payload.get("stream_id", ""),
                    "blob_id":     ev.blob_id or "",
                    "timestamp":   ev.timestamp,
                    "tx_digest":   ev.transaction_digest or "",
                })
    except Exception as exc:
        logger.warning("get_activity failed: %s", exc)
    return result


# ── Workspace Sync ────────────────────────────────────────────────────────────

@app.get("/api/workspace/sync")
async def sync_workspace_endpoint() -> dict[str, Any]:
    """Trigger a workspace sync against Walrus/Sui."""
    try:
        ws = runtime.workspace("default")
        if hasattr(ws, "sync"):
            await ws.sync()
        return {"status": "synced", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ── Protocol Explorer — Walrus Blob ──────────────────────────────────────────

@app.get("/api/explorer/blob/{blob_id:path}")
async def explore_blob(blob_id: str) -> dict[str, Any]:
    """Fetch a Walrus blob directly via httpx and decode its WalrusOS envelope."""
    import httpx as _httpx
    import gzip as _gzip
    import json as _json

    aggregator = "https://aggregator.walrus-testnet.walrus.space"
    try:
        async with _httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{aggregator}/v1/blobs/{blob_id}")

        if resp.status_code == 404:
            return {"found": False, "blob_id": blob_id, "error": "Blob not found on Walrus"}
        if resp.status_code != 200:
            return {"found": False, "blob_id": blob_id, "error": f"Walrus returned HTTP {resp.status_code}"}

        raw = resp.content

        # Try gzip-decompressed JSON first, then raw JSON, then give up
        envelope: dict = {}
        try:
            envelope = _json.loads(_gzip.decompress(raw))
        except Exception:
            try:
                envelope = _json.loads(raw)
            except Exception:
                envelope = {"raw": raw.decode("utf-8", errors="replace")}

        event = envelope.get("event", envelope)
        return {
            "found":       True,
            "blob_id":     blob_id,
            "size_bytes":  len(raw),
            "walrus_url":  f"{aggregator}/v1/blobs/{blob_id}",
            "event_id":    event.get("event_id", ""),
            "agent_id":    event.get("agent_id", ""),
            "stream_id":   event.get("stream_id", ""),
            "content":     event.get("content", ""),
            "timestamp":   event.get("timestamp", ""),
            "memory_type": event.get("memory_type", "observation"),
            "tags":        event.get("tags", []),
            "hash":        envelope.get("hash", ""),
            "signature":   envelope.get("signature", ""),
            "public_key":  event.get("public_key", ""),
        }
    except Exception as exc:
        return {"found": False, "blob_id": blob_id, "error": str(exc)}


# ── Protocol Explorer — Sui Object ────────────────────────────────────────────

@app.get("/api/explorer/object/{object_id}")
async def explore_object(object_id: str) -> dict[str, Any]:
    """Query a Sui object by ID via JSON-RPC."""
    import httpx as _httpx

    rpc_url = "https://fullnode.testnet.sui.io:443"
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method":  "sui_getObject",
        "params":  [
            object_id,
            {"showContent": True, "showOwner": True, "showType": True,
             "showPreviousTransaction": True},
        ],
    }
    try:
        async with _httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(rpc_url, json=payload)
            body = resp.json()

        if "error" in body:
            return {"found": False, "object_id": object_id, "error": str(body["error"])}

        data = (body.get("result") or {}).get("data")
        if not data:
            return {"found": False, "object_id": object_id, "error": "Object not found"}

        raw_owner = data.get("owner", {})
        if isinstance(raw_owner, dict):
            if "AddressOwner" in raw_owner:
                owner_str = raw_owner["AddressOwner"]
            elif "ObjectOwner" in raw_owner:
                owner_str = raw_owner["ObjectOwner"]
            elif "Shared" in raw_owner:
                owner_str = "Shared"
            else:
                owner_str = str(raw_owner)
        else:
            owner_str = str(raw_owner)

        content = data.get("content") or {}
        fields  = content.get("fields", {}) if isinstance(content, dict) else {}

        return {
            "found":            True,
            "object_id":        object_id,
            "object_type":      data.get("type", ""),
            "owner":            owner_str,
            "version":          data.get("version", ""),
            "digest":           data.get("digest", ""),
            "fields":           fields,
            "sui_explorer_url": f"https://suiexplorer.com/object/{object_id}?network=testnet",
        }
    except Exception as exc:
        return {"found": False, "object_id": object_id, "error": str(exc)}


# ── Agent/Stream Graph Data ───────────────────────────────────────────────────

@app.get("/api/graph-data")
async def get_graph_data() -> dict[str, Any]:
    """
    Build nodes + edges for the ReactFlow agent graph.
    Nodes: agents (violet) and streams (slate).
    Edges: agent → stream "published" relationships from MemoryStreamRecord.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return {"nodes": [], "edges": []}

    from walrusos.adapters.sqlite_ledger import AgentIdentityRecord, MemoryStreamRecord
    from sqlmodel import Session, select

    nodes: list[dict] = []
    edges: list[dict] = []

    try:
        with Session(sqlite._engine) as session:
            agents  = session.exec(select(AgentIdentityRecord)).all()
            streams = session.exec(select(MemoryStreamRecord)).all()

            agent_ids = set()
            for a in agents:
                agent_ids.add(a.agent_id)
                nodes.append({
                    "id":              a.agent_id,
                    "label":           a.agent_name,
                    "type":            "agent",
                    "status":          a.status,
                    "event_count":     a.memory_counter,
                    "execution_count": a.execution_counter,
                    "public_key":      a.public_key,
                    "created_at":      a.created_at,
                    "sui_object_id":   a.sui_object_id,
                })

            seen_streams: set[str] = set()
            for s in streams:
                if s.stream_id not in seen_streams:
                    seen_streams.add(s.stream_id)
                    nodes.append({
                        "id":          s.stream_id,
                        "label":       s.stream_id[:12] + "…",
                        "type":        "stream",
                        "event_count": s.epoch_counter,
                        "head":        s.head_event_id,
                        "created_at":  s.created_at,
                    })

                if s.agent_id in agent_ids:
                    edges.append({
                        "id":     f"{s.agent_id}->{s.stream_id}",
                        "source": s.agent_id,
                        "target": s.stream_id,
                        "label":  "published",
                        "count":  s.epoch_counter,
                    })
    except Exception as exc:
        logger.warning("get_graph_data failed: %s", exc)

    return {"nodes": nodes, "edges": edges}


# ── Paginated Memory Events ───────────────────────────────────────────────────

_INTERNAL_PAYLOAD_KEYS = frozenset({
    "author", "agent_id", "trust_root", "public_key", "workspace_id",
    "stream_id", "class_type", "memory_type", "tags", "importance",
    "summary", "project",
})

@app.get("/api/memory/events")
async def get_memory_events(
    stream:      Optional[str] = None,
    agent:       Optional[str] = None,
    memory_type: Optional[str] = None,
    limit:       int = 50,
    offset:      int = 0,
) -> list[dict[str, Any]]:
    """
    Paginated memory events from ProtocolEventRecord (event_type=MemoryAppended).
    Returns rich payload data without requiring Walrus downloads.
    """
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import ProtocolEventRecord, AgentIdentityRecord
    from sqlmodel import Session, select

    result: list[dict] = []
    try:
        with Session(sqlite._engine) as session:
            agents      = session.exec(select(AgentIdentityRecord)).all()
            agent_names = {a.agent_id: a.agent_name for a in agents}

            query = (
                select(ProtocolEventRecord)
                .where(ProtocolEventRecord.event_type == "MemoryAppended")
                .order_by(ProtocolEventRecord.timestamp.desc())
                .offset(offset)
                .limit(limit)
            )
            if agent:
                query = query.where(ProtocolEventRecord.agent_id == agent)

            events = session.exec(query).all()

            for ev in events:
                payload: dict = {}
                try:
                    payload = json.loads(ev.payload_json)
                except Exception:
                    pass

                sid   = payload.get("stream_id", "")
                mtype = payload.get("memory_type") or payload.get("class_type", "observation")

                if stream and stream not in sid:
                    continue
                if memory_type and mtype != memory_type:
                    continue

                agent_name = agent_names.get(
                    ev.agent_id or "",
                    payload.get("author", "Unknown"),
                )

                content = {k: v for k, v in payload.items()
                           if k not in _INTERNAL_PAYLOAD_KEYS}

                result.append({
                    "id":           ev.event_id,
                    "agent_id":     ev.agent_id or "",
                    "agent_name":   agent_name,
                    "stream_id":    sid,
                    "memory_type":  mtype,
                    "tags":         payload.get("tags", []),
                    "importance":   payload.get("importance", 0.5),
                    "summary":      payload.get("summary", ""),
                    "content":      content,
                    "blob_id":      ev.blob_id or "",
                    "event_hash":   ev.blob_hash or "",
                    "signature":    ev.signature or "",
                    "public_key":   payload.get("public_key", ""),
                    "verified":     bool(ev.signature),
                    "timestamp":    ev.timestamp,
                    "tx_digest":    ev.transaction_digest or "",
                    "workspace_id": ev.workspace_id,
                })
    except Exception as exc:
        logger.warning("get_memory_events failed: %s", exc)

    return result


# ── Tasks (Kanban) ───────────────────────────────────────────────────────────

@app.get("/api/tasks")
async def list_tasks() -> list[dict[str, Any]]:
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import TaskRecord, AgentIdentityRecord
    from sqlmodel import Session, select

    result: list[dict] = []
    try:
        with Session(sqlite._engine) as session:
            agents      = session.exec(select(AgentIdentityRecord)).all()
            agent_names = {a.agent_id: a.agent_name for a in agents}

            tasks = session.exec(select(TaskRecord).order_by(TaskRecord.created_at.desc())).all()
            for t in tasks:
                result.append({
                    "id":               t.task_id,
                    "workspace_id":     t.workspace_id,
                    "title":            t.title,
                    "description":      t.description,
                    "created_by":       t.created_by,
                    "created_by_name":  agent_names.get(t.created_by, t.created_by[:8] + "…"),
                    "assigned_to":      t.assigned_to,
                    "assigned_to_name": agent_names.get(t.assigned_to or "", "") if t.assigned_to else None,
                    "status":           t.status,
                    "priority":         t.priority,
                    "tags":             json.loads(t.tags) if t.tags else [],
                    "notes":            t.notes,
                    "created_at":       t.created_at,
                    "updated_at":       t.updated_at,
                    "completed_at":     t.completed_at,
                })
    except Exception as exc:
        logger.warning("list_tasks failed: %s", exc)
    return result


@app.post("/api/tasks")
async def create_task(body: dict[str, Any]) -> dict[str, Any]:
    sqlite = _get_sqlite()
    if sqlite is None:
        return {"error": "No database"}

    from walrusos.adapters.sqlite_ledger import TaskRecord
    from sqlmodel import Session

    try:
        with Session(sqlite._engine) as session:
            task = TaskRecord(
                task_id=str(uuid.uuid4()),
                workspace_id=body.get("workspace_id", "default"),
                title=body.get("title", "Untitled"),
                description=body.get("description", ""),
                created_by=body.get("created_by", ""),
                assigned_to=body.get("assigned_to") or None,
                status=body.get("status", "pending"),
                priority=int(body.get("priority", 3)),
                tags=json.dumps(body.get("tags", [])),
                notes=body.get("notes", ""),
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return {"id": task.task_id, "title": task.title, "status": task.status}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/tasks/{task_id}/status")
async def update_task_status(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    sqlite = _get_sqlite()
    if sqlite is None:
        return {"error": "No database"}

    from walrusos.adapters.sqlite_ledger import TaskRecord
    from sqlmodel import Session

    try:
        with Session(sqlite._engine) as session:
            task = session.get(TaskRecord, task_id)
            if not task:
                return {"error": "Task not found"}
            task.status     = body.get("status", task.status)
            task.updated_at = datetime.now(timezone.utc).isoformat()
            if task.status == "done" and not task.completed_at:
                task.completed_at = task.updated_at
            session.add(task)
            session.commit()
            return {"id": task_id, "status": task.status}
    except Exception as exc:
        return {"error": str(exc)}


# ── Memory Search ─────────────────────────────────────────────────────────────

@app.get("/api/memory/search")
async def memory_search(q: str = "", limit: int = 20) -> list[dict[str, Any]]:
    if not q.strip():
        return []

    import time as _time
    t0 = _time.monotonic()

    sqlite = _get_sqlite()
    agent_names: dict[str, str] = {}
    if sqlite:
        from walrusos.adapters.sqlite_ledger import AgentIdentityRecord
        from sqlmodel import Session, select
        with Session(sqlite._engine) as session:
            agents      = session.exec(select(AgentIdentityRecord)).all()
            agent_names = {a.agent_id: a.agent_name for a in agents}

    try:
        raw = await runtime._engine.semantic_search(q, limit=limit)
    except Exception as exc:
        logger.warning("memory_search engine error: %s", exc)
        raw = []

    elapsed_ms = round((_time.monotonic() - t0) * 1000, 1)

    return [
        {
            "id":            r.get("doc_id", ""),
            "score":         round(r.get("score", 0.0), 4),
            "text":          r.get("text", ""),
            "stream_id":     (r.get("metadata") or {}).get("stream_id", ""),
            "agent_id":      (r.get("metadata") or {}).get("agent_id", ""),
            "agent_name":    agent_names.get((r.get("metadata") or {}).get("agent_id", ""), "Unknown"),
            "memory_type":   (r.get("metadata") or {}).get("memory_type", "observation"),
            "timestamp":     (r.get("metadata") or {}).get("timestamp", ""),
            "search_time_ms": elapsed_ms,
        }
        for r in raw
    ]


# ── Snapshots (summary checkpoints) ──────────────────────────────────────────

@app.get("/api/snapshots")
async def list_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    sqlite = _get_sqlite()
    if sqlite is None:
        return []

    from walrusos.adapters.sqlite_ledger import ProtocolEventRecord, AgentIdentityRecord
    from sqlmodel import Session, select

    result: list[dict] = []
    try:
        with Session(sqlite._engine) as session:
            agents      = session.exec(select(AgentIdentityRecord)).all()
            agent_names = {a.agent_id: a.agent_name for a in agents}

            events = session.exec(
                select(ProtocolEventRecord)
                .where(ProtocolEventRecord.event_type == "MemoryAppended")
                .order_by(ProtocolEventRecord.timestamp.desc())
                .limit(limit * 10)
            ).all()

            for ev in events:
                payload: dict = {}
                try:
                    payload = json.loads(ev.payload_json)
                except Exception:
                    pass

                mtype = (payload.get("memory_type") or payload.get("class_type", "")).lower()
                if "summary" not in mtype:
                    continue

                agent_name = agent_names.get(
                    ev.agent_id or "",
                    payload.get("author", "Unknown"),
                )
                content = {k: v for k, v in payload.items() if k not in _INTERNAL_PAYLOAD_KEYS}
                result.append({
                    "id":         ev.event_id,
                    "agent_id":   ev.agent_id or "",
                    "agent_name": agent_name,
                    "stream_id":  payload.get("stream_id", ""),
                    "summary":    payload.get("summary", ""),
                    "content":    content,
                    "blob_id":    ev.blob_id or "",
                    "timestamp":  ev.timestamp,
                    "tags":       payload.get("tags", []),
                })
                if len(result) >= limit:
                    break
    except Exception as exc:
        logger.warning("list_snapshots failed: %s", exc)
    return result


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    cfg             = runtime._config
    package_id      = getattr(cfg, "package_id", "") or ""
    ledger_anchor   = "0x0f96188ee403ecc58bd498fb874ef3037078775deb68e2061964ac1d3827e27d"
    identity        = getattr(runtime, "_identity", None)
    wallet          = (getattr(identity, "active_address", "") or "") if identity else ""

    claude_config = json.dumps({
        "mcpServers": {
            "walrusos": {"command": "walrusos", "args": ["mcp", "start"]}
        }
    }, indent=2)

    cursor_config = json.dumps({
        "mcpServers": {
            "walrusos": {"command": "walrusos", "args": ["mcp", "start"], "env": {}}
        }
    }, indent=2)

    return {
        "package_id":            package_id,
        "ledger_anchor_id":      ledger_anchor,
        "wallet":                wallet,
        "network":               "testnet",
        "publisher_url":         getattr(cfg, "publisher_url", "") or "",
        "aggregator_url":        getattr(cfg, "aggregator_url", "") or "",
        "db_path":               getattr(cfg, "db_path", "") or "",
        "mcp_status":            "available",
        "claude_desktop_config": claude_config,
        "cursor_config":         cursor_config,
        "sui_explorer_package":  f"https://suiexplorer.com/object/{package_id}?network=testnet",
        "sui_explorer_ledger":   f"https://suiexplorer.com/object/{ledger_anchor}?network=testnet",
    }


# ── Recovery Demo — SSE Stream ────────────────────────────────────────────────

@app.get("/api/recovery/run")
async def run_recovery_demo():
    """Stream demo_recovery.py output as Server-Sent Events."""
    import asyncio
    import os
    import sys
    from fastapi.responses import StreamingResponse

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script       = os.path.join(project_root, "scripts", "demo_recovery.py")

    async def generate():
        if not os.path.isfile(script):
            yield f"data: {json.dumps({'line': f'Script not found: {script}', 'error': True})}\n\n"
            yield f"data: {json.dumps({'done': True, 'returncode': 1})}\n\n"
            return

        env = {**os.environ, "WALRUSOS_USE_MOCKS": "1"}
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                yield f"data: {json.dumps({'line': line})}\n\n"
            await proc.wait()
            yield f"data: {json.dumps({'done': True, 'returncode': proc.returncode})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'line': str(exc), 'error': True})}\n\n"
            yield f"data: {json.dumps({'done': True, 'returncode': 1})}\n\n"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Agent Session / Presence Endpoints ───────────────────────────────────────

class SessionStartRequest(BaseModel):
    agent_id:     str
    agent_name:   str
    workspace_id: str
    framework:    str = "custom"
    session_id:   Optional[str] = None
    capabilities: list[dict]    = []
    tools:        list[str]     = []


class HeartbeatRequest(BaseModel):
    session_token:       str
    agent_id:            str
    status:              Optional[str] = None
    memory_writes_delta: int = 0
    memory_reads_delta:  int = 0
    tasks_delta:         int = 0


class SessionEndRequest(BaseModel):
    session_token: str
    agent_id:      str


@app.post("/internal/event")
async def internal_event(body: dict) -> dict[str, Any]:
    """Called by EventMesh to forward topic events to WebSocket clients."""
    message = json.dumps({"type": "mesh_event", **body})
    dead: list[WebSocket] = []
    for ws in list(_event_subscribers):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _event_subscribers:
            _event_subscribers.remove(ws)
    return {"ok": True}


@app.post("/agent/session/start")
async def session_start(req: SessionStartRequest) -> dict[str, Any]:
    store = get_presence_store()
    session = await store.register(
        agent_id=req.agent_id,
        agent_name=req.agent_name,
        workspace_id=req.workspace_id,
        framework=req.framework,
        session_id=req.session_id,
    )
    # Register capabilities in the agent registry
    from walrusos.runtime.registry import get_registry, AgentRegistration, AgentCapability
    registry = get_registry()
    caps = [AgentCapability(**c) for c in req.capabilities]
    await registry.register(AgentRegistration(
        agent_id=req.agent_id,
        agent_name=req.agent_name,
        framework=req.framework,
        workspace_id=req.workspace_id,
        capabilities=caps,
        tools_exposed=req.tools,
    ))

    return {"session_token": session.session_id, "status": "connected"}


async def _auto_recover_session(req: "HeartbeatRequest") -> "AgentSession":
    """Register a minimal session for an agent that's heartbeating but isn't
    in the in-process PresenceStore — happens when the bridge restarts after a
    client has already started its session.

    Best-effort metadata recovery:
      - agent_name + workspace_id: from agent_identities (persisted in SQLite)
      - framework:                 from the in-process AgentRegistry, if still set
      - fallbacks: agent_id as name, "default" workspace, "unknown" framework

    Uses req.session_token as the session_id so the recovered session links
    back to the token the client is already using.
    """
    from walrusos.runtime.presence import get_presence_store as _gps
    store = _gps()

    agent_name   = req.agent_id  # placeholder if nothing better is found
    workspace_id = "default"
    framework    = "unknown"

    sqlite = _get_sqlite()
    if sqlite is not None:
        from walrusos.adapters.sqlite_ledger import AgentIdentityRecord
        from sqlmodel import Session, select
        try:
            with Session(sqlite._engine) as s:
                ident = s.exec(
                    select(AgentIdentityRecord).where(
                        AgentIdentityRecord.agent_id == req.agent_id
                    )
                ).first()
                if ident:
                    agent_name   = ident.agent_name or agent_name
                    workspace_id = ident.workspace_id or workspace_id
        except Exception as exc:
            logger.debug("auto-recover identity lookup failed: %s", exc)

    try:
        from walrusos.runtime.registry import get_registry as _gr
        reg = _gr().get(req.agent_id)
        if reg:
            framework = reg.framework or framework
    except Exception as exc:
        logger.debug("auto-recover registry lookup failed: %s", exc)

    return await store.register(
        agent_id=req.agent_id,
        agent_name=agent_name,
        workspace_id=workspace_id,
        framework=framework,
        session_id=req.session_token,
    )


@app.post("/agent/session/heartbeat")
async def session_heartbeat(req: HeartbeatRequest) -> dict[str, Any]:
    """Apply a heartbeat. If the agent isn't yet known to this bridge process
    (e.g. the bridge restarted but the client kept heartbeating), auto-recover
    a minimal session and apply the heartbeat — return 200 either way so the
    live client doesn't need to detect a server restart.
    """
    store = get_presence_store()
    recovered = False
    try:
        session = await store.heartbeat(
            agent_id=req.agent_id,
            status=req.status,  # type: ignore[arg-type]
            memory_writes_delta=req.memory_writes_delta,
            memory_reads_delta=req.memory_reads_delta,
            tasks_delta=req.tasks_delta,
        )
    except KeyError:
        logger.info(
            "Heartbeat for unknown agent %s — auto-recovering session "
            "(bridge likely restarted after client connected)",
            req.agent_id[:16],
        )
        await _auto_recover_session(req)
        session = await store.heartbeat(
            agent_id=req.agent_id,
            status=req.status,  # type: ignore[arg-type]
            memory_writes_delta=req.memory_writes_delta,
            memory_reads_delta=req.memory_reads_delta,
            tasks_delta=req.tasks_delta,
        )
        recovered = True
    return {
        "ok":             True,
        "last_heartbeat": session.last_heartbeat.isoformat(),
        "recovered":      recovered,
    }


@app.post("/agent/session/end")
async def session_end(req: SessionEndRequest) -> dict[str, Any]:
    store = get_presence_store()
    await store.unregister(req.agent_id)
    from walrusos.runtime.registry import get_registry
    await get_registry().unregister(req.agent_id)
    return {"ok": True}


@app.get("/agent/registry")
async def agent_registry() -> list[dict[str, Any]]:
    from walrusos.runtime.registry import get_registry
    return [r.model_dump() for r in get_registry().list_all()]


@app.get("/agent/discover")
async def agent_discover(
    capability: Optional[str] = None,
    framework:  Optional[str] = None,
) -> list[dict[str, Any]]:
    from walrusos.runtime.registry import get_registry
    registry = get_registry()
    if capability:
        results = registry.find_by_capability(capability)
    elif framework:
        results = registry.find_by_framework(framework)
    else:
        results = registry.list_all()
    return [r.model_dump() for r in results]


@app.get("/agent/presence")
async def agent_presence(workspace_id: Optional[str] = None) -> list[dict[str, Any]]:
    store = get_presence_store()
    sessions = store.list_sessions(workspace_id=workspace_id)
    return [s.model_dump(mode="json") for s in sessions]


# ── Live Events WebSocket ─────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    """
    Stream real runtime events over WebSocket.

    Events are emitted whenever the runtime appends a MemoryEvent.
    Without a real pub/sub bus, we poll the SQLite head pointer for each
    known stream every 2 seconds and emit new events as they appear.
    """
    await websocket.accept()
    _event_subscribers.append(websocket)

    # ── Presence integration ───────────────────────────────────────────────────
    store = get_presence_store()

    async def broadcast_to_client(message: str) -> None:
        try:
            await websocket.send_text(message)
        except Exception:
            pass

    store.subscribe(broadcast_to_client)

    # Send current presence snapshot immediately on connect
    try:
        sessions = store.list_sessions()
        await websocket.send_text(json.dumps({
            "type":   "presence_snapshot",
            "agents": [s.model_dump(mode="json") for s in sessions],
        }))
    except Exception:
        pass

    sqlite = _get_sqlite()
    # Track last-seen epoch per stream to only emit genuinely new events
    last_epoch: dict[str, int] = {}

    try:
        while True:
            if sqlite is not None:
                from walrusos.adapters.sqlite_ledger import (
                    MemoryStreamRecord, MemoryEventRecord,
                )
                from sqlmodel import Session, select

                try:
                    with Session(sqlite._engine) as session:
                        streams = session.exec(select(MemoryStreamRecord)).all()
                        for s in streams:
                            prev = last_epoch.get(s.stream_id, 0)
                            if s.epoch_counter > prev:
                                # Emit every new event since last poll
                                new_evs = session.exec(
                                    select(MemoryEventRecord)
                                    .where(MemoryEventRecord.stream_id == s.stream_id)
                                    .where(MemoryEventRecord.epoch > prev)
                                    .order_by(MemoryEventRecord.epoch)
                                ).all()
                                for ev in new_evs:
                                    await websocket.send_json({
                                        "id":         ev.id[:16],
                                        "type":       f"memory.{ev.class_type}",
                                        "stream":     s.stream_id[:12],
                                        "agent":      s.agent_id[:12],
                                        "epoch":      ev.epoch,
                                        "blob_id":    ev.content_blob_id[:16],
                                        "timestamp":  ev.created_at,
                                    })
                                last_epoch[s.stream_id] = s.epoch_counter
                except Exception as exc:
                    logger.debug("events_ws poll error: %s", exc)

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _event_subscribers:
            _event_subscribers.remove(websocket)
        store.unsubscribe(broadcast_to_client)


# ── Coordination Plan Endpoints ───────────────────────────────────────────────
# In-memory store of recent coordination plans (last 20, keyed by goal_id).
_coordination_plans: dict[str, dict] = {}
_MAX_COORDINATION_PLANS = 20


async def _broadcast_coordination(msg: dict) -> None:
    """Send a coordination update to all WebSocket subscribers."""
    text = json.dumps(msg)
    dead: list[WebSocket] = []
    for ws in list(_event_subscribers):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _event_subscribers:
            _event_subscribers.remove(ws)


@app.post("/internal/coordination/plan")
async def internal_coordination_plan(body: dict) -> dict[str, Any]:
    """Called by workspace.coordinate() to register a new plan."""
    goal_id = body.get("goal_id", "")
    if goal_id:
        _coordination_plans[goal_id] = body
        # Keep only the last N plans
        if len(_coordination_plans) > _MAX_COORDINATION_PLANS:
            oldest = next(iter(_coordination_plans))
            del _coordination_plans[oldest]
    await _broadcast_coordination({"type": "coordination_plan", **body})
    return {"ok": True}


@app.post("/internal/coordination/task_update")
async def internal_coordination_task_update(body: dict) -> dict[str, Any]:
    """Called after each task completes or changes status."""
    goal_id = body.get("goal_id", "")
    task_id = body.get("task_id", "")
    if goal_id in _coordination_plans:
        plan = _coordination_plans[goal_id]
        for task in plan.get("tasks", []):
            if task.get("task_id") == task_id:
                task.update({
                    "status":           body.get("status", task.get("status")),
                    "assigned_to_name": body.get("assigned_to_name", task.get("assigned_to_name")),
                    "result_content":   body.get("result_content", task.get("result_content")),
                })
    await _broadcast_coordination({"type": "coordination_task", **body})
    return {"ok": True}


@app.get("/api/coordination/plans")
async def list_coordination_plans() -> list[dict[str, Any]]:
    """Return the last 10 coordination plans (summary, no full task results)."""
    plans = list(_coordination_plans.values())[-10:]
    return [
        {
            "goal_id":         p.get("goal_id", ""),
            "goal":            p.get("goal", ""),
            "status":          p.get("status", ""),
            "tasks_total":     len(p.get("tasks", [])),
            "tasks_completed": sum(1 for t in p.get("tasks", []) if t.get("status") == "done"),
            "created_at":      p.get("created_at", ""),
        }
        for p in plans
    ]


@app.get("/api/coordination/plans/{goal_id}")
async def get_coordination_plan(goal_id: str) -> dict[str, Any]:
    """Return one coordination plan with its full task graph."""
    plan = _coordination_plans.get(goal_id)
    if not plan:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Plan {goal_id} not found")
    return plan
