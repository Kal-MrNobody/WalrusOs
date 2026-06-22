import uuid
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone

from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.engine.replay import ReplayEngine
from walrusos.core.projections.engine import ProjectionEngine
from walrusos.core.crypto import sign_payload, hash_payload, canonicalize_payload

class TimeTravelEngine:
    """
    Engine responsible for Git-like operations over event-sourced streams:
    Forking, Branching, Merging, and Comparing histories.
    """
    def __init__(self, ledger: LedgerAdapter, storage: StorageAdapter):
        self.ledger = ledger
        self.storage = storage
        self.replay_engine = ReplayEngine(ledger, storage)

    async def get_stream_lineage(self, stream_id: str) -> List[ProtocolEvent]:
        """Fetch all events forming the history of a stream."""
        events = await self.ledger.list_events(uuid.UUID(stream_id))
        # Assuming fetch_events returns chronological array
        # In a real environment, we'd follow the previous_hash / parent_event pointers 
        # from head to genesis and reverse it.
        return sorted(events, key=lambda e: e.timestamp)

    async def find_lca(self, stream_a: str, stream_b: str) -> Tuple[Optional[ProtocolEvent], List[ProtocolEvent], List[ProtocolEvent]]:
        """
        Find the Lowest Common Ancestor (LCA) between two streams and return the divergent paths.
        Returns: (LCA Event, branch_a_events, branch_b_events)
        """
        lineage_a = await self.get_stream_lineage(stream_a)
        lineage_b = await self.get_stream_lineage(stream_b)

        lca = None
        diverge_index_a = 0
        diverge_index_b = 0

        # Walk forward as long as events are identical
        for a, b in zip(lineage_a, lineage_b):
            if a.event_id == b.event_id:
                lca = a
                diverge_index_a += 1
                diverge_index_b += 1
            else:
                break

        # A stream might have branched from a specific event ID.
        # If they don't share the same root in lineage (e.g. branch is a new stream_id),
        # we check if branch B's first event (MemoryForked) points to an event in A.
        if lca is None and lineage_b and lineage_b[0].event_type == EventType.MemoryForked:
            fork_parent = lineage_b[0].parent_event
            for idx, a in enumerate(lineage_a):
                if a.event_id == fork_parent:
                    lca = a
                    diverge_index_a = idx + 1
                    diverge_index_b = 0
                    break

        return lca, lineage_a[diverge_index_a:], lineage_b[diverge_index_b:]

    async def fork_stream(self, agent_id: str, wallet: str, original_stream: str, fork_event_id: str, private_key_hex: str) -> str:
        """
        Fork a stream at a specific event, creating a new branch.
        """
        lineage = await self.get_stream_lineage(original_stream)
        
        # Verify fork_event_id exists in the stream
        if not any(e.event_id == fork_event_id for e in lineage):
            raise ValueError(f"Event {fork_event_id} not found in stream {original_stream}")

        new_stream_id = str(uuid.uuid4())
        
        # The fork event itself is the genesis of the new stream branch
        payload = {
            "stream_id": new_stream_id,
            "original_stream_id": original_stream,
            "forked_at": fork_event_id
        }
        
        canonical_bytes = canonicalize_payload(payload)
        event_hash = hash_payload(canonical_bytes)
        priv_bytes = bytes.fromhex(private_key_hex) if private_key_hex else b""
        signature = sign_payload(priv_bytes, event_hash).hex() if priv_bytes else "v0_migration"

        fork_event = ProtocolEvent(
            event_id=event_hash,
            event_type=EventType.MemoryForked,
            workspace_id=lineage[0].workspace_id if lineage else "unknown",
            agent_id=agent_id,
            wallet=wallet,
            parent_event=fork_event_id,
            previous_hash=fork_event_id,
            payload=payload,
            signature=signature,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        await self.ledger.append_event(uuid.UUID(new_stream_id), fork_event) # type: ignore
        return new_stream_id

    async def merge_streams(self, agent_id: str, wallet: str, source_stream: str, target_stream: str, private_key_hex: str) -> str:
        """
        Merge source_stream into target_stream.
        Appends all divergent events from source to target, capped by a MemoryMerged event.
        """
        lca, divergent_target, divergent_source = await self.find_lca(target_stream, source_stream)
        
        # In a real merge, we'd interleave or fast-forward.
        # For simplicity, we just copy divergent source events onto the target stream.
        target_head = divergent_target[-1].event_id if divergent_target else (lca.event_id if lca else "genesis")
        
        # We append a MemoryMerged event
        payload = {
            "stream_id": target_stream,
            "merged_from_stream": source_stream,
            "divergent_events_merged": len(divergent_source)
        }
        
        canonical_bytes = canonicalize_payload(payload)
        event_hash = hash_payload(canonical_bytes)
        priv_bytes = bytes.fromhex(private_key_hex) if private_key_hex else b""
        signature = sign_payload(priv_bytes, event_hash).hex() if priv_bytes else "v0_migration"

        merge_event = ProtocolEvent(
            event_id=event_hash,
            event_type=EventType.MemoryMerged,
            workspace_id="unknown", # We would look this up normally
            agent_id=agent_id,
            wallet=wallet,
            parent_event=target_head,
            previous_hash=target_head,
            payload=payload,
            signature=signature,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        await self.ledger.append_event(uuid.UUID(target_stream), merge_event) # type: ignore
        return merge_event.event_id

    async def project_to_time(self, workspace_id: str, timestamp: str) -> Dict[str, Any]:
        """
        Reconstruct the workspace to exactly how it looked at a specific time.
        Returns the raw Projection mapping for the Workspace context.
        """
        # 1. Fetch all events for workspace
        events = await self.replay_engine.replay(workspace_id=workspace_id, until_timestamp=timestamp)
        
        # 2. Project
        workspace_state = None
        for ev in events:
            workspace_state = ProjectionEngine.apply_workspace_event(workspace_state, ev)
            
        return workspace_state or {}
