import asyncio
import uuid
import json
from walrusos.engine.memory import MemoryEngine
from walrusos.adapters.walrus import WalrusAdapter
from walrusos.adapters.in_memory import InMemoryLedger, InMemoryVector

TESTNET_PUBLISHER = "https://publisher.walrus-testnet.walrus.space"
TESTNET_AGGREGATOR = "https://aggregator.walrus-testnet.walrus.space"

async def main():
    print("--- WalrusOS: Public Storage Network Example ---")
    
    # 1. Instantiate the Engine, injecting the true Walrus HTTP Adapter
    storage = WalrusAdapter(TESTNET_PUBLISHER, TESTNET_AGGREGATOR)
    ledger = InMemoryLedger() # We still use a mock ledger until Milestone 4 (Sui)
    vector = InMemoryVector()
    
    engine = MemoryEngine(ledger, storage, vector)
    
    # 2. Agent creates a stream
    agent_id = uuid.uuid4()
    stream_id = await engine.create_stream(agent_id)
    print(f"Created Stream ID: {stream_id}")
    
    # 3. Agent appends an event to the public testnet
    print("\nCompressing, Encrypting, and Uploading to Walrus Testnet...")
    payload = {"thought": "I am storing this payload permanently on a decentralized network."}
    
    event = await engine.append(stream_id, "working", payload)
    
    print("\n--- Event Appended Successfully ---")
    print(f"Sui Tx Hash (Mocked): {event.id}")
    print(f"Walrus Blob ID: {event.content_blob_id}")
    
    # 4. Agent reads the timeline (Downloading, Decrypting, Decompressing)
    print("\n--- DAG Timeline ---")
    print("Fetching and decrypting blobs from the network...")
    timeline = await engine.timeline(stream_id)
    for ev, data in timeline:
        print(f"Blob {ev.content_blob_id} -> {json.dumps(data)}")

if __name__ == "__main__":
    asyncio.run(main())
