import asyncio
import uuid
from walrusos.engine.memory import MemoryEngine
from walrusos.adapters.in_memory import InMemoryStorage, InMemoryLedger, InMemoryVector

async def main():
    print("--- WalrusOS Shared Memory Example ---")
    engine = MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())
    
    # 1. Agent Alpha creates the Stream
    alpha_id = uuid.uuid4()
    shared_stream = await engine.create_stream(alpha_id)
    
    print(f"Created Shared Stream ID: {shared_stream}")
    
    # 2. Agent Alpha appends a memory
    ev1 = await engine.append(shared_stream, "episodic", {"author": "Alpha", "msg": "I am exploring the map."})
    print(f"Alpha appended event: {ev1.id}")
    
    # 3. Agent Beta accesses the same stream and appends
    ev2 = await engine.append(shared_stream, "working", {"author": "Beta", "msg": "I see you, Alpha. Following."})
    print(f"Beta appended event: {ev2.id}")
    
    # 4. Agent Alpha reads the timeline
    print("\n--- DAG Timeline ---")
    timeline = await engine.timeline(shared_stream)
    for ev, payload in timeline:
        print(f"[{ev.epoch}] {payload['author']}: {payload['msg']}")

if __name__ == "__main__":
    asyncio.run(main())
