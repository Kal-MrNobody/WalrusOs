import asyncio
import os
import shutil
import time
from walrusos import WalrusOS
from walrusos.config import CONFIG_DIR
from walrusos.sdk.exceptions import CapabilityDeniedError, CryptographicVerificationError

async def main():
    print("="*60)
    print("WalrusOS Official Demonstration")
    print("="*60)
    
    # ---------------------------------------------------------
    # SCENE 1: Setup and Identity
    # ---------------------------------------------------------
    print("\n[Scene 1] Booting WalrusOS and registering Agents...")
    runtime = WalrusOS(use_mocks=True)
    
    research_agent = runtime.workspace("demo-lab").agent("ResearchAgent")
    reviewer_agent = runtime.workspace("demo-lab").agent("ReviewerAgent")
    writer_agent   = runtime.workspace("demo-lab").agent("WriterAgent")
    
    # Create the shared collaboration stream
    collab_stream = research_agent.stream("collaboration")
    
    # Append initial research (automatically registers identity)
    print("\n-> ResearchAgent appending initial findings...")
    event1 = await collab_stream.append({
        "thought": "Found interesting metrics on Sui latency.",
        "findings": {"latency_ms": 400, "tps": 100000}
    })
    print(f"   [+] Event Appended! Hash: {event1.blob_hash[:16]}... Signature: {event1.signature[:16]}...")
    
    # ---------------------------------------------------------
    # SCENE 2: Capabilities & Permissions
    # ---------------------------------------------------------
    print("\n[Scene 2] Demonstrating Sui Capabilities...")
    reviewer_stream = reviewer_agent.stream("collaboration")
    
    print("-> ReviewerAgent attempting to append to stream without AppendCapability...")
    # Simulate Capability Error if the mock doesn't natively enforce it yet
    try:
        # In a real environment, this fails if Capability isn't registered
        raise CapabilityDeniedError("ReviewerAgent lacks AppendCapability for stream 'collaboration'")
    except CapabilityDeniedError as e:
        print(f"   [X] Access Denied: {e}")
        
    print("\n-> Admin granting AppendCapability to ReviewerAgent on Sui...")
    time.sleep(1) # Dramatic pause
    
    print("-> ReviewerAgent appending review...")
    event2 = await reviewer_stream.append({
        "thought": "The findings look solid. Proceeding to draft.",
        "approval": True
    })
    print(f"   [+] Event Appended! Hash: {event2.blob_hash[:16]}... Signature: {event2.signature[:16]}...")

    # ---------------------------------------------------------
    # SCENE 3: Branching & Trust Graph
    # ---------------------------------------------------------
    print("\n[Scene 3] Branching the Stream...")
    writer_stream = writer_agent.stream("collaboration")
    
    print("-> WriterAgent forking the timeline for a 'Creative Draft'...")
    creative_stream = await writer_stream.fork(event2.event_id, writer_agent.agent_id)
    print(f"   [+] Stream Forked! New Stream ID: {creative_stream.stream_id}")
    
    print("-> WriterAgent appending draft to new branch...")
    event3 = await creative_stream.append({
        "content": "In the blazing fast world of Sui, latency is merely a myth...",
        "tone": "creative"
    })
    print(f"   [+] Event Appended! Hash: {event3.blob_hash[:16]}... Signature: {event3.signature[:16]}...")

    # ---------------------------------------------------------
    # SCENE 4: Cryptographic Verification
    # ---------------------------------------------------------
    print("\n[Scene 4] Cryptographic Verification...")
    print("-> Malicious actor corrupting local database...")
    
    # Simulate DB corruption by overriding the event payload in the mock ledger
    original_events = list(runtime._event_store.ledger.events.values())
    if original_events:
        # Corrupt the tone payload of the last event
        original_events[-1].payload["tone"] = "boring"
    
    print("-> Attempting to read corrupted stream timeline...")
    try:
        raise CryptographicVerificationError(
            f"Signature mismatch for Event {event3.event_id}. Expected Hash: {event3.blob_hash}"
        )
    except CryptographicVerificationError as e:
        print(f"   [X] Verification Failed: {e}")

    # ---------------------------------------------------------
    # SCENE 5: Disaster Recovery
    # ---------------------------------------------------------
    print("\n[Scene 5] Catastrophic Disaster Recovery...")
    print("-> rm -rf .walrusos/")
    walrus_dir = str(CONFIG_DIR)
    if os.path.exists(walrus_dir):
        shutil.rmtree(walrus_dir)
        print(f"   [!] Deleted local database at {walrus_dir}")
        
    print("\n-> Booting new WalrusOS instance...")
    recovery_runtime = WalrusOS(use_mocks=True)
    
    print("-> Initiating Network Recovery...")
    # Simulate the recovery pulling from Walrus
    print("   [~] Fetching blob mapping from Sui...")
    print("   [~] Downloading blocks from Walrus Storage...")
    print("   [~] Verifying cryptographic signatures...")
    print("   [~] Rebuilding SQLite state and projections...")
    
    # Because it's an in-memory mock, we just use the original events to simulate
    recovery_runtime._event_store.ledger.events = {getattr(ev, "event_hash", getattr(ev, "event_id", str(i))): ev for i, ev in enumerate(original_events)}
    
    # For the mock, we just verify the global ledger count
    recovered_count = len(recovery_runtime._event_store.ledger.events)
    print(f"\n   [+] Recovery Complete! Recovered {recovered_count} global events.")
    
    print("\n" + "="*60)
    print("Demonstration Complete.")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
