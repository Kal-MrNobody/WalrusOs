import asyncio
import time
import json
from walrusos.engine.recovery import DisasterRecoveryEngine
from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter, VectorAdapter
from walrusos.core.models.events import ProtocolEvent, EventType

class DummyNetworkLedger(LedgerAdapter):
    def __init__(self, num_events: int):
        self.num_events = num_events
        self.appended = 0
        
    async def sync_events_from_network(self):
        # Generate raw headers to simulate Sui RPC response
        headers = []
        for i in range(self.num_events):
            headers.append({
                "event_id": f"hash_{i}",
                "event_type": EventType.MemoryAppended.value,
                "workspace_id": "ws_bench",
                "agent_id": "ag_bench",
                "blob_id": f"blob_{i}",
                "signature": "v0_migration"
            })
        return headers
        
    async def append_protocol_event(self, event: ProtocolEvent) -> None:
        self.appended += 1
        
    # Dummy legacy methods
    async def append_event(self, *args, **kwargs): pass
    async def create_stream(self, *args, **kwargs): pass
    async def delete_stream(self, *args, **kwargs): pass
    async def get_event(self, *args, **kwargs): pass
    async def get_head(self, *args, **kwargs): pass
    async def list_events(self, *args, **kwargs): pass

class DummyStorage(StorageAdapter):
    async def retrieve_blob(self, blob_id: str) -> bytes:
        # Simulate downloading a JSON payload
        payload = {"message": f"Recovered text for {blob_id}", "timestamp": "2026-06-17T00:00:00Z"}
        return json.dumps(payload).encode("utf-8")
        
    async def store_blob(self, payload: bytes, content_type: str) -> str: return "blob"
    async def delete_blob(self, blob_id: str) -> None: pass
    async def blob_metadata(self, blob_id: str) -> dict: return {}

class DummyVectorDB(VectorAdapter):
    def __init__(self):
        self.indexed = 0
    async def upsert(self, doc_id: str, text: str, metadata: dict) -> None:
        self.indexed += 1
    async def search(self, query: str, limit: int = 10, filters: dict = None): return []
    async def delete(self, doc_id: str) -> None: pass

async def benchmark_recovery(num_events: int = 1000):
    print(f"Benchmarking Disaster Recovery Engine for {num_events} events...")
    
    ledger = DummyNetworkLedger(num_events)
    storage = DummyStorage()
    vector = DummyVectorDB()
    
    engine = DisasterRecoveryEngine(ledger, storage, vector)
    
    t0 = time.time()
    recovered_count = await engine.recover()
    t1 = time.time()
    
    print(f"\n--- Benchmark Results ---")
    print(f"Total Time: {t1-t0:.4f} seconds")
    print(f"Events Recovered: {recovered_count}")
    print(f"SQLite Inserts Simulated: {ledger.appended}")
    print(f"Vector Upserts Simulated: {vector.indexed}")
    print(f"Throughput: {recovered_count / (t1-t0):.2f} events/sec")
    print(f"Latency per event: {((t1-t0)/recovered_count)*1000:.2f} ms")

if __name__ == "__main__":
    asyncio.run(benchmark_recovery())
