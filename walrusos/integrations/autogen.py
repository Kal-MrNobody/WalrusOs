"""
AutoGen integration — ``WalrusMessageStore``

Wraps an AutoGen ``ConversableAgent``'s conversation history so every
message is persisted to a WalrusOS MemoryStream.

Usage::

    from walrusos import WalrusOS
    from walrusos.integrations.autogen import WalrusMessageStore

    runtime = WalrusOS()
    stream  = runtime.workspace("debate").stream("messages")
    store   = WalrusMessageStore(stream)

    # Attach to an AutoGen agent's reply hook
    agent.register_reply(trigger=..., reply_func=store.on_message)

Compatibility: ``pyautogen >= 0.2.20``
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from walrusos.sdk.stream import StreamClient

# Integration requires a bound StreamClient


class WalrusMessageStore:
    """
    Persistent message store for AutoGen multi-agent conversations.

    Stores every sender→receiver message as an immutable event on a
    WalrusOS MemoryStream so the full conversation is auditable and
    replayable after the process exits.
    """

    def __init__(self, stream: StreamClient) -> None:
        self.stream       = stream

    async def on_message(
        self,
        sender:   str,
        receiver: str,
        message:  Any,
        *,
        role:     str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persist a message exchange to the MemoryStream.

        Args:
            sender:   Name or ID of the sending agent.
            receiver: Name or ID of the receiving agent.
            message:  Message content (str, dict, or any JSON-serialisable type).
            role:     OpenAI role string (``"user"``, ``"assistant"``, ``"system"``).
            metadata: Optional extra context to store alongside the message.
        """
        payload: Dict[str, Any] = {
            "type":     "autogen_message",
            "sender":   sender,
            "receiver": receiver,
            "role":     role,
            "message":  message if isinstance(message, str) else str(message),
            **(metadata or {}),
        }
        await self.stream.append(payload, memory_type="semantic")

    async def get_history(
        self,
        sender:   Optional[str] = None,
        receiver: Optional[str] = None,
        limit:    Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve conversation history, optionally filtered.

        Args:
            sender:   Filter by sender name/ID.
            receiver: Filter by receiver name/ID.
            limit:    Maximum number of messages to return (newest last).
        """
        tl = await self.stream.timeline()
        last_clear_idx = -1
        for idx, (_, payload) in enumerate(tl):
            if payload.get("type") == "autogen_clear":
                last_clear_idx = idx

        messages = [
            payload
            for _, payload in tl[last_clear_idx + 1:]
            if payload.get("type") == "autogen_message"
            and (sender is None   or payload.get("sender")   == sender)
            and (receiver is None or payload.get("receiver") == receiver)
        ]
        return messages[-limit:] if limit else messages

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search across all stored messages."""
        results = await self.stream.search(query, limit=limit)
        valid_messages = await self.get_history()
        return [
            payload
            for payload, _ in results
            if any(msg == payload for msg in valid_messages)
        ]

    async def clear(self) -> None:
        """Delete all messages and reset the stream by appending a clear tombstone."""
        await self.stream.append(
            {"type": "autogen_clear"},
            memory_type="system"
        )

    async def count(self) -> int:
        """Return the total number of stored messages."""
        return len(await self.get_history())
