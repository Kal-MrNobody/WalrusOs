import pytest
import asyncio
from typing import List, Dict

from walrusos.engine.recovery import DisasterRecoveryEngine
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter, VectorAdapter

class MockSuiNetworkLedger(LedgerAdapter):
    """Mocks Sui RPC by returning a pre-defined set of headers"""
    def __init__(self, headers):
        self.headers = headers
        self.appended = []
        
    async def sync_events_from_network(self) -> List[Dict]:
        return self.headers
        
    async def append_protocol_event(self, event: ProtocolEvent) -> None:
        self.appended.append(event)
        
    async def get_events_for_agent(self, agent_id: str):
        return [e for e in self.appended if e.agent_id == agent_id]
        
    async def get_events_for_workspace(self, workspace_id: str):
        return [e for e in self.appended if e.workspace_id == workspace_id]
        
    # Dummy implementations for legacy LedgerAdapter interfaces
    async def append_event(self, *args, **kwargs): pass
    async def create_stream(self, *args, **kwargs): pass
    async def delete_stream(self, *args, **kwargs): pass
    async def get_event(self, *args, **kwargs): pass
    async def get_head(self, *args, **kwargs): pass
    async def list_events(self, *args, **kwargs): pass

class MockWalrusStorage(StorageAdapter):
    """Mocks Walrus by returning payloads for known blob_ids"""
    def __init__(self, blobs):
        self.blobs = blobs
        
    async def retrieve_blob(self, blob_id: str) -> bytes:
        if blob_id in self.blobs:
            import json
            return json.dumps(self.blobs[blob_id]).encode("utf-8")
        raise ValueError("Blob not found")
        
    async def store_blob(self, payload: bytes, content_type: str) -> str:
        return "mock_blob"
        
    async def delete_blob(self, blob_id: str) -> None: pass
    async def blob_metadata(self, blob_id: str) -> Dict: return {}

class MockVectorDB(VectorAdapter):
    def __init__(self):
        self.upserted = []
        
    async def upsert(self, doc_id: str, text: str, metadata: dict) -> None:
        self.upserted.append((doc_id, text))
        
    async def search(self, query: str, limit: int = 10, filters: dict = None):
        return []
        
    async def delete(self, doc_id: str) -> None: pass

@pytest.mark.asyncio
async def test_disaster_recovery_engine():
    # 1. Setup Mock Network State
    workspace_id = "ws_123"
    agent_id = "ag_456"
    
    # We will pretend the network has 3 events:
    # WorkspaceCreated, AgentRegistered, MemoryAppended
    
    headers = [
        {
            "event_id": "hash_1",
            "event_type": EventType.WorkspaceCreated.value,
            "workspace_id": workspace_id,
            "blob_id": "blob_1",
            "signature": "v0_migration"
        },
        {
            "event_id": "hash_2",
            "event_type": EventType.AgentRegistered.value,
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "blob_id": "blob_2",
            "signature": "v0_migration"
        },
        {
            "event_id": "hash_3",
            "event_type": EventType.MemoryAppended.value,
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "blob_id": "blob_3",
            "signature": "v0_migration"
        }
    ]
    
    blobs = {
        "blob_1": {"name": "Recovery Workspace"},
        "blob_2": {"agent_name": "Phoenix Agent", "public_key": "aabbcc"},
        "blob_3": {"message": "I survived the crash!", "timestamp": "2026-06-17T00:00:00Z"}
    }
    
    # 2. Blank Slate Environment
    ledger = MockSuiNetworkLedger(headers)
    storage = MockWalrusStorage(blobs)
    vector = MockVectorDB()
    
    engine = DisasterRecoveryEngine(ledger, storage, vector)
    
    # 3. Trigger Recovery
    recovered_count = await engine.recover()
    
    # 4. Assertions
    assert recovered_count == 3
    
    # Assert SQLite Ledger was rebuilt
    assert len(ledger.appended) == 3
    assert ledger.appended[0].event_id == "hash_1"
    assert ledger.appended[2].payload["message"] == "I survived the crash!"
    
    # Assert Vector DB was re-indexed (only MemoryAppended)
    assert len(vector.upserted) == 1
    assert vector.upserted[0][0] == "hash_3"
    assert "I survived the crash!" in vector.upserted[0][1]

@pytest.mark.asyncio
async def test_payload_lost_handling():
    # If Walrus expired a blob, we must still recover the DAG header but mark as PayloadLost
    headers = [{
        "event_id": "hash_lost",
        "event_type": EventType.MemoryAppended.value,
        "blob_id": "expired_blob", # Will throw
        "signature": "v0_migration"
    }]
    
    ledger = MockSuiNetworkLedger(headers)
    storage = MockWalrusStorage({}) # Empty Walrus
    vector = MockVectorDB()
    
    engine = DisasterRecoveryEngine(ledger, storage, vector)
    count = await engine.recover()
    
    assert count == 1
    assert ledger.appended[0].payload["_status"] == "PayloadLost"
    # Should NOT index lost payloads into Vector
    assert len(vector.upserted) == 0
