import pytest
import os
import asyncio
from walrusos.client import WalrusOS

@pytest.fixture(autouse=True)
def use_mocks():
    os.environ["WALRUSOS_USE_MOCKS"] = "1"
    yield
    del os.environ["WALRUSOS_USE_MOCKS"]

@pytest.mark.asyncio
async def test_memory_intelligence_enrichment():
    wos = WalrusOS()
    workspace = wos.workspace("test-intelligence-workspace")
    agent = workspace.agent("test-agent")
    stream = agent.stream("test-stream")

    # Part A: Enrichment
    await stream.append(
        {"action": "research", "topic": "transformers", "result": "Self-attention replaces recurrence."},
        memory_type="observation",
        tags=["research", "ai"],
        importance=0.8,
        project="phase-1"
    )
    
    tl = await stream.latest(1)
    assert len(tl) == 1
    event, payload = tl[0]
    assert event.memory_type == "observation"
    assert event.tags == ["research", "ai"]
    assert event.importance == 0.8
    assert event.project == "phase-1"
    assert payload["topic"] == "transformers"
    assert payload["action"] == "research"

@pytest.mark.asyncio
async def test_memory_search_methods():
    wos = WalrusOS()
    workspace = wos.workspace("test-search-workspace")
    agent = workspace.agent("search-agent")
    stream = agent.stream("search-stream")

    await stream.append({"msg": "event one"}, tags=["tag1"], memory_type="observation")
    await stream.append({"msg": "event two"}, tags=["tag2"], memory_type="working")
    await stream.append({"msg": "event three"}, tags=["tag1"], memory_type="observation")

    # By Type
    obs = await stream.by_type("observation")
    assert len(obs) == 2
    
    # By Tag
    tag1_events = await stream.by_tag("tag1")
    assert len(tag1_events) == 2
    
    # Latest (returns chronological order of latest n)
    latest = await stream.latest(2)
    assert latest[0][1]["msg"] == "event two"
    assert latest[1][1]["msg"] == "event three"

@pytest.mark.asyncio
async def test_memory_summarizer_and_context():
    wos = WalrusOS()
    workspace = wos.workspace("test-context-workspace")
    agent = workspace.agent("context-agent")
    stream = agent.stream("context-stream")

    await stream.append({"msg": "The quick brown fox jumps over the lazy dog."})
    await stream.append({"msg": "A fast brown fox leaps over a sleeping dog."})
    
    # Checkpoint
    checkpoint_id = await stream.checkpoint("Test Checkpoint")
    assert checkpoint_id
    
    # After checkpoint, append more
    await stream.append({"msg": "It's raining outside."})
    
    # Build Context using smart strategy
    context = await agent.build_context(stream, query="fox", max_tokens=1000, strategy="smart")
    
    # Should include checkpoint summary
    assert "--- PREVIOUS CHECKPOINT ---" in context
    assert "fox" in context.lower()
    assert "raining" in context
