"""
WalrusOS v0.1 — 10 Minute Hello World
This script demonstrates the simplified, developer-optimized API of WalrusOS.

To run this, make sure WALRUSOS_KEY_PASSWORD and WALRUSOS_PACKAGE_ID are set,
or use_mocks=True to test it instantly without networking.
"""
import asyncio
from walrusos.client import WalrusOS

async def main():
    # 1. Initialize the Runtime (use_mocks=True for local testing)
    print("Starting WalrusOS...")
    runtime = WalrusOS(use_mocks=True)

    # 2. Get a Workspace & Agent (Lazy Initialization handles the rest)
    # The agent and workspace will automatically be anchored to the ledger when first used!
    agent = runtime.workspace("tutorial").agent("Alice")

    # 3. Create a Stream & Append Memory
    print(f"Appending memory as Agent {agent.agent_name}...")
    stream = agent.stream("scratchpad")
    
    event = await stream.append({
        "thought": "Hello WalrusOS! The new API is much cleaner.",
        "confidence": 0.99
    })

    print(f"\nSuccessfully Appended Event:")
    print(f"- Event ID:   {event.event_id}")
    print(f"- Timestamp:  {event.timestamp}")
    print(f"- Trust Root: {event.payload.get('trust_root', 'N/A')}")
    print(f"- Hash:       {event.blob_hash}")
    print(f"- Signature:  {event.signature[:16]}...")

    # 4. Read the timeline back
    print("\nReading Stream Timeline:")
    timeline = await stream.timeline()
    for ev, payload in timeline:
        print(f"[{ev.timestamp}] {payload['author']}: {payload['thought']}")

if __name__ == "__main__":
    asyncio.run(main())
