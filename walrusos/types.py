"""
walrusos.types — Public type definitions for the WalrusOS SDK.

Import these from the top-level package:

    from walrusos import MemoryType
    await stream.append(payload, memory_type=MemoryType.EPISODIC)
"""
from __future__ import annotations

from enum import Enum


class MemoryType(str, Enum):
    """
    Classification for a memory event.

    WalrusOS stores all types identically — this is a developer-facing
    label that helps you organise and filter events during replay or search.

    Example::

        await stream.append({"fact": "..."}, memory_type=MemoryType.SEMANTIC)
        await stream.append({"turn": 1, ...}, memory_type=MemoryType.EPISODIC)

    Values are plain strings, so you can also pass the string directly:

        await stream.append(payload, memory_type="episodic")
    """

    SEMANTIC   = "semantic"    # Facts and long-term knowledge
    EPISODIC   = "episodic"    # Specific experiences, conversation turns
    PROCEDURAL = "procedural"  # How to do things — learned skills
    WORKING    = "working"     # Short-term scratchpad for the current task
    SYSTEM     = "system"      # Infrastructure events (checkpoints, recovery)

    # Framework-internal values (used by integrations, not by developers)
    _LANGGRAPH       = "langgraph"
    _LANGGRAPH_WRITE = "langgraph_write"

    def __str__(self) -> str:  # lets str(MemoryType.EPISODIC) == "episodic"
        return self.value


# ── Convenience alias ─────────────────────────────────────────────────────────

#: Shorthand for ``MemoryType`` — identical object, shorter name.
MT = MemoryType
