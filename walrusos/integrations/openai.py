"""
OpenAI Agents SDK integration — ``WalrusConversationStore``

Persists OpenAI Agents SDK conversation turns to a WalrusOS MemoryStream.
Works with both the Chat Completions messages format and the newer
Agents SDK ``Runner`` / ``Conversation`` pattern.

Usage::

    from walrusos import WalrusOS
    from walrusos.integrations.openai import WalrusConversationStore

    runtime = WalrusOS()
    stream  = runtime.workspace("app").stream("conversations")
    store   = WalrusConversationStore(stream)

    # Sync a full messages array
    await store.sync_messages(thread_id="t-123", messages=[...])

    # Append a single turn
    await store.append_turn(thread_id="t-123", role="assistant", content="Hello!")

    # Retrieve history
    history = await store.get_thread("t-123")

Compatibility: ``openai >= 1.14.0``
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from walrusos.sdk.stream import StreamClient

# Integration requires a bound StreamClient


class WalrusConversationStore:
    """
    Persistent conversation store for the OpenAI Agents SDK.

    Each conversation thread is stored as a sequence of events on the
    WalrusOS MemoryStream, keyed by ``thread_id``.
    """

    def __init__(self, stream: StreamClient) -> None:
        self.stream       = stream

    async def append_turn(
        self,
        thread_id: str,
        role:      str,
        content:   Any,
        *,
        name:      Optional[str]       = None,
        tool_calls: Optional[List[Any]] = None,
        metadata:  Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Append a single conversation turn.

        Args:
            thread_id:  Conversation thread identifier.
            role:       ``"user"``, ``"assistant"``, ``"system"``, or ``"tool"``.
            content:    Message content (str or structured dict).
            name:       Optional agent/tool name.
            tool_calls: Optional list of tool call dicts.
            metadata:   Optional extra context.
        """
        payload: Dict[str, Any] = {
            "type":      "openai_turn",
            "thread_id": thread_id,
            "role":      role,
            "content":   content if isinstance(content, str) else str(content),
            **({"name": name}         if name       else {}),
            **({"tool_calls": tool_calls} if tool_calls else {}),
            **(metadata or {}),
        }
        await self.stream.append(payload, memory_type="working")

    async def sync_messages(
        self,
        thread_id: str,
        messages:  List[Dict[str, Any]],
    ) -> None:
        """
        Persist an entire OpenAI messages array.

        Only the messages not yet in the store are appended (deduplication
        by content hash).  Safe to call after every LLM response.
        """
        existing  = await self.get_thread(thread_id)
        seen_keys = {(m.get("role"), str(m.get("content", ""))) for m in existing}

        for msg in messages:
            key = (msg.get("role"), str(msg.get("content", "")))
            if key not in seen_keys:
                await self.append_turn(
                    thread_id,
                    role    = msg.get("role", "user"),
                    content = msg.get("content", ""),
                    name    = msg.get("name"),
                )
                seen_keys.add(key)

    async def get_thread(
        self,
        thread_id: str,
        limit:     Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all turns for a conversation thread, oldest first.

        Args:
            thread_id: The thread to fetch.
            limit:     Maximum number of turns to return.
        """
        tl = await self.stream.timeline()
        turns = [
            payload
            for _, payload in tl
            if payload.get("type") == "openai_turn"
            and payload.get("thread_id") == thread_id
        ]
        return turns[-limit:] if limit else turns

    async def list_threads(self) -> List[str]:
        """Return all distinct thread IDs stored in this stream."""
        tl = await self.stream.timeline()
        return list({
            payload["thread_id"]
            for _, payload in tl
            if payload.get("type") == "openai_turn" and "thread_id" in payload
        })

    async def delete_thread(self, thread_id: str) -> int:
        """
        Delete all turns for a thread by inserting a tombstone event.

        Returns the number of turns that were logically deleted.
        (Physical deletion is not possible in an append-only DAG.)
        """
        turns = await self.get_thread(thread_id)
        if not turns:
            return 0
        await self.stream.append(
            {"type": "openai_thread_deleted", "thread_id": thread_id, "count": len(turns)},
            memory_type="system"
        )
        return len(turns)

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search across all conversation turns."""
        return await self.stream.search(query, limit=limit)
