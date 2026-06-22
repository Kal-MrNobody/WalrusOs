from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter, VectorAdapter
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.core.projections.engine import ProjectionEngine
from walrusos.core.models.agent_identity import AgentIdentity

logger = logging.getLogger(__name__)

class EventStoreEngine:
    """
    Core Event Sourcing Engine.
    
    Appends immutable ProtocolEvents and reconstructs state (Projections)
    by replaying events.
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

    @staticmethod
    def _compute_event_hash(payload_bytes: bytes, previous_hash: Optional[str]) -> str:
        """Compute the canonical hash for an event."""
        material = payload_bytes
        if previous_hash:
            material = previous_hash.encode("utf-8") + b":" + material
        return hashlib.sha256(material).hexdigest()

    async def append(
        self,
        event_type: EventType,
        workspace_id: str,
        wallet: str,
        payload_dict: Dict[str, Any],
        agent_id: Optional[str] = None,
        signature: str = "",
    ) -> ProtocolEvent:
        """
        Append a new ProtocolEvent to the global event log.
        """
        # Store large payloads on Walrus
        payload_bytes = json.dumps(payload_dict, default=str).encode("utf-8")
        blob_id = await self.storage.store_blob(payload_bytes, "application/json")
        blob_hash = hashlib.sha256(payload_bytes).hexdigest()
        
        # Get head event to form DAG/hash chain
        # Note: We rely on the ledger adapter to give us the latest event_hash globally or per workspace
        parent_id = None
        previous_hash = None
        if hasattr(self.ledger, "get_latest_event_hash"):
            previous_hash = await self.ledger.get_latest_event_hash(workspace_id)
            
        event_id = self._compute_event_hash(payload_bytes, previous_hash)

        event = ProtocolEvent(
            event_id=event_id,
            event_type=event_type,
            workspace_id=workspace_id,
            agent_id=agent_id,
            wallet=wallet,
            blob_id=blob_id,
            blob_hash=blob_hash,
            parent_event=parent_id,
            previous_hash=previous_hash,
            signature=signature,
            payload=payload_dict,
        )

        # Anchor on Sui FIRST so the digest is set before persistence.
        # Previously the row was inserted then the digest was set in-memory only,
        # leaving transaction_digest=NULL in SQLite even on successful anchoring.
        if hasattr(self.ledger, "anchor_protocol_event"):
            try:
                tx_digest = await self.ledger.anchor_protocol_event(event)
                if tx_digest:
                    event.transaction_digest = tx_digest
            except Exception as exc:
                logger.warning(
                    "Sui anchor failed for event %s: %s", event.event_id[:16], exc
                )

        # Store in ledger — event now carries its transaction_digest if anchoring succeeded.
        if hasattr(self.ledger, "append_protocol_event"):
            await self.ledger.append_protocol_event(event)

        # Vector Indexing and Memory Intelligence for Memory Appends
        if event_type == EventType.MemoryAppended:
            text_vals = []
            for v in payload_dict.values():
                if isinstance(v, str):
                    text_vals.append(v)
            if text_vals:
                doc_text = " ".join(text_vals)
                await self.vector.upsert(event.event_id, doc_text, {"workspace_id": workspace_id, "agent_id": agent_id})
                
            # Populate MemoryEventRecord for intelligence queries
            if hasattr(self.ledger, "append_event"):
                import uuid
                from walrusos.core.models.memory import MemoryEvent
                stream_id_str = payload_dict.get("stream_id")
                if stream_id_str:
                    try:
                        stream_id = uuid.UUID(stream_id_str)
                        mem_event = MemoryEvent(
                            id=event.event_id,
                            stream_id=stream_id,
                            parent_id=payload_dict.get("parent_id") or "genesis",
                            epoch=payload_dict.get("epoch") or 0,
                            memory_type=payload_dict.get("memory_type", "observation"),
                            tags=payload_dict.get("tags") or [],
                            importance=payload_dict.get("importance", 0.5),
                            summary=payload_dict.get("summary"),
                            project=payload_dict.get("project"),
                            content_blob_id=blob_id,
                            agent_id=agent_id,
                            event_hash=event.previous_hash,
                            signature=signature,
                            public_key=payload_dict.get("public_key")
                        )
                        await self.ledger.append_event(stream_id, mem_event)
                    except ValueError:
                        pass

        return event

    async def replay_agent(self, agent_id: str) -> Optional[AgentIdentity]:
        """
        Reconstruct an AgentIdentity by replaying its events.
        """
        if not hasattr(self.ledger, "get_events_for_agent"):
            return None
            
        events = await self.ledger.get_events_for_agent(agent_id)
        if not events:
            return None
            
        state = None
        for ev in events:
            try:
                state = ProjectionEngine.apply_agent_event(state, ev)
            except ValueError:
                pass # Ignore malformed events during replay
                
        return state

    async def replay_workspace(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """
        Reconstruct a Workspace by replaying its events.
        """
        if not hasattr(self.ledger, "get_events_for_workspace"):
            return None
            
        events = await self.ledger.get_events_for_workspace(workspace_id)
        if not events:
            return None
            
        state = None
        for ev in events:
            try:
                state = ProjectionEngine.apply_workspace_event(state, ev)
            except ValueError:
                pass
        return state

    async def timeline(self, stream_id: uuid.UUID) -> List[Tuple[ProtocolEvent, Dict[str, Any]]]:
        """Return the timeline of events for a specific stream."""
        # For simplicity in Phase 5 migration, we filter by stream_id if possible
        # Or if the ledger supports stream-specific events
        if hasattr(self.ledger, "list_events"):
            events = await self.ledger.list_events(stream_id) # type: ignore
        else:
            return []
            
        result = []
        for event in events:
            # ProtocolEvents have .payload directly inside them, or a blob_id
            if isinstance(event, ProtocolEvent):
                # If it's a MemoryAppended event
                if event.event_type == EventType.MemoryAppended:
                    result.append((event, event.payload))
                elif event.event_type.name == "MemoryAppended":
                    result.append((event, event.payload))
        return result

    async def verify_event(self, event_id: str) -> bool:
        from walrusos.engine.memory import MemoryEngine
        return await MemoryEngine(self.ledger, self.storage, self.vector).verify_event(event_id)

    async def read(self, event_id: str) -> Optional[Dict[str, Any]]:
        from walrusos.engine.memory import MemoryEngine
        return await MemoryEngine(self.ledger, self.storage, self.vector).read(event_id)
