"""
CrewAI integration — ``WalrusMemory`` and ``WalrusStorage``

Replaces CrewAI's built-in SQLite/in-process memory with WalrusOS
MemoryStreams so agent episodic memory is persistent and searchable.

Usage::

    from walrusos import WalrusOS
    from walrusos.integrations.crewai import WalrusMemory

    runtime = WalrusOS()
    stream  = runtime.workspace("research").stream("episodes")
    memory  = WalrusMemory(stream)

    crew = Crew(
        agents=[...],
        tasks=[...],
        memory=True,
        long_term_memory=memory,
    )

Compatibility: ``crewai >= 0.20.0``
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from walrusos.sdk.stream import StreamClient

# Integration requires a bound StreamClient

class WalrusMemory:
    """
    Drop-in replacement for CrewAI ``LongTermMemory`` / ``ShortTermMemory``.

    Delegates storage to a WalrusOS ``StreamClient``.  Supports the full
    CrewAI memory interface: ``save``, ``search``, ``reset``, ``get_all``.
    """

    def __init__(self, stream: StreamClient) -> None:
        self.stream = stream

    async def save(self, item: Dict[str, Any]) -> None:
        """
        Persist a memory item (CrewAI task output, observation, etc.).

        The ``item`` dict is stored as an episodic event on the stream.
        """
        await self.stream.append(
            {"type": "crewai_memory", **item},
            memory_type="episodic"
        )

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search across all saved memory items.

        Returns up to ``limit`` results ranked by TF-IDF cosine similarity.
        """
        results = await self.stream.search(query, limit=limit)
        valid_items = await self.get_all()
        # Unwrap metadata to match CrewAI's expected return format
        return [
            {
                "score":    score,
                "metadata": payload,
                "text":     payload.get("result", payload.get("task", "")),
            }
            for payload, score in results
            if any(item == payload for item in valid_items)
        ]

    async def reset(self) -> None:
        """
        Clear all memory for this stream by appending a reset tombstone.
        """
        await self.stream.append(
            {"type": "crewai_reset"},
            memory_type="system"
        )

    async def get_all(self) -> List[Dict[str, Any]]:
        """Return all saved memory items in chronological order after the last reset."""
        tl = await self.stream.timeline()
        last_reset_idx = -1
        for idx, (_, payload) in enumerate(tl):
            if payload.get("type") == "crewai_reset":
                last_reset_idx = idx

        return [
            payload
            for _, payload in tl[last_reset_idx + 1:]
            if payload.get("type") == "crewai_memory"
        ]

    async def count(self) -> int:
        """Return the number of saved memory items."""
        return len(await self.get_all())
