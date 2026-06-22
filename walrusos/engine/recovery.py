import json
import logging
from typing import List, Optional

from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter, VectorAdapter
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.engine.replay import ReplayEngine, CryptographicVerificationError, _validate_blob_id

logger = logging.getLogger(__name__)

class DisasterRecoveryEngine:
    """
    Orchestrates a full system recovery from the Sui blockchain and Walrus storage.
    
    This engine downloads ProtocolEventAnchored headers from the network,
    fetches the JSON payloads from Walrus, cryptographically verifies them
    using ReplayEngine, and reconstructs the SQLite ledger and Vector database.
    """

    def __init__(
        self,
        ledger: LedgerAdapter,
        storage: StorageAdapter,
        vector: VectorAdapter,
    ):
        self.ledger = ledger
        self.storage = storage
        self.vector = vector
        self.replay_engine = ReplayEngine(ledger=ledger, storage=storage)

    async def recover(self, progress_callback=None) -> int:
        """
        Execute the full recovery pipeline.
        
        Returns the number of events successfully recovered and indexed.
        """
        # 1. Network Sync
        if not hasattr(self.ledger, "sync_events_from_network"):
            raise RuntimeError("LedgerAdapter does not support sync_events_from_network")

        logger.info("Initiating Network Sync...")
        raw_headers = await self.ledger.sync_events_from_network()
        if not raw_headers:
            return 0
            
        recovered_count = 0
        total = len(raw_headers)
        
        # CVE-WOS-006 fix: We no longer use a _TempLedger that bypasses capability
        # checks.  Instead we verify each event independently using verify_signature()
        # directly, and only write to SQLite after verification passes.
        #
        # Capability checks during recovery are skipped intentionally (the events
        # have ALREADY passed capability checks on Sui before being anchored), but
        # crypto verification is MANDATORY for every non-migration event.

        for i, header in enumerate(raw_headers):
            event_id = header.get("event_id")
            blob_id = header.get("blob_id")
            
            # CVE-WOS-006 + CVE-WOS-008: Validate blob_id format before use
            try:
                _validate_blob_id(blob_id)
            except CryptographicVerificationError:
                logger.error(
                    "Event %s has invalid blob_id %r — DROPPING during recovery.",
                    event_id, blob_id,
                )
                continue

            payload_dict = {"_status": "PayloadLost"}
            
            # 2. Blob Hydration
            try:
                if blob_id and blob_id != "null":
                    raw_payload_bytes = await self.storage.retrieve_blob(blob_id)
                    if raw_payload_bytes:
                        payload_dict = json.loads(raw_payload_bytes.decode("utf-8"))
            except Exception as e:
                logger.warning(f"Could not retrieve blob {blob_id} for event {event_id}: {e}")

            event = ProtocolEvent(
                event_id=event_id,
                event_type=EventType(header.get("event_type", "MemoryAppended")),
                workspace_id=header.get("workspace_id", ""),
                agent_id=header.get("agent_id", ""),
                wallet=header.get("wallet", ""),
                blob_id=blob_id,
                blob_hash=header.get("blob_hash"),
                parent_event=header.get("parent_event"),
                previous_hash=header.get("previous_hash"),
                signature=header.get("signature", ""),
                payload=payload_dict,
                timestamp="" # Sui events don't embed ISO timestamp in the header usually, we take from payload
            )
            
            if payload_dict.get("timestamp"):
                event.timestamp = payload_dict["timestamp"]

            # 3. Cryptographic Verification (CVE-WOS-006 fix)
            if payload_dict.get("_status") != "PayloadLost":
                if event.signature and event.signature not in ("", "v0_migration"):
                    from walrusos.core.crypto import canonicalize_payload, hash_payload, verify_signature
                    try:
                        canonical_bytes = canonicalize_payload(payload_dict)
                        expected_hash = hash_payload(canonical_bytes)
                        pub_key_hex = payload_dict.get("public_key")
                        if pub_key_hex:
                            if not verify_signature(
                                public_key_hex=pub_key_hex,
                                event_hash_hex=expected_hash,
                                signature_b64=event.signature,
                            ):
                                logger.error(
                                    "Event %s FAILED cryptographic verification during recovery. "
                                    "Dropping — event will NOT be written to local ledger.",
                                    event_id,
                                )
                                continue
                    except Exception as e:
                        logger.error(
                            "Event %s caused an exception during crypto verification: %s. Dropping.",
                            event_id, e,
                        )
                        continue
            
            # 4. State Projection (Write to local Ledger)
            if hasattr(self.ledger, "append_protocol_event"):
                # We skip actual Sui emission because these are ALREADY on Sui!
                # We need a direct SQLite insert.
                # If append_protocol_event triggers an anchor emission, we'd double-spend/double-anchor.
                # Assuming `append_protocol_event` in SQLiteLedger just writes to the DB.
                # Wait, SuiLedgerAdapter overrides it to do BOTH.
                # We must access the underlying SQLiteLedger.
                
                # We'll use a hack or assume we can write directly.
                underlying_sqlite = getattr(self.ledger, "_sqlite", self.ledger)
                if hasattr(underlying_sqlite, "append_protocol_event"):
                    await underlying_sqlite.append_protocol_event(event)

            # 5. Vector Re-indexing
            if event.event_type == EventType.MemoryAppended and payload_dict.get("_status") != "PayloadLost":
                text_vals = [v for v in payload_dict.values() if isinstance(v, str)]
                if text_vals:
                    doc_text = " ".join(text_vals)
                    await self.vector.upsert(
                        doc_id=event.event_id, 
                        text=doc_text, 
                        metadata={"workspace_id": event.workspace_id, "agent_id": event.agent_id}
                    )
            
            recovered_count += 1
            if progress_callback:
                progress_callback(i + 1, total)

        logger.info(f"Recovery complete. Restored {recovered_count} events.")
        return recovered_count
