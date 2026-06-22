import pytest
import json
import uuid
import datetime
from cryptography.hazmat.primitives.asymmetric import ed25519

from walrusos.engine.replay import ReplayEngine, CryptographicVerificationError
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.core.crypto import canonicalize_payload, hash_payload

class DummyLedger:
    def __init__(self, events):
        self.events = events
    async def get_events_for_agent(self, agent_id):
        return [e for e in self.events if e.agent_id == agent_id]
    async def get_events_for_workspace(self, workspace_id):
        return [e for e in self.events if e.workspace_id == workspace_id]

class DummyStorage:
    pass

@pytest.mark.asyncio
async def test_replay_engine_verification():
    # 1. Setup keys
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw().hex()

    workspace_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    wallet = "0xwallet"

    events = []

    # 2. Agent Registered
    payload = {"agent_name": "test", "public_key": public_key}
    payload_bytes = json.dumps(payload).encode()
    events.append(ProtocolEvent(
        event_id=hash_payload(payload_bytes),
        event_type=EventType.AgentRegistered,
        workspace_id=workspace_id,
        agent_id=agent_id,
        wallet=wallet,
        previous_hash=None,
        payload=payload,
        signature="v0_migration",
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    ))

    # 3. Valid Memory Appended
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    from walrusos.core.crypto import sign_payload
    private_key_bytes = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    payload = {"message": "hello"}
    canonical = canonicalize_payload(payload)
    ev_hash = hash_payload(canonical)
    sig = sign_payload(private_key_bytes, ev_hash)
    
    events.append(ProtocolEvent(
        event_id=ev_hash,
        event_type=EventType.MemoryAppended,
        workspace_id=workspace_id,
        agent_id=agent_id,
        wallet=wallet,
        previous_hash=events[0].event_id,
        payload=payload,
        signature=sig,
        blob_hash=ev_hash,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    ))

    # 4. Tampered Memory Appended (Wrong Hash)
    tampered_payload = {"message": "hacked"}
    events.append(ProtocolEvent(
        event_id=ev_hash, # same id but tampered payload
        event_type=EventType.MemoryAppended,
        workspace_id=workspace_id,
        agent_id=agent_id,
        wallet=wallet,
        previous_hash=events[1].event_id,
        payload=tampered_payload,
        signature=sig, # Reusing signature
        blob_hash=ev_hash,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    ))

    engine = ReplayEngine(DummyLedger(events), DummyStorage())

    # Replay without verification should return all 3
    result = await engine.replay(agent_id=agent_id, verify_crypto=False)
    assert len(result) == 3

    # Replay with verification drops the tampered one, returning only 2 valid events
    valid_events = await engine.replay(agent_id=agent_id, verify_crypto=True)
    
    assert len(valid_events) == 2
    assert valid_events[1].event_id == ev_hash

