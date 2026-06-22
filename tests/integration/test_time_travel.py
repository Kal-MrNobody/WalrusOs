import uuid
import pytest
from datetime import datetime, timezone
from walrusos.engine.time_travel import TimeTravelEngine
from walrusos.core.models.events import ProtocolEvent, EventType

from walrusos.adapters.in_memory import InMemoryLedger, InMemoryStorage

@pytest.fixture
def mock_ledger():
    return InMemoryLedger()

@pytest.fixture
def mock_storage():
    return InMemoryStorage()

@pytest.fixture
def engine(mock_ledger, mock_storage):
    return TimeTravelEngine(ledger=mock_ledger, storage=mock_storage)

@pytest.mark.asyncio
async def test_time_travel_fork_and_lca(engine, mock_ledger):
    agent_id = str(uuid.uuid4())
    wallet = "0x123"
    stream_a = str(uuid.uuid4())
    
    # 1. Create base stream
    event1 = ProtocolEvent(
        event_id="hash_1",
        event_type=EventType.MemoryAppended,
        workspace_id="ws_1",
        agent_id=agent_id,
        wallet=wallet,
        payload={"msg": "A"},
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    event2 = ProtocolEvent(
        event_id="hash_2",
        event_type=EventType.MemoryAppended,
        workspace_id="ws_1",
        agent_id=agent_id,
        wallet=wallet,
        parent_event="hash_1",
        payload={"msg": "B"},
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await mock_ledger.append_event(uuid.UUID(stream_a), event1)
    await mock_ledger.append_event(uuid.UUID(stream_a), event2)
    
    # 2. Fork at event1
    stream_b = await engine.fork_stream(
        agent_id=agent_id,
        wallet=wallet,
        original_stream=stream_a,
        fork_event_id="hash_1",
        private_key_hex=""
    )
    
    assert stream_b != stream_a
    
    # 3. Append to branch B
    event3 = ProtocolEvent(
        event_id="hash_3",
        event_type=EventType.MemoryAppended,
        workspace_id="ws_1",
        agent_id=agent_id,
        wallet=wallet,
        parent_event="hash_1", # Technically parent of the payload logic, but it branches after MemoryForked
        payload={"msg": "C"},
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    await mock_ledger.append_event(uuid.UUID(stream_b), event3)
    
    # 4. Find LCA
    lca, div_a, div_b = await engine.find_lca(stream_a, stream_b)
    
    assert lca is not None
    assert lca.event_id == "hash_1"
    
    # Branch A diverges with event2
    assert len(div_a) == 1
    assert div_a[0].event_id == "hash_2"
    
    # Branch B diverges with MemoryForked and event3
    assert len(div_b) == 2
    assert div_b[0].event_type == EventType.MemoryForked
    assert div_b[1].event_id == "hash_3"

@pytest.mark.asyncio
async def test_time_travel_merge(engine, mock_ledger):
    agent_id = str(uuid.uuid4())
    wallet = "0x123"
    stream_a = str(uuid.uuid4())
    
    # Setup some events...
    event1 = ProtocolEvent(
        event_id="hash_1",
        event_type=EventType.MemoryAppended,
        workspace_id="ws_1",
        agent_id=agent_id,
        wallet=wallet,
        payload={"msg": "A"}
    )
    await mock_ledger.append_event(uuid.UUID(stream_a), event1)
    
    # Fork
    stream_b = await engine.fork_stream(
        agent_id=agent_id, wallet=wallet, original_stream=stream_a, fork_event_id="hash_1", private_key_hex=""
    )
    
    # Merge B back into A
    merge_event_id = await engine.merge_streams(
        agent_id=agent_id, wallet=wallet, source_stream=stream_b, target_stream=stream_a, private_key_hex=""
    )
    
    assert merge_event_id is not None
    
    # Verify merge event was appended to A
    events_a = await mock_ledger.list_events(uuid.UUID(stream_a))
    assert events_a[-1].event_type == EventType.MemoryMerged
    assert events_a[-1].payload["merged_from_stream"] == stream_b
