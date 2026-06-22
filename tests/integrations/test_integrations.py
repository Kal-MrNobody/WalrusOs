import pytest

# Skip the entire module if any required framework isn't installed.
# CI installs .[dev] only; these heavy frameworks live in .[integrations]
# and frequently fail to build on Windows runners. Run locally with:
#     pip install -e .[integrations]
pytest.importorskip("langgraph")
pytest.importorskip("crewai")
pytest.importorskip("autogen")
pytest.importorskip("llama_index")
pytest.importorskip("openai")
pytest.importorskip("pydantic_ai")

from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver
from walrusos.integrations.crewai import WalrusMemory
from walrusos.integrations.autogen import WalrusMessageStore
from walrusos.integrations.llamaindex import WalrusChatStore, WalrusDocumentStore
from walrusos.integrations.openai import WalrusConversationStore
from walrusos.integrations.pydantic_ai import WalrusMessageHistory

@pytest.fixture
def runtime():
    return WalrusOS(use_mocks=True)

@pytest.mark.asyncio
async def test_langgraph(runtime):
    stream = runtime.workspace("test").agent("lg").stream("chk")
    saver = AsyncWalrusSaver(stream)
    await saver.aput({"configurable": {"thread_id": "1"}}, {"id": "c1", "ts": "2026"}, {})
    chk = await saver.aget_tuple({"configurable": {"thread_id": "1"}})
    assert chk.checkpoint["id"] == "c1"

@pytest.mark.asyncio
async def test_crewai(runtime):
    stream = runtime.workspace("test").agent("crew").stream("mem")
    memory = WalrusMemory(stream)
    await memory.save({"task": "A", "output": "B"})
    items = await memory.get_all()
    assert len(items) == 1
    assert items[0]["task"] == "A"

@pytest.mark.asyncio
async def test_autogen(runtime):
    stream = runtime.workspace("test").agent("autogen").stream("msg")
    store = WalrusMessageStore(stream)
    await store.on_message("u", "a", "hello")
    hist = await store.get_history()
    assert len(hist) == 1
    assert hist[0]["message"] == "hello"

@pytest.mark.asyncio
async def test_llamaindex(runtime):
    stream = runtime.workspace("test").agent("li").stream("chat")
    store = WalrusChatStore(stream)
    class Msg:
        role = "user"
        content = "hello"
        additional_kwargs = {}
    await store.add_message("1", Msg())
    msgs = await store.get_messages("1")
    assert msgs[0]["content"] == "hello"

@pytest.mark.asyncio
async def test_openai(runtime):
    stream = runtime.workspace("test").agent("openai").stream("conv")
    store = WalrusConversationStore(stream)
    await store.append_turn("t1", "user", "hello")
    turns = await store.get_thread("t1")
    assert turns[0]["content"] == "hello"

@pytest.mark.asyncio
async def test_pydantic_ai(runtime):
    stream = runtime.workspace("test").agent("pydantic").stream("hist")
    history = WalrusMessageHistory(stream)
    await history.sync_messages([{"role": "user", "content": "hi"}])
    msgs = await history.get_messages()
    assert len(msgs) == 1
    assert msgs[0]["content"] == "hi"
