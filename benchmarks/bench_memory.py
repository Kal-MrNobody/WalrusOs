import asyncio
import time
import uuid
from walrusos.engine.memory import MemoryEngine
from walrusos.adapters.in_memory import InMemoryStorage, InMemoryLedger, InMemoryVector

async def bench_appends(iterations: int = 10000):
    engine = MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())
    agent_id = uuid.uuid4()
    stream_id = await engine.create_stream(agent_id)
    
    print(f"Benchmarking {iterations} memory appends...")
    start_time = time.time()
    
    for i in range(iterations):
        await engine.append(stream_id, "working", {"iteration": i, "data": "A" * 1024})
        
    duration = time.time() - start_time
    ops = iterations / duration
    print(f"Completed in {duration:.2f} seconds.")
    print(f"Performance: {ops:.2f} appends/sec")

if __name__ == "__main__":
    asyncio.run(bench_appends())
