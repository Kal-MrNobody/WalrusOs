"""
PydanticAI integration — ``WalrusMessageHistory``

Persists PydanticAI ModelMessages to a WalrusOS MemoryStream.

Usage::

    from walrusos import WalrusOS
    from walrusos.integrations.pydantic_ai import WalrusMessageHistory

    runtime = WalrusOS()
    stream  = runtime.workspace("default").agent("pydantic").stream("history")
    history = WalrusMessageHistory(stream)

    # Fetch previous messages
    msgs = await history.get_messages()

    # Run agent
    result = await agent.run("Hello", message_history=msgs)

    # Sync back the entire message history to WalrusOS
    await history.sync_messages(result.new_messages())

Compatibility: ``pydantic-ai >= 0.0.12``
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from walrusos.sdk.stream import StreamClient


class WalrusMessageHistory:
    """
    Persistent message history for PydanticAI Agents.

    Stores PydanticAI messages as an append-only sequence on a
    WalrusOS MemoryStream.
    """

    def __init__(self, stream: StreamClient) -> None:
        self.stream = stream

    async def append_message(self, message: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Append a single PydanticAI ModelMessage (or generic dict).
        """
        payload: Dict[str, Any] = {
            "type": "pydantic_ai_message",
            "message": message if isinstance(message, dict) else (
                message.model_dump() if hasattr(message, "model_dump") else str(message)
            ),
            **(metadata or {}),
        }
        await self.stream.append(payload, memory_type="working")

    async def sync_messages(self, messages: List[Any]) -> None:
        """
        Persist a list of PydanticAI messages (e.g., from `result.new_messages()`).
        
        This deduplicates against the existing stream so only new messages are appended.
        """
        existing_timeline = await self.stream.timeline()
        # Create a set of serialized messages to avoid duplicates
        seen = {
            json.dumps(payload.get("message", {}), sort_keys=True)
            for _, payload in existing_timeline
            if payload.get("type") == "pydantic_ai_message"
        }

        for msg in messages:
            msg_dump = msg if isinstance(msg, dict) else (
                msg.model_dump() if hasattr(msg, "model_dump") else str(msg)
            )
            msg_str = json.dumps(msg_dump, sort_keys=True)
            if msg_str not in seen:
                await self.append_message(msg_dump)
                seen.add(msg_str)

    async def get_messages(self, limit: Optional[int] = None) -> List[Any]:
        """
        Retrieve all PydanticAI messages stored in the stream, oldest first.
        
        Returns raw dicts which PydanticAI can accept, or which can be 
        parsed back into ModelMessage objects by the application.
        """
        tl = await self.stream.timeline()
        msgs = [
            payload["message"]
            for _, payload in tl
            if payload.get("type") == "pydantic_ai_message" and "message" in payload
        ]
        return msgs[-limit:] if limit else msgs

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search across all PydanticAI messages."""
        return await self.stream.search(query, limit=limit)
