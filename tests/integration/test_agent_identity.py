"""
Integration tests for Protocol Hardening Phase 2: AgentIdentity.
"""
import asyncio
import os
import tempfile
import uuid
from typing import Generator

import pytest

from walrusos import WalrusOS
from walrusos.core.models.agent_identity import AgentIdentity, AgentStatus
from walrusos.sdk.agent import _KEY_PASSWORD


@pytest.fixture
async def runtime():
    """Provide a mock runtime using SQLite locally for testing persistence."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = os.path.join(td, "test.db")
        # Initialize the production adapters with dummy URLs so SQLite gets created
        rt = WalrusOS(
            use_mocks=False,
            db_path=db_path,
            publisher_url="http://mock",
            aggregator_url="http://mock",
        )
        
        # We replace the actual Walrus and Sui adapters with in-memory versions
        # so tests run fast without network calls, but we KEEP the SQLite ledger
        from walrusos.adapters.in_memory import InMemoryStorage, InMemoryVector
        from walrusos.adapters.sqlite_ledger import SQLiteLedger
        
        # Override just storage and vector to avoid real HTTP requests
        rt._storage = InMemoryStorage()
        rt._vector  = InMemoryVector()
        rt._engine.storage = rt._storage
        rt._engine.vector = rt._vector
        
        # Ensure we have the actual SQLiteLedger we want to test
        if not isinstance(rt._engine.ledger, SQLiteLedger):
            # If SuiLedgerAdapter wraps it, extract the internal SQLiteLedger
            rt._engine.ledger = getattr(rt._engine.ledger, "_sqlite", rt._engine.ledger)
            
        try:
            yield rt
        finally:
            # Await any pending background tasks to avoid database lock race
            try:
                loop = asyncio.get_running_loop()
                pending = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
                if pending:
                    await asyncio.wait(pending, timeout=1.0)
            except RuntimeError:
                pass

            # Dispose the SQLAlchemy engine so Windows can delete the tempdir
            if hasattr(rt._engine.ledger, "_engine"):
                rt._engine.ledger._engine.dispose()


@pytest.mark.asyncio
async def test_agent_identity_creation(runtime: WalrusOS):
    """Test that creating an agent mints a persistent AgentIdentity."""
    ws = runtime.workspace("test_ws")
    
    # 1. Accessing the agent implicitly creates its identity
    agent = ws.agent("Alice")
    
    assert agent.identity is not None
    assert agent.identity.agent_name == "Alice"
    assert agent.identity.status == AgentStatus.ACTIVE
    assert agent.identity.execution_counter == 0
    assert agent.identity.trust_root != ""
    assert len(agent.identity.public_key) == 64  # 32 bytes hex encoded
    
    # 2. Key should be in KeyStore
    ledger = runtime._engine.ledger
    priv_key = ledger.load_agent_private_key(agent.identity.agent_id, _KEY_PASSWORD())
    assert priv_key is not None
    assert len(priv_key) == 32
    
    
@pytest.mark.asyncio
async def test_agent_counters(runtime: WalrusOS):
    """Test that publishing events increments agent counters atomically."""
    ws = runtime.workspace("test_ws")
    agent = ws.agent("Bob")
    stream = ws.stream("logs")
    
    assert agent.identity.execution_counter == 0
    assert agent.identity.memory_counter == 0
    
    await agent.publish(stream, {"msg": "hello"})
    
    # Refresh identity
    id1 = agent.identity
    assert id1.execution_counter == 1
    assert id1.memory_counter == 1
    
    await agent.publish(stream, {"msg": "world"})
    
    id2 = agent.identity
    assert id2.execution_counter == 2
    assert id2.memory_counter == 2


@pytest.mark.asyncio
async def test_agent_status_lifecycle(runtime: WalrusOS):
    """Test pausing and terminating agents."""
    ws = runtime.workspace("test_ws")
    agent = ws.agent("Charlie")
    stream = ws.stream("logs")
    
    # Pause agent
    agent.pause()
    assert agent.identity.status == AgentStatus.PAUSED
    
    with pytest.raises(RuntimeError, match="is paused"):
        await agent.publish(stream, {"msg": "fail"})
        
    # Resume agent
    agent.resume()
    assert agent.identity.status == AgentStatus.ACTIVE
    await agent.publish(stream, {"msg": "ok"})  # should succeed
    
    # Terminate agent
    agent.terminate()
    assert agent.identity.status == AgentStatus.TERMINATED
    
    with pytest.raises(RuntimeError, match="is terminated"):
        await agent.publish(stream, {"msg": "fail2"})
        
        
@pytest.mark.asyncio
async def test_memory_event_agent_stamping(runtime: WalrusOS):
    """Test that MemoryEvents get stamped with the agent's identity."""
    ws = runtime.workspace("test_ws")
    agent = ws.agent("Dave")
    stream = ws.stream("logs")
    
    # Grab the pre-event trust root since publishing advances the trust root
    pre_trust_root = agent.identity.trust_root
    
    event = await agent.publish(stream, {"msg": "hello"})
    
    # 1. The returned event object has the agent_id
    assert event.agent_id == agent.identity.agent_id
    
    # 2. The event in SQLite has the agent_id
    ledger = runtime._engine.ledger
    ev_record = await ledger.get_event(event.id)
    assert getattr(ev_record, "agent_id", None) == agent.identity.agent_id
    
    # 3. The payload envelope has the identity metadata
    payload = await runtime._engine.read(event.id)
    assert payload["agent_id"] == agent.identity.agent_id
    assert payload["trust_root"] == pre_trust_root
    assert payload["public_key"] == agent.identity.public_key
