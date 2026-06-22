"""
Integration tests for all five framework integrations.

Uses WalrusOS mock adapters so no network or LLM is required.

Heavy third-party frameworks (crewai, autogen/pyautogen, openai, llama-index)
are NOT installed by `.[dev]`. CI doesn't install `.[integrations]` because
those packages have heavy native dependencies (chromadb, etc.) that often
fail to build on Windows runners. The importorskip calls below cause this
whole test module to skip cleanly when any framework is missing, instead of
crashing pytest collection with ImportError.

To run these tests locally: `pip install -e .[integrations]`.
"""
from __future__ import annotations

import asyncio
import uuid
import pytest

# Skip the entire module if any required framework isn't installed.
pytest.importorskip("crewai")
pytest.importorskip("autogen")
pytest.importorskip("openai")
pytest.importorskip("llama_index")

from walrusos import WalrusOS
from walrusos.integrations.crewai    import WalrusMemory
from walrusos.integrations.autogen   import WalrusMessageStore
from walrusos.integrations.openai    import WalrusConversationStore
from walrusos.integrations.llamaindex import WalrusChatStore, WalrusDocumentStore


# ── CrewAI ────────────────────────────────────────────────────────────────────

class TestWalrusMemory:
    @pytest.fixture
    def memory(self) -> WalrusMemory:
        rt     = WalrusOS(use_mocks=True)
        stream = rt.workspace("crewai").stream("episodes")
        return WalrusMemory(stream)

    async def test_save_and_get_all(self, memory: WalrusMemory) -> None:
        await memory.save({"task": "research", "result": "found 10 papers"})
        await memory.save({"task": "write",    "result": "drafted introduction"})
        all_items = await memory.get_all()
        assert len(all_items) == 2

    async def test_search_returns_results(self, memory: WalrusMemory) -> None:
        await memory.save({"task": "machine learning", "result": "trained model"})
        results = await memory.search("machine learning model", limit=5)
        assert isinstance(results, list)

    async def test_count(self, memory: WalrusMemory) -> None:
        await memory.save({"x": 1})
        await memory.save({"x": 2})
        assert await memory.count() == 2

    async def test_reset_clears_memory(self, memory: WalrusMemory) -> None:
        await memory.save({"x": 1})
        await memory.reset()
        all_items = await memory.get_all()
        assert all_items == []


# ── AutoGen ───────────────────────────────────────────────────────────────────

class TestWalrusMessageStore:
    @pytest.fixture
    def store(self) -> WalrusMessageStore:
        rt     = WalrusOS(use_mocks=True)
        stream = rt.workspace("autogen").stream("dialogue")
        return WalrusMessageStore(stream)

    async def test_on_message_and_get_history(self, store: WalrusMessageStore) -> None:
        await store.on_message("Alice", "Bob", "Hello Bob!")
        await store.on_message("Bob",   "Alice", "Hello Alice!")
        history = await store.get_history()
        assert len(history) == 2

    async def test_get_history_filter_sender(self, store: WalrusMessageStore) -> None:
        await store.on_message("Alice", "Bob",   "msg1")
        await store.on_message("Bob",   "Alice", "msg2")
        alice_msgs = await store.get_history(sender="Alice")
        assert len(alice_msgs) == 1
        assert alice_msgs[0]["sender"] == "Alice"

    async def test_get_history_limit(self, store: WalrusMessageStore) -> None:
        for i in range(10):
            await store.on_message("A", "B", f"msg {i}")
        history = await store.get_history(limit=3)
        assert len(history) == 3

    async def test_count(self, store: WalrusMessageStore) -> None:
        await store.on_message("A", "B", "x")
        assert await store.count() == 1

    async def test_search(self, store: WalrusMessageStore) -> None:
        await store.on_message("A", "B", "neural network training loss")
        results = await store.search("training loss", limit=5)
        assert isinstance(results, list)

    async def test_clear(self, store: WalrusMessageStore) -> None:
        await store.on_message("A", "B", "to-be-deleted")
        await store.clear()
        # After clear the stream is reset
        assert await store.count() == 0


# ── OpenAI ────────────────────────────────────────────────────────────────────

