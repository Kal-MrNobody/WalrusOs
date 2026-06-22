import asyncio
import json
import uuid
import hashlib
from datetime import datetime, timezone
from sqlmodel import Session, select

from walrusos.adapters.sqlite_ledger import (
    SQLiteLedger,
    MemoryEventRecord,
    AgentIdentityRecord,
    WorkspaceRecord,
    ProtocolEventRecord
)
from walrusos.core.models.events import EventType

def _compute_event_hash(payload_bytes: bytes, previous_hash: str = None) -> str:
    material = payload_bytes
    if previous_hash:
        material = previous_hash.encode("utf-8") + b":" + material
    return hashlib.sha256(material).hexdigest()

def migrate_to_events(db_path: str = "~/.walrusos/walrusos.db"):
    """
    Migrates state-based tables to the new immutable event store.
    Generates synthetic events for Workspaces and Agents, then ports MemoryEvents.
    """
    ledger = SQLiteLedger(db_path)
    engine = ledger._engine
    
    with Session(engine) as session:
        # Check if already migrated
        existing = session.exec(select(ProtocolEventRecord).limit(1)).first()
        if existing:
            print("Database already contains ProtocolEvents. Skipping migration.")
            return

        print("Starting Event Sourcing Migration...")
        previous_hash_per_ws = {}

        # 1. Migrate Workspaces
        workspaces = session.exec(select(WorkspaceRecord)).all()
        for ws in workspaces:
            payload = {"name": ws.name}
            payload_bytes = json.dumps(payload, default=str).encode("utf-8")
            event_id = _compute_event_hash(payload_bytes)
            
            record = ProtocolEventRecord(
                event_id=event_id,
                event_type=EventType.WorkspaceCreated.value,
                workspace_id=ws.workspace_id,
                agent_id=None,
                wallet=ws.owner_wallet,
                signature="v0_migration",
                timestamp=ws.created_at,
                payload_json=json.dumps(payload)
            )
            session.add(record)
            previous_hash_per_ws[ws.workspace_id] = event_id
            print(f"Migrated Workspace: {ws.workspace_id}")

        # 2. Migrate Agents
        agents = session.exec(select(AgentIdentityRecord)).all()
        for agent in agents:
            payload = {
                "agent_name": agent.agent_name,
                "public_key": agent.public_key,
                "trust_root": agent.trust_root,
                "metadata": json.loads(agent.metadata_json) if agent.metadata_json else {}
            }
            payload_bytes = json.dumps(payload, default=str).encode("utf-8")
            prev_hash = previous_hash_per_ws.get(agent.workspace_id)
            event_id = _compute_event_hash(payload_bytes, prev_hash)
            
            record = ProtocolEventRecord(
                event_id=event_id,
                event_type=EventType.AgentRegistered.value,
                workspace_id=agent.workspace_id,
                agent_id=agent.agent_id,
                wallet=agent.owner_wallet,
                previous_hash=prev_hash,
                signature="v0_migration",
                timestamp=agent.created_at,
                payload_json=json.dumps(payload)
            )
            session.add(record)
            previous_hash_per_ws[agent.workspace_id] = event_id
            print(f"Migrated Agent: {agent.agent_id}")

        # 3. Migrate MemoryEvents
        memory_events = session.exec(select(MemoryEventRecord).order_by(MemoryEventRecord.epoch.asc())).all() # type: ignore
        for me in memory_events:
            # We don't have workspace_id easily available on MemoryEvent, so we fetch it via agent
            agent = session.get(AgentIdentityRecord, me.agent_id)
            if not agent:
                print(f"Skipping MemoryEvent {me.id} - orphaned agent {me.agent_id}")
                continue
                
            payload = {
                "class_type": me.class_type,
                "epoch": me.epoch,
            }
            payload_bytes = json.dumps(payload, default=str).encode("utf-8")
            prev_hash = previous_hash_per_ws.get(agent.workspace_id)
            event_id = me.id # Use existing ID to preserve DAG
            
            record = ProtocolEventRecord(
                event_id=event_id,
                event_type=EventType.MemoryAppended.value,
                workspace_id=agent.workspace_id,
                agent_id=agent.agent_id,
                wallet=agent.owner_wallet,
                blob_id=me.content_blob_id,
                blob_hash=me.event_hash,
                parent_event=me.parent_id,
                previous_hash=prev_hash,
                signature=me.signature or "v0_migration",
                timestamp=me.created_at,
                payload_json=json.dumps(payload)
            )
            session.add(record)
            previous_hash_per_ws[agent.workspace_id] = event_id

        session.commit()
        print("Migration complete.")

if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "~/.walrusos/walrusos.db"
    migrate_to_events(db)
