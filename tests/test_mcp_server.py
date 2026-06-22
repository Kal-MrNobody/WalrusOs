import pytest
import os
import json
from walrusos.mcp.server import list_tools, call_tool

# Set up mocks before testing
os.environ["WALRUSOS_USE_MOCKS"] = "1"

@pytest.mark.asyncio
async def test_all_tools_registered():
    tools = await list_tools()
    tool_names = [t.name for t in tools]
    
    expected_tools = [
        "memory_search",
        "memory_append",
        "memory_latest",
        "memory_context",
        "workspace_sync",
        "agent_status",
        "memory_timeline"
    ]
    for expected in expected_tools:
        assert expected in tool_names

@pytest.mark.asyncio
async def test_memory_append_tool():
    result = await call_tool("memory_append", {"content": "Test memory"})
    
    assert len(result) == 1
    text = result[0].text
    assert "Saved. Blob: mock_blob_" in text or "Saved. Blob:" in text

@pytest.mark.asyncio
async def test_memory_search_tool():
    # First append something so there's a result
    await call_tool("memory_append", {"content": "searchable test memory"})
    
    result = await call_tool("memory_search", {"query": "searchable test"})
    assert len(result) == 1
    text = result[0].text
    
    assert len(text) > 0
    assert "searchable test" in text

@pytest.mark.asyncio
async def test_memory_context_tool():
    result = await call_tool("memory_context", {"max_tokens": 500})
    
    assert len(result) == 1
    text = result[0].text
    assert isinstance(text, str)
    # The context should respect max_tokens, meaning character count is likely < 2500
    assert len(text) < 2500

@pytest.mark.asyncio
async def test_memory_latest_tool():
    # Append 3 events
    await call_tool("memory_append", {"content": "Event 1"})
    await call_tool("memory_append", {"content": "Event 2"})
    await call_tool("memory_append", {"content": "Event 3"})
    
    result = await call_tool("memory_latest", {"n": 3})
    assert len(result) == 1
    text = result[0].text
    
    # Text should have 3 entries
    assert text.count("---") >= 3

@pytest.mark.asyncio
async def test_agent_status_tool():
    result = await call_tool("agent_status", {})
    assert len(result) == 1
    text = result[0].text
    
    assert isinstance(text, str)