class TestWalrusConversationStore:
    @pytest.fixture
    def store(self) -> WalrusConversationStore:
        rt     = WalrusOS(use_mocks=True)
        stream = rt.workspace("openai").stream("threads")
        return WalrusConversationStore(stream)

    async def test_append_turn(self, store: WalrusConversationStore) -> None:
        await store.append_turn("t1", "user",      "Hello")
        await store.append_turn("t1", "assistant", "Hi there!")
        thread = await store.get_thread("t1")
        assert len(thread) == 2

    async def test_sync_messages_dedup(self, store: WalrusConversationStore) -> None:
        messages = [
            {"role": "user",      "content": "What is AI?"},
            {"role": "assistant", "content": "AI is..."},
        ]
        await store.sync_messages("t2", messages)
        await store.sync_messages("t2", messages)  # Second sync should not duplicate
        thread = await store.get_thread("t2")
        assert len(thread) == 2

    async def test_list_threads(self, store: WalrusConversationStore) -> None:
        await store.append_turn("t-alpha", "user", "msg")
        await store.append_turn("t-beta",  "user", "msg")
        threads = await store.list_threads()
        assert "t-alpha" in threads
        assert "t-beta"  in threads

    async def test_get_thread_limit(self, store: WalrusConversationStore) -> None:
        for i in range(10):
            await store.append_turn("t3", "user", f"msg {i}")
        thread = await store.get_thread("t3", limit=3)
        assert len(thread) == 3

    async def test_delete_thread_tombstone(self, store: WalrusConversationStore) -> None:
        await store.append_turn("t-del", "user", "to be deleted")
        count = await store.delete_thread("t-del")
        assert count == 1


# ── LlamaIndex Chat Store ─────────────────────────────────────────────────────

class _FakeMessage:
    def __init__(self, role: str, content: str) -> None:
        self.role    = role
        self.content = content


class TestWalrusChatStore:
    @pytest.fixture
    def store(self) -> WalrusChatStore:
        rt     = WalrusOS(use_mocks=True)
        stream = rt.workspace("llama").stream("chat")
        return WalrusChatStore(stream)

    async def test_add_and_get_messages(self, store: WalrusChatStore) -> None:
        await store.add_message("session1", _FakeMessage("user",      "Hello"))
        await store.add_message("session1", _FakeMessage("assistant", "Hi!"))
        msgs = await store.get_messages("session1")
        assert len(msgs) == 2

    async def test_get_messages_key_isolation(self, store: WalrusChatStore) -> None:
        await store.add_message("s1", _FakeMessage("user", "a"))
        await store.add_message("s2", _FakeMessage("user", "b"))
        assert len(await store.get_messages("s1")) == 1
        assert len(await store.get_messages("s2")) == 1

    async def test_get_keys(self, store: WalrusChatStore) -> None:
        await store.add_message("k1", _FakeMessage("user", "msg"))
        await store.add_message("k2", _FakeMessage("user", "msg"))
        keys = await store.get_keys()
        assert "k1" in keys and "k2" in keys

    async def test_delete_messages(self, store: WalrusChatStore) -> None:
        await store.add_message("s3", _FakeMessage("user", "msg"))
        deleted = await store.delete_messages("s3")
        assert deleted is not None
        assert len(deleted) == 1

    async def test_delete_last_message(self, store: WalrusChatStore) -> None:
        await store.add_message("s4", _FakeMessage("user", "first"))
        await store.add_message("s4", _FakeMessage("user", "last"))
        deleted = await store.delete_last_message("s4")
        assert deleted is not None
        assert deleted["content"] == "last"


# ── LlamaIndex Document Store ─────────────────────────────────────────────────

class TestWalrusDocumentStore:
    @pytest.fixture
    def store(self) -> WalrusDocumentStore:
        rt     = WalrusOS(use_mocks=True)
        stream = rt.workspace("llama").stream("docs")
        return WalrusDocumentStore(stream)

    async def test_add_and_get_document(self, store: WalrusDocumentStore) -> None:
        await store.add_document("d1", "Introduction to machine learning",
                                  {"source": "textbook"})
        doc = await store.get_document("d1")
        assert doc is not None
        assert doc["text"] == "Introduction to machine learning"

    async def test_search_finds_document(self, store: WalrusDocumentStore) -> None:
        await store.add_document("d2", "Attention is all you need transformers", {})
        results = await store.search("transformer attention mechanism")
        assert len(results) > 0

    async def test_list_document_ids(self, store: WalrusDocumentStore) -> None:
        await store.add_document("d3", "some text", {})
        await store.add_document("d4", "more text", {})
        ids = await store.list_document_ids()
        assert "d3" in ids and "d4" in ids

    async def test_delete_document(self, store: WalrusDocumentStore) -> None:
        await store.add_document("d5", "to be deleted", {})
        result = await store.delete_document("d5")
        assert result is True
        doc = await store.get_document("d5")
        assert doc is None

    async def test_delete_nonexistent_returns_false(self, store: WalrusDocumentStore) -> None:
        result = await store.delete_document("nonexistent")
        assert result is False
