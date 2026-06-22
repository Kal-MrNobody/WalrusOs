"""
WalrusOS End-to-End Demo
========================

This script demonstrates the full WalrusOS developer experience:

  1. Login with Sui wallet
  2. Create workspace on-chain
  3. Register agents with Ed25519 identities on-chain
  4. Create a memory stream
  5. Grant permissions (real Sui capabilities)
  6. Publish content (sign -> compress -> Walrus upload -> Sui anchor)
  7. Read content (Walrus download -> decompress -> verify signature)

Every operation is REAL:
  - Blobs on Walrus testnet
  - Transactions on Sui testnet
  - Ed25519 signatures generated and verified

Run:
    python examples/end_to_end_demo.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from walrusos.sdk.live import WalrusOS


def main():
    print()
    print("=" * 70)
    print("  WalrusOS End-to-End Demo")
    print("  Real Walrus storage + Real Sui transactions")
    print("=" * 70)
    print()

    # Step 1: Login
    print("[Step 1] Logging in...")
    wos = WalrusOS()
    wos.login()
    print()

    # Step 2: Create workspace
    print("[Step 2] Creating workspace...")
    workspace = wos.workspace("my-research-project")
    print()

    # Step 3: Register agents
    print("[Step 3] Registering agents...")
    research = workspace.agent("Research")
    writer = workspace.agent("Writer")
    print()

    # Step 4: Create stream
    print("[Step 4] Creating stream...")
    stream = workspace.stream("papers")
    print()

    # Step 5: Grant permissions
    print("[Step 5] Granting permissions...")
    stream.grant(research, permissions=["read", "append"])
    stream.grant(writer, permissions=["read", "append"])
    print()

    # Step 6: Research publishes
    print("[Step 6] Research agent publishing...")
    result1 = research.publish(
        stream,
        "Transformers use attention mechanisms for memory."
    )
    print()

    # Step 7: Writer reads
    print("[Step 7] Writer reading stream...")
    messages = writer.read(stream)
    print(f"  Read {len(messages)} message(s)")
    for msg in messages:
        print(f"    [{msg.agent_name}] {msg.content}")
        print(f"      Verified: {msg.verified}")
        print(f"      Blob:     {msg.blob_id}")
    print()

    # Step 8: Writer publishes a response
    print("[Step 8] Writer agent publishing...")
    result2 = writer.publish(
        stream,
        "Summary: attention replaces recurrence in sequence models."
    )
    print()

    # Step 9: Verify all messages
    print("[Step 9] Verifying all messages...")
    all_messages = research.read(stream)
    all_verified = all(m.verified for m in all_messages)
    print(f"  Total messages: {len(all_messages)}")
    print(f"  All verified:   {all_verified}")
    for msg in all_messages:
        print(f"    [{msg.agent_name}] {msg.content[:60]}...")
    print()

    # Summary
    print("=" * 70)
    print("  === WalrusOS Demo Complete ===")
    print("=" * 70)
    print(f"  Workspace:     {workspace.workspace_id}")
    print(f"  Agents:        Research ({research.agent_id})")
    print(f"                 Writer   ({writer.agent_id})")
    print(f"  Events stored: {len(all_messages)}")
    print(f"  Walrus blobs:  [{result1.blob_id},")
    print(f"                  {result2.blob_id}]")
    print(f"  Sui anchors:   [{result1.tx_digest},")
    print(f"                  {result2.tx_digest}]")
    print(f"  All signatures verified: {all_verified}")
    print()
    print("  Explorer links:")
    print(f"    Workspace: https://suiexplorer.com/object/{workspace.workspace_id}?network=testnet")
    print(f"    Tx 1:      https://suiexplorer.com/txblock/{result1.tx_digest}?network=testnet")
    print(f"    Tx 2:      https://suiexplorer.com/txblock/{result2.tx_digest}?network=testnet")
    print()
    print("  Walrus links:")
    print(f"    Blob 1:    https://aggregator.walrus-testnet.walrus.space/v1/blobs/{result1.blob_id}")
    print(f"    Blob 2:    https://aggregator.walrus-testnet.walrus.space/v1/blobs/{result2.blob_id}")
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
