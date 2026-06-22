import asyncio
import time
import uuid

import pytest
from walrusos import WalrusOS
from walrusos.adapters.in_memory import InMemoryStorage, InMemoryVector
from walrusos.adapters.sqlite_ledger import SQLiteLedger
from walrusos.core.models.agent_identity import AgentStatus

@pytest.fixture
def runtime(tmp_path):
    """Setup a WalrusOS runtime using InMemory storage and SQLite ledger."""
    db_path = str(tmp_path / "test.db")
    rt = WalrusOS(db_path=db_path)
    rt._engine.storage = InMemoryStorage()
    rt._engine.vector = InMemoryVector()
    # Inject SQLite ledger directly
    rt._engine.ledger = SQLiteLedger(db_path=db_path)
    return rt


@pytest.mark.asyncio
async def test_capability_enforcement_expired(runtime):
    ws = runtime.workspace("test_sec")
    agent = ws.agent("Alice")
    stream = ws.stream("stream1")
    
    # 1. Setup mock SUI Objects in SQLite to enable enforcement
    ledger = runtime._engine.ledger
    await ledger.register_stream(stream.stream_id, agent.agent_id)
    
    stream_sui_obj = "0xStream123"
    ledger.save_sui_stream_object(stream.stream_id, stream_sui_obj)
    
    # Save a capability that expired in epoch 1
    ledger.save_capability("0xCap123", stream_sui_obj, verb_bitmask=2, valid_until_epoch=1)
    
    # 2. Attack: Try to publish with expired capability
    with pytest.raises(PermissionError, match="CapabilityExpiredError"):
        await agent.publish(stream, {"attack": "expired_cap"})


@pytest.mark.asyncio
async def test_capability_enforcement_revoked(runtime):
    ws = runtime.workspace("test_sec")
    agent = ws.agent("Alice")
    stream = ws.stream("stream2")
    
    ledger = runtime._engine.ledger
    await ledger.register_stream(stream.stream_id, agent.agent_id)
    
    stream_sui_obj = "0xStream123"
    ledger.save_sui_stream_object(stream.stream_id, stream_sui_obj)
    
    # No capabilities exist (it was revoked)
    # The list is empty
    
    # 2. Attack: Try to publish with revoked/missing capability
    with pytest.raises(PermissionError, match="No capabilities found"):
        await agent.publish(stream, {"attack": "revoked_cap"})


@pytest.mark.asyncio
async def test_capability_enforcement_forged_agent(runtime):
    ws = runtime.workspace("test_sec")
    agent = ws.agent("Alice")
    stream = ws.stream("stream3")
    
    ledger = runtime._engine.ledger
    await ledger.register_stream(stream.stream_id, agent.agent_id)
    
    stream_sui_obj = "0xStream123"
    ledger.save_sui_stream_object(stream.stream_id, stream_sui_obj)
    
    # Save a valid capability
    ledger.save_capability("0xCap123", stream_sui_obj, verb_bitmask=15, valid_until_epoch=0)
    
    # Attack: Terminate the agent status manually to forge a failure state
    ledger.update_agent_status(str(agent.agent_id), AgentStatus.TERMINATED.value)
    
    # Refresh agent identity cache
    agent._identity = ledger.get_agent_identity(str(agent.agent_id))
    
    with pytest.raises(RuntimeError, match="Agent 'Alice' is terminated"):
        await agent.publish(stream, {"attack": "forged_agent"})


@pytest.mark.asyncio
async def test_capability_enforcement_wrong_bitmask(runtime):
    ws = runtime.workspace("test_sec")
    agent = ws.agent("Alice")
    stream = ws.stream("stream4")
    
    ledger = runtime._engine.ledger
    await ledger.register_stream(stream.stream_id, agent.agent_id)
    
    stream_sui_obj = "0xStream123"
    ledger.save_sui_stream_object(stream.stream_id, stream_sui_obj)
    
    # Save a capability with READ ONLY (1)
    ledger.save_capability("0xCap123", stream_sui_obj, verb_bitmask=1, valid_until_epoch=0)
    
    # Attack: Try to WRITE using a READ capability
    with pytest.raises(PermissionError, match="CapabilityExpiredError: No valid write capability"):
        await agent.publish(stream, {"attack": "read_only"})


@pytest.mark.asyncio
async def test_capability_enforcement_success(runtime):
    ws = runtime.workspace("test_sec")
    agent = ws.agent("Alice")
    stream = ws.stream("stream5")
    
    ledger = runtime._engine.ledger
    await ledger.register_stream(stream.stream_id, agent.agent_id)
    
    stream_sui_obj = "0xStream123"
    ledger.save_sui_stream_object(stream.stream_id, stream_sui_obj)
    
    # Save a valid capability with WRITE (2) and infinite expiry
    ledger.save_capability("0xCap123", stream_sui_obj, verb_bitmask=2, valid_until_epoch=0)
    
    # This should succeed
    event = await agent.publish(stream, {"status": "ok"})
    assert event is not None
    assert event.content_blob_id is not None
