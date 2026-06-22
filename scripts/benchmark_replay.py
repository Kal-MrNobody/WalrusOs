import asyncio
import time
import uuid
import uuid as _uuid
from walrusos.engine.event_store import EventStoreEngine
from walrusos.adapters.sqlite_ledger import SQLiteLedger
from walrusos.core.models.events import EventType

# Dummy vector/storage adapters for benchmarking
class DummyStorage:
    async def store_blob(self, payload_bytes: bytes, content_type: str) -> str:
        return f"blob_{uuid.uuid4().hex}"

class DummyVector:
    async def upsert(self, doc_id: str, text: str, metadata: dict) -> None:
        pass

async def benchmark_replay(num_events: int = 10000):
    print(f"Generating {num_events} events...")
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    ledger = SQLiteLedger(db_path)
    engine = EventStoreEngine(ledger, DummyStorage(), DummyVector())

    workspace_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "benchmark_workspace"))
    wallet = "0xwallet"
    agent_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, "benchmark_agent"))

    # Append events directly to ledger to bypass blob storage overhead for fast generation
    from walrusos.core.models.events import ProtocolEvent
    import hashlib
    import json
    
    events = []
    prev_hash = None
    
    # 1. Create Workspace
    payload = {"name": "benchmark_workspace"}
    payload_bytes = json.dumps(payload).encode("utf-8")
    ev_id = engine._compute_event_hash(payload_bytes, prev_hash)
    events.append(ProtocolEvent(
        event_id=ev_id, event_type=EventType.WorkspaceCreated, workspace_id=workspace_id,
        wallet=wallet, previous_hash=prev_hash, payload=payload
    ))
    prev_hash = ev_id
    
    # 2. Register Agent
    payload = {"agent_name": "benchmark_agent"}
    payload_bytes = json.dumps(payload).encode("utf-8")
    ev_id = engine._compute_event_hash(payload_bytes, prev_hash)
    events.append(ProtocolEvent(
        event_id=ev_id, event_type=EventType.AgentRegistered, workspace_id=workspace_id,
        agent_id=agent_id, wallet=wallet, previous_hash=prev_hash, payload=payload
    ))
    prev_hash = ev_id

    # 3. Memory Appends
    for i in range(num_events - 2):
        payload = {"message": f"Hello {i}"}
        payload_bytes = json.dumps(payload).encode("utf-8")
        ev_id = engine._compute_event_hash(payload_bytes, prev_hash)
        events.append(ProtocolEvent(
            event_id=ev_id, event_type=EventType.MemoryAppended, workspace_id=workspace_id,
            agent_id=agent_id, wallet=wallet, previous_hash=prev_hash, payload=payload
        ))
        prev_hash = ev_id

    # Insert bulk
    from sqlmodel import Session
    from walrusos.adapters.sqlite_ledger import ProtocolEventRecord
    with Session(ledger._engine) as session:
        for ev in events:
            session.add(ProtocolEventRecord(
                event_id=ev.event_id,
                event_type=ev.event_type.value,
                workspace_id=ev.workspace_id,
                agent_id=ev.agent_id,
                wallet=ev.wallet,
                previous_hash=ev.previous_hash,
                signature="",
                timestamp=ev.timestamp,
                payload_json=json.dumps(ev.payload)
            ))
        session.commit()

    from walrusos.engine.replay import ReplayEngine
    replay_engine = ReplayEngine(ledger, DummyStorage())
    
    print(f"Replaying {num_events} events for Agent Projection (Verification ENABLED)...")
    t0 = time.time()
    valid_events = await replay_engine.replay(agent_id=agent_id, verify_crypto=True)
    t1 = time.time()
    
    print(f"Replay completed in {t1-t0:.4f} seconds.")
    print(f"Valid Events Reconstructed: {len(valid_events)}")
    print(f"Latency per event: {((t1-t0)/num_events)*1000:.4f} ms")

if __name__ == "__main__":
    asyncio.run(benchmark_replay())
