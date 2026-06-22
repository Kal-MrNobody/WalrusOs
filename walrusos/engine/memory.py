"""
WalrusOS Memory Engine — epoch counter now reads from SQLite if the
ledger supports it, so counters survive process restarts.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter, VectorAdapter
from walrusos.core.models.memory import MemoryEvent


class MemoryEngine:
    """
    Core DAG traversal and mutation engine for AI Memory streams.

    Coordinates three adapters (storage, ledger, vector) to provide a
    high-level, transport-agnostic memory API.
    """

    def __init__(
        self,
        ledger:  LedgerAdapter,
        storage: StorageAdapter,
        vector:  VectorAdapter,
    ) -> None:
        self.ledger  = ledger
        self.storage = storage
        self.vector  = vector
        # In-process epoch cache.  Populated lazily from the ledger on first use.
        # For SQLiteLedger, the ledger's persisted counter is authoritative.
        self._epochs: Dict[uuid.UUID, int] = {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _next_epoch(self, stream_id: uuid.UUID) -> int:
        """
        Return the next epoch number for a stream.

        If the in-process cache is cold (0 or missing), and the ledger supports
        persistent epoch counters (``get_epoch_counter``), seed from the ledger.
        """
        if stream_id not in self._epochs:
            # Try to read persisted counter from SQLiteLedger
            if hasattr(self.ledger, "get_epoch_counter"):
                persisted = await self.ledger.get_epoch_counter(stream_id)  # type: ignore[attr-defined]
                self._epochs[stream_id] = persisted
            else:
                self._epochs[stream_id] = 0

        self._epochs[stream_id] += 1
        return self._epochs[stream_id]

    @staticmethod
    def _event_id(parent_id: str, blob_id: str, ts: str) -> str:
        """Deterministic SHA-256 event ID with a random nonce to prevent
        timing-based double-write collisions (CVE-WOS-007)."""
        nonce = os.urandom(8).hex()
        return hashlib.sha256(f"{parent_id}:{blob_id}:{ts}:{nonce}".encode()).hexdigest()

    # ── Stream registration ───────────────────────────────────────────────────

    async def register_stream(self, stream_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        """
        Register a deterministic stream UUID without generating a new one.

        Used by StreamClient so that name-based UUID5 IDs persist across
        process restarts via the SQLite ledger.
        """
        if hasattr(self.ledger, "register_stream"):
            await self.ledger.register_stream(stream_id, agent_id)  # type: ignore[attr-defined]
        else:
            # InMemoryLedger fallback: set directly
            if hasattr(self.ledger, "streams"):
                if stream_id not in self.ledger.streams:  # type: ignore[attr-defined]
                    self.ledger.streams[stream_id] = "genesis"  # type: ignore[attr-defined]

    # ── Core Operations ───────────────────────────────────────────────────────

    async def create_stream(self, agent_id: uuid.UUID) -> uuid.UUID:
        """Create a new MemoryStream and return its UUID."""
        return await self.ledger.create_stream(agent_id)

    async def delete_stream(self, stream_id: uuid.UUID) -> None:
        """Permanently delete a stream and all its events and blobs."""
        events = await self.ledger.list_events(stream_id)
        for ev in events:
            try:
                await self.storage.delete_blob(ev.content_blob_id)
            except Exception:
                pass
            try:
                await self.vector.delete(ev.id)
            except Exception:
                pass
        await self.ledger.delete_stream(stream_id)
        self._epochs.pop(stream_id, None)

    async def append(
        self,
        stream_id:    uuid.UUID,
        memory_type:  str,
        payload_dict: Dict[str, Any],
        agent_id:     Optional[str] = None,
        signature_block: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        summary: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        project: Optional[str] = None,
    ) -> MemoryEvent:
        """
        Append an immutable event to the stream.

        Steps:
          1. Workspace isolation check (CVE-WOS-005): verify stream_id belongs
             to workspace_id if both are supplied.
          2. Serialize payload to JSON bytes.
          3. Store blob → get content-addressed blob_id.
          4. Compute deterministic event_id from (parent, blob, timestamp, nonce).
          5. Create MemoryEvent (Phase 2: stamped with agent_id) and append to ledger.
          6. Upsert document text into vector index.
        """
        # ── CVE-WOS-005: Workspace isolation check ────────────────────────────
        # If a workspace_id is provided, confirm the stream belongs to it.
        # This prevents one workspace from injecting events into another workspace's
        # stream even if the stream UUID is known.
        if workspace_id is not None and hasattr(self.ledger, "get_stream_workspace"):
            stream_workspace = await self.ledger.get_stream_workspace(stream_id)  # type: ignore
            if stream_workspace is not None and stream_workspace != workspace_id:
                raise PermissionError(
                    f"Stream {stream_id} belongs to workspace '{stream_workspace}', "
                    f"not '{workspace_id}'. Cross-workspace write rejected."
                )

        parent_id     = await self.ledger.get_head(stream_id) or "genesis"

        # Embed signature if provided
        if signature_block:
            payload_dict["_signature"] = signature_block

        # Inject intelligence metadata into the Walrus blob payload
        payload_dict["_meta"] = {
            "tags": tags or [],
            "importance": importance,
            "summary": summary,
            "project": project,
            "memory_type": memory_type,
        }

        payload_bytes = json.dumps(payload_dict, default=str).encode("utf-8")
        blob_id       = await self.storage.store_blob(payload_bytes, "application/json")

        ts       = datetime.now(timezone.utc).isoformat()
        epoch    = await self._next_epoch(stream_id)

        # Use cryptographic event_hash if signed, otherwise fallback to blob+ts derivation
        event_id = signature_block["event_hash"] if signature_block else self._event_id(parent_id, blob_id, ts)

        event = MemoryEvent(
            id=event_id,
            stream_id=stream_id,
            parent_id=parent_id,
            epoch=epoch,
            memory_type=memory_type,
            tags=tags or [],
            importance=importance,
            summary=summary,
            embedding=embedding,
            project=project,
            content_blob_id=blob_id,
            # Phase 2: persistent agent attribution
            agent_id=agent_id,
            # Phase 3: crypto fields
            event_hash=signature_block["event_hash"] if signature_block else None,
            signature=signature_block["signature"] if signature_block else None,
            public_key=signature_block["public_key"] if signature_block else None,
        )
        await self.ledger.append_event(stream_id, event)

        # Index all string/numeric values for semantic search
        text = " ".join(
            str(v) for v in payload_dict.values() if isinstance(v, (str, int, float))
        )
        if text.strip():
            await self.vector.upsert(
                event_id, text, {
                    "stream_id": str(stream_id),
                    "epoch":     epoch,
                    "agent_id":  agent_id or "",
                }
            )

        return event

    async def read(self, event_id: str) -> Dict[str, Any]:
        """Fetch and deserialize the payload for a single event."""
        event = await self.ledger.get_event(event_id)
        if not event:
            raise KeyError(f"Event '{event_id}' not found")
        # ProtocolEvent (InMemory/EventStore mode): payload stored inline
        if hasattr(event, "payload") and event.payload:
            return event.payload
        # ProtocolEvent with blob_id but no inline payload
        if hasattr(event, "blob_id") and event.blob_id:
            raw = await self.storage.retrieve_blob(event.blob_id)
            return json.loads(raw.decode("utf-8"))
        # MemoryEvent (SQLite/Walrus mode): payload stored in Walrus blob
        if hasattr(event, "content_blob_id") and event.content_blob_id:
            raw = await self.storage.retrieve_blob(event.content_blob_id)
            return json.loads(raw.decode("utf-8"))
        return {}

    async def verify_event(self, event_id: str) -> bool:
        """
        Verify the cryptographic signature and payload integrity of an event.
        Returns True if valid, False if tampered or missing signature.
        """
        from walrusos.core.crypto import canonicalize_payload, hash_payload, verify_signature

        event = await self.ledger.get_event(event_id)
        if not event:
            raise KeyError(f"Event '{event_id}' not found")

        try:
            eid = getattr(event, "id", None) or getattr(event, "event_id", None)
            blob_id = getattr(event, "blob_id", None) or getattr(event, "content_blob_id", None)
            if blob_id:
                raw = await self.storage.retrieve_blob(blob_id)
                payload = json.loads(raw.decode("utf-8"))
            else:
                payload = await self.read(eid)
        except Exception:
            return False

        # Mode A: signature on the event object directly (ProtocolEvent mode)
        sig = getattr(event, "signature", None)
        if sig and sig not in ("v0_migration", "cli-unsigned", ""):
            payload_without_sig = {k: v for k, v in payload.items() if k != "_signature"}
            canonical_bytes = canonicalize_payload(payload_without_sig)
            computed_hash = hash_payload(canonical_bytes)
            
            pub_key = payload.get("public_key")
            if not pub_key:
                return False
                
            return verify_signature(
                public_key_hex=pub_key,
                event_hash_hex=computed_hash,
                signature_b64=sig
            )

        # Mode B: signature block in the payload (_signature) (MemoryEvent mode)
        sig_block = payload.get("_signature")
        if not sig_block:
            return False  # Not signed

        payload_without_sig = {k: v for k, v in payload.items() if k != "_signature"}
        canonical_bytes = canonicalize_payload(payload_without_sig)
        computed_hash = hash_payload(canonical_bytes)

        if computed_hash != sig_block["event_hash"]:
            return False  # Payload was tampered with (hash mismatch)

        return verify_signature(
            public_key_hex=sig_block["public_key"],
            event_hash_hex=computed_hash,
            signature_b64=sig_block["signature"]
        )

    async def timeline(
        self,
        stream_id: uuid.UUID,
    ) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Return the full stream history in chronological order."""
        events = await self.ledger.list_events(stream_id)
        result: List[Tuple[Any, Dict[str, Any]]] = []
        for event in events:
            try:
                # Use .id for MemoryEvent, .event_id for ProtocolEvent
                eid = getattr(event, "id", None) or getattr(event, "event_id", None)
                if eid:
                    payload = await self.read(eid)
                else:
                    payload = {}
            except (KeyError, json.JSONDecodeError):
                payload = {}
            result.append((event, payload))
        return result

    # ── DAG Branching ─────────────────────────────────────────────────────────

    async def fork(
        self,
        stream_id:     uuid.UUID,
        from_event_id: str,
        new_agent_id:  uuid.UUID,
    ) -> uuid.UUID:
        """Create a new stream that branches from a specific event."""
        event = await self.ledger.get_event(from_event_id)
        if not event:
            raise KeyError(f"Fork source event '{from_event_id}' not found")

        new_stream_id = await self.ledger.create_stream(new_agent_id)

        fork_payload = {
            "system":        "fork",
            "forked_from":   str(stream_id),
            "fork_event_id": from_event_id,
            "fork_epoch":    getattr(event, "epoch", 0),
        }
        await self.append(new_stream_id, "system", fork_payload)
        return new_stream_id

    async def merge(
        self,
        target_stream_id: uuid.UUID,
        source_stream_id: uuid.UUID,
    ) -> MemoryEvent:
        """
        Merge source_stream_id into target_stream_id.

        Creates a two-parent merge-commit whose parent_id is
        "<target_head>,<source_head>".
        """
        target_head = await self.ledger.get_head(target_stream_id) or "genesis"
        source_head = await self.ledger.get_head(source_stream_id) or "genesis"

        multi_parent  = f"{target_head},{source_head}"
        merge_payload: Dict[str, Any] = {
            "system":        "merge",
            "source_stream": str(source_stream_id),
            "source_head":   source_head,
            "target_head":   target_head,
        }
        payload_bytes = json.dumps(merge_payload, default=str).encode("utf-8")
        blob_id       = await self.storage.store_blob(payload_bytes, "application/json")

        ts       = datetime.now(timezone.utc).isoformat()
        event_id = self._event_id(multi_parent, blob_id, ts)
        epoch    = await self._next_epoch(target_stream_id)

        event = MemoryEvent(
            id=event_id,
            stream_id=target_stream_id,
            parent_id=multi_parent,
            epoch=epoch,
            class_type="system",  # type: ignore[arg-type]
            content_blob_id=blob_id,
        )
        await self.ledger.append_event(target_stream_id, event)
        return event

    # ── Replay ────────────────────────────────────────────────────────────────

    async def replay(
        self,
        stream_id:   uuid.UUID,
        up_to_epoch: Optional[int] = None,
        from_epoch:  int = 1,
    ) -> List[Dict[str, Any]]:
        """Replay all events, optionally bounded by epoch range."""
        tl = await self.timeline(stream_id)
        result = []
        for i, (ev, payload) in enumerate(tl, start=1):
            epoch = getattr(ev, "epoch", None) or i
            if epoch >= from_epoch and (up_to_epoch is None or epoch <= up_to_epoch):
                result.append(payload)
        return result

    # ── Checkpoint / Snapshot / Resume ────────────────────────────────────────

    async def checkpoint(self, stream_id: uuid.UUID) -> str:
        """Save a lightweight checkpoint (head + epoch) and return its blob_id."""
        head  = await self.ledger.get_head(stream_id) or "genesis"
        epoch = self._epochs.get(stream_id, 0)
        payload = {
            "type":      "checkpoint",
            "stream_id": str(stream_id),
            "head":      head,
            "epoch":     epoch,
            "ts":        datetime.now(timezone.utc).isoformat(),
        }
        return await self.storage.store_blob(
            json.dumps(payload).encode("utf-8"), "application/json"
        )

    async def snapshot(self, stream_id: uuid.UUID) -> str:
        """Save a full timeline snapshot and return its blob_id."""
        tl = await self.timeline(stream_id)
        events_data = [
            {
                "id":              getattr(ev, "id", None) or getattr(ev, "event_id", ""),
                "parent_id":       getattr(ev, "parent_id", None) or getattr(ev, "parent_event", ""),
                "epoch":           getattr(ev, "epoch", i),
                "class_type":      getattr(ev, "class_type", "episodic"),
                "content_blob_id": getattr(ev, "content_blob_id", None) or getattr(ev, "blob_id", ""),
                "payload":         payload,
            }
            for i, (ev, payload) in enumerate(tl, start=1)
        ]
        snapshot_payload = {
            "type":      "snapshot",
            "stream_id": str(stream_id),
            "events":    events_data,
            "ts":        datetime.now(timezone.utc).isoformat(),
        }
        return await self.storage.store_blob(
            json.dumps(snapshot_payload, default=str).encode("utf-8"),
            "application/json",
        )

    async def resume(self, stream_id: uuid.UUID, checkpoint_blob_id: str) -> None:
        """Restore in-process epoch state from a checkpoint blob."""
        raw  = await self.storage.retrieve_blob(checkpoint_blob_id)
        data = json.loads(raw.decode("utf-8"))
        if data.get("type") not in ("checkpoint", "snapshot"):
            raise ValueError("blob_id does not point to a checkpoint or snapshot")
        self._epochs[stream_id] = data.get("epoch", 0)

    async def restore_snapshot(self, snapshot_blob_id: str, new_agent_id: uuid.UUID) -> uuid.UUID:
        """Restore a full snapshot into a brand-new stream.

        CVE-WOS-004 fix: events from snapshots are re-written without replaying
        their original signatures (which would be stale / invalid in a new stream).
        The restored events carry a 'restored_from_snapshot' marker in their payload.
        Callers that need cryptographic continuity should use the disaster recovery
        engine (which re-fetches and re-verifies events from Walrus + Sui).
        """
        raw  = await self.storage.retrieve_blob(snapshot_blob_id)
        data = json.loads(raw.decode("utf-8"))
        if data.get("type") != "snapshot":
            raise ValueError("blob_id does not point to a snapshot")

        new_stream_id = await self.ledger.create_stream(new_agent_id)
        for ev_data in data.get("events", []):
            # Strip any embedded signature block — it is invalid in a new stream.
            # The restored event is marked as a restored copy, not a signed original.
            payload = ev_data.get("payload", {})
            payload.pop("_signature", None)  # remove stale signature
            payload["_restored_from_snapshot"] = snapshot_blob_id
            await self.append(new_stream_id, ev_data["class_type"], payload)
        return new_stream_id

    # ── Summarize ─────────────────────────────────────────────────────────────

    async def summarize(self, stream_id: uuid.UUID, max_events: int = 20) -> str:
        """Generate a deterministic human-readable digest of recent stream events."""
        tl = await self.timeline(stream_id)
        recent = tl[-max_events:] if len(tl) > max_events else tl
        if not recent:
            return "(empty stream)"

        lines: List[str] = [f"Stream summary ({len(recent)} of {len(tl)} events):"]
        for i, (ev, payload) in enumerate(recent, start=1):
            author     = payload.get("author", "system")
            class_type = getattr(ev, "class_type", "episodic")
            action     = payload.get("action", payload.get("system", class_type))
            detail     = payload.get("title", payload.get("message", payload.get("commit", "")))
            epoch      = getattr(ev, "epoch", i)
            lines.append(
                f"  [{epoch}] {author} — {action}"
                + (f": {detail}" if detail else "")
            )
        return "\n".join(lines)

    # ── Semantic Search ───────────────────────────────────────────────────────

    async def semantic_search(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search across all indexed events using TF-IDF cosine similarity."""
        return await self.vector.search(query, limit=limit)
