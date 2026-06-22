import asyncio
import pytest
from walrusos.client import WalrusOS

@pytest.fixture
def os():
    return WalrusOS(use_mocks=True)

@pytest.fixture
def workspace(os):
    return os.workspace("test-collab-ws")

@pytest.fixture
def research(workspace):
    return workspace.agent("research")

@pytest.fixture
def writer(workspace):
    return workspace.agent("writer")

@pytest.fixture
def stream(workspace):
    return workspace.stream("shared-stream")

@pytest.mark.asyncio
async def test_subscribe_and_receive(workspace, research, writer, stream):
    received = []
    def callback(ev):
        received.append(ev)
        
    await writer.subscribe(stream, callback)

    # Needs a small sleep to ensure subscription task is registered before publish
    await asyncio.sleep(0.01)
    
    ev = await research.publish(stream, {"msg": "hello world"})
    
    # Wait for callback to be fired via async event loop
    await asyncio.sleep(0.05)
    
    assert len(received) == 1
    # Note: EventBus yields MemoryEvent, we need to read it or check its properties
    mem_ev = received[0]
    payload = await workspace._engine.read(mem_ev.id)
    assert payload["msg"] == "hello world"

@pytest.mark.asyncio
async def test_poll_queues_events(research, writer, stream):
    await writer.subscribe(stream)

    await asyncio.sleep(0.01)
    
    await research.publish(stream, {"msg": "event 1"})
    await research.publish(stream, {"msg": "event 2"})
    await research.publish(stream, {"msg": "event 3"})
    
    await asyncio.sleep(0.05)
    
    events = writer.poll(stream)
    assert len(events) == 3

@pytest.mark.asyncio
async def test_watch_yields_events(research, writer, stream):
    # Fire up the watcher in the background
    async def run_watcher():
        events = []
        try:
            async with asyncio.timeout(1.0):
                async for ev in writer.watch(stream):
                    events.append(ev)
                    break # exit after 1 for test
        except asyncio.TimeoutError:
            pass
        return events
        
    task = asyncio.create_task(run_watcher())
    await asyncio.sleep(0.05)
    
    await research.publish(stream, {"msg": "watch this"})
    
    events = await task
    assert len(events) == 1

@pytest.mark.asyncio
async def test_pipeline_chains_three_agents(workspace, stream):
    a1 = workspace.agent("a1")
    a2 = workspace.agent("a2")
    a3 = workspace.agent("a3")
    
    pipeline = workspace.pipeline([a1, a2, a3], stream)
    
    events = await pipeline.run("start")
    
    assert len(events) == 3

@pytest.mark.asyncio
async def test_broadcast_notifies_all(workspace, stream):
    source = workspace.agent("source")
    recipients = [workspace.agent(f"r{i}") for i in range(3)]
    
    received_counts = [0, 0, 0]
    
    def make_cb(index):
        async def cb(ev):
            if getattr(ev, "agent_id", None) == source._agent_id_str:
                received_counts[index] += 1
                # Simulate a response by publishing back
                await recipients[index].publish(stream, {"msg": f"response from r{index}"})
        return cb
        
    for i, r in enumerate(recipients):
        await r.subscribe(stream, make_cb(i))

    await asyncio.sleep(0.05)
    
    broadcast = workspace.broadcast(source, recipients, stream)
    responses = await broadcast.send("hello all")
    
    assert len(responses) == 3
    assert received_counts == [1, 1, 1]

@pytest.mark.asyncio
async def test_consensus_majority_true(workspace, stream):
    a1 = workspace.agent("a1")
    a2 = workspace.agent("a2")
    a3 = workspace.agent("a3")
    
    # We must orchestrate the responses from the agents since they aren't real AI
    # in this test suite.
    async def simulate_responses():
        await asyncio.sleep(0.1)
        await a1.publish(stream, {"msg": "I approve this"})
        await asyncio.sleep(0.01)
        await a2.publish(stream, {"msg": "Yes"})
        await asyncio.sleep(0.01)
        await a3.publish(stream, {"msg": "I reject this"})
        
    asyncio.create_task(simulate_responses())
    
    consensus = workspace.consensus([a1, a2, a3], stream)
    result = await consensus.vote("Should we proceed?")
    
    assert result.result is True
    assert pytest.approx(result.confidence, abs=0.01) == 0.667

@pytest.mark.asyncio
async def test_task_lifecycle(workspace, research):
    task = workspace.create_task("Fix bug", description="Fix the null pointer")
    
    assert task.task.status == "pending"
    assert task.task.created_by == f"workspace:{workspace.name}"
    
    task.assign(research)
    assert task.task.assigned_to == research._agent_id_str
    
    task.start()
    assert task.task.status == "in_progress"
    
    task.complete(notes="Done!")
    assert task.task.status == "done"
    assert task.task.completed_at is not None

@pytest.mark.asyncio
async def test_task_query_by_status(workspace):
    t1 = workspace.create_task("t1")
    t1.start()
    
    t2 = workspace.create_task("t2") # pending
    t3 = workspace.create_task("t3") # pending
    
    pending_tasks = workspace.tasks(status="pending")
    # Workspace tasks queries return all tasks for the workspace matching the filter.
    # Since sqlite_ledger persists in memory per connection or file, we just count.
    assert len(pending_tasks) >= 2 

@pytest.mark.asyncio
async def test_sync_in_mock_returns_zero(workspace):
    res = await workspace.sync()
    assert res.new_events == 0
    assert res.bytes_downloaded == 0
