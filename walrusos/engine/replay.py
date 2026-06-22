import json
import re
from typing import List, Optional, Callable, Dict, Any, Set
from datetime import datetime, timezone
import dateutil.parser

from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.core.projections.engine import ProjectionEngine
from walrusos.core.crypto import canonicalize_payload, hash_payload, verify_signature

# Blob ID allow-list: Walrus blob IDs are base58 alphanumeric strings, max 64 chars.
# Manifest IDs are prefixed with 'manifest:' followed by the same pattern.
_BLOB_ID_RE = re.compile(r'^(?:manifest:)?[A-Za-z0-9_-]{1,64}$')


def _validate_blob_id(blob_id: Optional[str]) -> None:
    """Reject blob_ids that could be used for path traversal or injection."""
    if blob_id is None:
        return
    if not _BLOB_ID_RE.match(blob_id):
        raise CryptographicVerificationError(
            f"Invalid blob_id format: {blob_id!r}. "
            "Blob IDs must be alphanumeric base58 strings."
        )


class CryptographicVerificationError(Exception):
    pass

class ReplayEngine:
    """
    Reconstructs protocol state from a raw ProtocolEvent stream while mathematically
    verifying cryptographic integrity and access control.
    """

    def __init__(self, ledger: LedgerAdapter, storage: StorageAdapter):
        self.ledger = ledger
        self.storage = storage

    async def fetch_events(
        self,
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        stream_id: Optional[str] = None,
    ) -> List[ProtocolEvent]:
        """Fetch the base stream of events from the ledger."""
        if agent_id and hasattr(self.ledger, "get_events_for_agent"):
            return await self.ledger.get_events_for_agent(agent_id)
        if workspace_id and hasattr(self.ledger, "get_events_for_workspace"):
            events = await self.ledger.get_events_for_workspace(workspace_id)
            if stream_id:
                return [e for e in events if e.payload.get("stream_id") == stream_id]
            return events
        return []

    async def replay(
        self,
        workspace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        stream_id: Optional[str] = None,
        until_timestamp: Optional[str] = None,
        until_event: Optional[str] = None,
        verify_crypto: bool = True,
        verify_capabilities: bool = True,
    ) -> List[ProtocolEvent]:
        """
        Replay an event stream, filtering and verifying along the way.
        
        Returns the verified, filtered chronological event list.
        """
        events = await self.fetch_events(workspace_id, agent_id, stream_id)
        
        valid_events = []
        
        # Capability tracker: AgentID -> List of Capabilities
        # Note: A real capability system tracks the Sui Capability Objects.
        # Here we track logically based on CapabilityGranted/Revoked events in the stream.
        # In a real Sui system, we might query the RPC for active capabilities at a given epoch.
        active_capabilities = {}
        
        # Agent keys tracker: AgentID -> public_key
        agent_keys = {}

        for event in events:
            # 1. Stop conditions
            if until_event and event.event_id == until_event:
                valid_events.append(event)
                break
                
            if until_timestamp:
                try:
                    ev_time = dateutil.parser.isoparse(event.timestamp)
                    until_time = dateutil.parser.isoparse(until_timestamp)
                    if ev_time > until_time:
                        break
                except Exception:
                    pass

            # 2. Track Keys and Capabilities for verification
            if event.event_type == EventType.AgentRegistered:
                agent_keys[event.agent_id] = event.payload.get("public_key")
            
            if event.event_type == EventType.CapabilityGranted:
                cap = event.payload.get("capability")
                tgt = event.payload.get("target_agent_id")
                if tgt and cap:
                    if tgt not in active_capabilities:
                        active_capabilities[tgt] = []
                    active_capabilities[tgt].append(cap)
            
            if event.event_type == EventType.CapabilityRevoked:
                cap = event.payload.get("capability")
                tgt = event.payload.get("target_agent_id")
                if tgt and cap and tgt in active_capabilities:
                    if cap in active_capabilities[tgt]:
                        active_capabilities[tgt].remove(cap)

            # 3. Blob ID validation (CVE-WOS-008)
            try:
                _validate_blob_id(event.blob_id)
            except CryptographicVerificationError as e:
                # Malformed blob ID — drop event, log, continue
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Event %s dropped: invalid blob_id (%s)", event.event_id, e
                )
                continue

            # 4. Cryptographic Verification (CVE-WOS-001 fix: correct arg order)
            try:
                if verify_crypto and event.signature and event.signature != "v0_migration":
                    # Verify hash — canonical payload must match blob_hash
                    canonical_bytes = canonicalize_payload(event.payload)
                    expected_hash = hash_payload(canonical_bytes)
                    if event.event_type == EventType.MemoryAppended:
                        if event.blob_hash and event.blob_hash != expected_hash:
                            raise CryptographicVerificationError(
                                f"Hash mismatch for event {event.event_id}. Payload tampered."
                            )

                    # Verify signature — FIXED: pass hex strings, not raw bytes
                    # CVE-WOS-001: previous code passed bytes.fromhex(pub_key_hex) to a
                    # function expecting a hex string, causing silent verification bypass.
                    pub_key_hex = event.payload.get("public_key") or agent_keys.get(event.agent_id)
                    if pub_key_hex:
                        if not verify_signature(
                            public_key_hex=pub_key_hex,
                            event_hash_hex=expected_hash,
                            signature_b64=event.signature,
                        ):
                            raise CryptographicVerificationError(
                                f"Signature verification failed for event {event.event_id}."
                            )

            except (CryptographicVerificationError, ValueError, TypeError) as e:
                # CVE-WOS-002 fix: do NOT re-queue the tampered event as ValidationFailed.
                # The original design appended a ValidationFailed event which still advanced
                # agent state (memory_counter, execution_counter). Instead we:
                #   1. Log the failure.
                #   2. Drop the event entirely — it is never added to valid_events.
                #   3. The caller is responsible for external reputation penalisation.
                import logging as _logging
                _logging.getLogger(__name__).error(
                    "Event %s DROPPED — cryptographic verification failed: %s",
                    event.event_id, e,
                )
                continue  # Drop tampered event; do NOT append to valid_events

            # 5. Capability Verification (CVE-WOS-010 partial fix)
            if verify_capabilities and event.event_type == EventType.MemoryAppended:
                # Check agent has WRITE capability
                agent_caps = active_capabilities.get(event.agent_id, [])
                # If agent was registered and has an explicit (non-empty) cap list,
                # require 'write'. If never registered (v0 migration), allow through.
                if agent_caps is not None and len(agent_caps) > 0:
                    if "write" not in agent_caps:
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            "Event %s DROPPED — agent %s lacks 'write' capability.",
                            event.event_id, event.agent_id,
                        )
                        continue

            if verify_capabilities and event.event_type == EventType.MemoryForked:
                agent_caps = active_capabilities.get(event.agent_id, [])
                if agent_caps and "fork" not in agent_caps:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "Event %s DROPPED — agent %s lacks 'fork' capability.",
                        event.event_id, event.agent_id,
                    )
                    continue

            valid_events.append(event)

        return valid_events
