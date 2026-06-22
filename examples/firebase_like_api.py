import asyncio
from typing import Dict, Any
from walrusos import WalrusOS

async def main():
    print("--- WalrusOS: Firebase-like DX Example ---")
    
    # 1. Initialize Runtime (using local SQLite / InMemory mocks)
    runtime = WalrusOS()  # Production: reads ~/.walrusos/config.json
# Dev/offline: WALRUSOS_USE_MOCKS=1 python firebase_like_api.py
    
    # 2. Fluid Method Chaining
    workspace = runtime.workspace("research_lab")
    researcher = workspace.agent("Researcher")
    writer = workspace.agent("Writer")
    stream = workspace.stream("papers")
    
    # 3. Define Async Callback
    async def writer_callback(payload: Dict[str, Any]) -> None:
        print(f"\n[Writer] Received notification from {payload.get('author')}:")
        print(f"[Writer] Content: {payload.get('thought')}")
        
    # 4. Subscribe Writer to the Stream
    print("Writer is subscribing to the 'papers' stream...")
    task = await writer.subscribe(stream, writer_callback)
    
    # 5. Researcher publishes to the Stream
    print("Researcher is publishing a new thought...")
    await researcher.publish(stream, {"thought": "I found a new paper on Swarm Intelligence."})
    
    # Let the polling callback fire
    await asyncio.sleep(2.0)
    task.cancel()
    print("Example complete.")

if __name__ == "__main__":
    asyncio.run(main())
