import asyncio
import json
import tempfile
import uuid

import pytest

from walrusos import WalrusOS
from walrusos.adapters.in_memory import InMemoryStorage, InMemoryVector
from walrusos.adapters.sqlite_ledger import SQLiteLedger


@pytest.fixture
async def runtime():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        rt = WalrusOS(db_path=f"{td}/test.db")
        rt._engine.storage = InMemoryStorage()
        rt._engine.vector = InMemoryVector()
        rt._engine.ledger._sqlite = SQLiteLedger(f"{td}/test.db")
        
        yield rt
        
        # Await any pending background tasks to avoid database lock race
        try:
            loop = asyncio.get_running_loop()
            pending = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
            if pending:
                await asyncio.wait(pending, timeout=1.0)
        except RuntimeError:
            pass

        if hasattr(rt._engine.ledger._sqlite, "_engine"):
            rt._engine.ledger._sqlite._engine.dispose()

@pytest.mark.asyncio
async def test_event_signing_and_verification(runtime: WalrusOS):
    ws = runtime.workspace("test_crypto")
    agent = ws.agent("Alice")

    # Publish an event
    event = await agent.publish(ws.stream("test_stream"), {"action": "hello", "data": "world"})
    
    # 1. Verify it passes natively
    is_valid = await runtime._engine.verify_event(event.id)
    assert is_valid is True, "Event should be valid right after publishing"

    # 2. Check the signature fields
    ev_record = await runtime._engine.ledger.get_event(event.id)
    assert getattr(ev_record, "signature", None) is not None
    assert getattr(ev_record, "event_hash", None) is not None
    assert getattr(ev_record, "public_key", None) == agent.identity.public_key

@pytest.mark.asyncio
async def test_attack_corrupted_payload(runtime: WalrusOS):
    ws = runtime.workspace("test_crypto_attack")
    agent = ws.agent("Eve")

    event = await agent.publish(ws.stream("test_stream"), {"secret": "data"})
    is_valid = await runtime._engine.verify_event(event.id)
    assert is_valid is True

    # Attack: Mutate the stored Walrus blob
    storage = runtime._engine.storage
    raw = await storage.retrieve_blob(event.content_blob_id)
    payload = json.loads(raw.decode("utf-8"))
    
    # Change data
    payload["secret"] = "hacked"
    new_raw = json.dumps(payload).encode("utf-8")
    
    # Directly overwrite the blob in the mock storage
    if isinstance(storage, InMemoryStorage):
        storage._blobs[event.content_blob_id] = new_raw

    # Verify must now fail
    is_valid_after_attack = await runtime._engine.verify_event(event.id)
    assert is_valid_after_attack is False, "Verification must fail after payload corruption"
