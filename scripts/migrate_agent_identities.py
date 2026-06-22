"""
Migration script for Protocol Hardening Phase 2.

Scans the SQLite ledger for all existing agents (identified implicitly by the
'author' string in stream event payloads) and mints a persistent AgentIdentity
record for them so they become first-class citizens.

Usage:
    python scripts/migrate_agent_identities.py --workspace default
"""
import argparse
import asyncio
import os
import sys

# Ensure the walrusos package is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from walrusos import WalrusOS
from walrusos.config import load_config
from walrusos.core.models.agent_identity import AgentIdentity, _compute_trust_root
from walrusos.sdk.agent import _generate_ed25519_keypair, _KEY_PASSWORD


def migrate_workspace(workspace_name: str) -> None:
    print(f"\n[WalrusOS Migration] Upgrading agents in workspace: {workspace_name}")
    cfg = load_config()
    
    # We load production mode but ignore Walrus network failures if we only
    # need the ledger
    runtime = WalrusOS(use_mocks=False)
    ledger  = runtime._engine.ledger
    engine  = runtime._engine
    sqlite  = getattr(ledger, "_sqlite", ledger) if hasattr(ledger, "_sqlite") else ledger
    
    if not hasattr(sqlite, "create_agent_identity"):
        print("ERROR: SQLiteLedger is not upgraded for Phase 2 yet.")
        sys.exit(1)

    owner_wallet = cfg.sui_address or "0x0"
    
    agents_found = set()
    from walrusos.adapters.sqlite_ledger import MemoryStreamRecord, MemoryEventRecord
    from sqlmodel import Session, select
    
    # 1. Discover agents implicitly by scanning the ledger
    try:
        with Session(sqlite._engine) as session:
            streams = session.exec(select(MemoryStreamRecord)).all()
            for s in streams:
                events = session.exec(
                    select(MemoryEventRecord).where(MemoryEventRecord.stream_id == s.stream_id)
                ).all()
                for ev in events:
                    # Parse the payload JSON to find 'author'
                    try:
                        payload = asyncio.run(engine.read(ev.id))
                        author = payload.get("author")
                        if author and author != "system":
                            agents_found.add(author)
                    except Exception:
                        pass
    except Exception as exc:
        print(f"Error scanning ledger: {exc}")
        sys.exit(1)

    if not agents_found:
        print("No implicit agents found. Nothing to migrate.")
        return

    print(f"Discovered {len(agents_found)} agent(s): {', '.join(agents_found)}")

    # 2. Mint persistent identities
    for agent_name in agents_found:
        existing = sqlite.get_agent_identity_by_name(workspace_name, agent_name)
        if existing:
            print(f"  - Agent '{agent_name}' already has an identity (Skipping).")
            continue
            
        print(f"  - Minting identity for '{agent_name}'...")
        priv_bytes, pub_bytes = _generate_ed25519_keypair()
        
        identity = AgentIdentity.create(
            workspace_name=workspace_name,
            agent_name=agent_name,
            owner_wallet=owner_wallet,
            public_key_hex=pub_bytes.hex(),
        )
        
        sqlite.create_agent_identity(identity)
        try:
            sqlite.store_agent_private_key(identity.agent_id, priv_bytes, _KEY_PASSWORD())
        except Exception as e:
            print(f"    Warning: Could not store key for '{agent_name}': {e}")
            
        print(f"    ✓ agent_id:   {identity.agent_id}")
        print(f"    ✓ trust_root: {identity.trust_root}")
        
    print("\nMigration complete. All agents are now first-class protocol objects.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate agents to Phase 2 AgentIdentity")
    parser.add_argument("--workspace", default="default", help="Workspace to migrate")
    args = parser.parse_args()
    migrate_workspace(args.workspace)
