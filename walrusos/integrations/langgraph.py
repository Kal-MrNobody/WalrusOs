"""
LangGraph integration — ``AsyncWalrusSaver``

Replaces LangGraph's built-in ``MemorySaver`` with a WalrusOS
MemoryStream so graph state is persisted to Walrus and anchored on Sui.

Usage::

    from walrusos import WalrusOS
    from walrusos.integrations.langgraph import AsyncWalrusSaver

    runtime = WalrusOS()
    stream  = runtime.workspace("my-app").stream("checkpoints")
    memory  = AsyncWalrusSaver(stream)

    graph = builder.compile(checkpointer=memory)
    # Use graph normally — checkpoints go to WalrusOS automatically

Compatibility: ``langgraph >= 0.0.30``
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncIterator, Dict, Iterator, Optional, Sequence, Tuple

from walrusos.sdk.stream import StreamClient

try:
    from langgraph.checkpoint.base import (  # type: ignore[import]
        BaseCheckpointSaver,
        Checkpoint,
        CheckpointMetadata,
        CheckpointTuple,
        SerializerProtocol,
    )
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    BaseCheckpointSaver = object  # type: ignore[assignment,misc]
    Checkpoint          = dict    # type: ignore[assignment,misc]
    CheckpointMetadata  = dict    # type: ignore[assignment,misc]
    CheckpointTuple     = tuple   # type: ignore[assignment,misc]

# Integration requires a bound StreamClient (created via agent.stream())
class AsyncWalrusSaver(BaseCheckpointSaver):  # type: ignore[misc]
    """
    LangGraph ``BaseCheckpointSaver`` backed by a WalrusOS ``StreamClient``.

    All checkpoint operations are async; the sync ``put`` and ``get`` methods
    raise ``NotImplementedError`` to guide users to the correct async API.
    """

    def __init__(self, stream: StreamClient) -> None:
        if not _LANGGRAPH_AVAILABLE:
            raise ImportError(
                "langgraph is required: pip install langgraph"
            )
        super().__init__()
        self.stream = stream

    # ── Async API (use these) ────────────────────────────────────────────────

    async def aput(  # type: ignore[override]
        self,
        config:     Dict[str, Any],
        checkpoint: Checkpoint,
        metadata:   CheckpointMetadata,
    ) -> Dict[str, Any]:
        """Persist a LangGraph checkpoint to the WalrusOS stream."""
        payload: Dict[str, Any] = {
            "type":           "langgraph_checkpoint",
            "thread_id":      config.get("configurable", {}).get("thread_id", ""),
            "checkpoint_id":  checkpoint["id"],
            "ts":             checkpoint["ts"],
            "channel_values": checkpoint.get("channel_values", {}),
            "channel_versions": checkpoint.get("channel_versions", {}),
            "versions_seen":    checkpoint.get("versions_seen", {}),
            "metadata":       dict(metadata),
        }
        await self.stream.append(payload, memory_type="langgraph")

        return {
            "configurable": {
                "thread_id":     payload["thread_id"],
                "checkpoint_id": payload["checkpoint_id"],
            }
        }

    async def aput_writes(  # type: ignore[override]
        self,
        config:  Dict[str, Any],
        writes:  Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Persist intermediate writes (channel patches) for a task."""
        payload: Dict[str, Any] = {
            "type":      "langgraph_writes",
            "task_id":   task_id,
            "thread_id": config.get("configurable", {}).get("thread_id", ""),
            "writes":    {k: v for k, v in writes},
        }
        await self.stream.append(payload, memory_type="langgraph_write")

    async def aget_tuple(  # type: ignore[override]
        self,
        config: Dict[str, Any],
    ) -> Optional[CheckpointTuple]:
        """
        Retrieve the most recent checkpoint for the given thread_id.

        Scans the stream timeline in reverse to find the latest checkpoint
        matching ``config["configurable"]["thread_id"]``.
        """
        thread_id = config.get("configurable", {}).get("thread_id", "")
        tl = await self.stream.timeline()

        for event, payload in reversed(tl):
            if (
                payload.get("type") == "langgraph_checkpoint"
                and payload.get("thread_id") == thread_id
            ):
                checkpoint: Checkpoint = {  # type: ignore[assignment]
                    "v":                1,
                    "id":               payload["checkpoint_id"],
                    "ts":               payload["ts"],
                    "channel_values":   payload.get("channel_values", {}),
                    "channel_versions": payload.get("channel_versions", {}),
                    "versions_seen":    payload.get("versions_seen", {}),
                }
                return CheckpointTuple(  # type: ignore[return-value]
                    config=config,
                    checkpoint=checkpoint,
                    metadata=payload.get("metadata", {}),
                    parent_config=None,
                )
        return None

    async def alist(  # type: ignore[override]
        self,
        config: Optional[Dict[str, Any]],
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        limit:  Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:  # type: ignore[override]
        """Iterate over all checkpoints, newest first."""
        thread_id = (config or {}).get("configurable", {}).get("thread_id")
        tl = await self.stream.timeline()
        count = 0
        for event, payload in reversed(tl):
            if payload.get("type") != "langgraph_checkpoint":
                continue
            if thread_id and payload.get("thread_id") != thread_id:
                continue
            if limit is not None and count >= limit:
                break
            checkpoint: Checkpoint = {  # type: ignore[assignment]
                "v":                1,
                "id":               payload["checkpoint_id"],
                "ts":               payload["ts"],
                "channel_values":   payload.get("channel_values", {}),
                "channel_versions": payload.get("channel_versions", {}),
                "versions_seen":    payload.get("versions_seen", {}),
            }
            yield CheckpointTuple(  # type: ignore[misc]
                config={"configurable": {"thread_id": payload["thread_id"]}},
                checkpoint=checkpoint,
                metadata=payload.get("metadata", {}),
                parent_config=None,
            )
            count += 1

    # ── Sync API stubs (guide users to async) ────────────────────────────────

    def put(
        self,
        config:     Dict[str, Any],
        checkpoint: Checkpoint,
        metadata:   CheckpointMetadata,
    ) -> Dict[str, Any]:
        """Sync put is not supported.  Use ``aput`` with an async graph."""
        raise NotImplementedError(
            "AsyncWalrusSaver requires an async graph. "
            "Compile your graph with `acompile()` and execute with `ainvoke()`."
        )

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        """Sync get is not supported.  Use ``aget_tuple``."""
        raise NotImplementedError("Use ``aget_tuple`` in an async context.")

    def list(
        self,
        config: Optional[Dict[str, Any]],
        **kwargs: Any,
    ) -> Iterator[CheckpointTuple]:
        """Sync list is not supported.  Use ``alist``."""
        raise NotImplementedError("Use ``alist`` in an async context.")
