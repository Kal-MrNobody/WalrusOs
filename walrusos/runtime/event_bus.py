"""
EventMesh — central nervous system for multi-agent WalrusOS.

Supports:
  • Stream subscriptions (existing): agents react when a stream gets a new event
  • Topic subscriptions (NEW):       agents react to named event types
  • Wildcard matching:               "memory.*", "task.*", "*"
  • Queue-based (poll) mode:         subscribe without a callback → poll() later
  • Bridge forwarding:               POST /internal/event to dashboard WebSocket

Backward compat: EventBus = EventMesh at module level.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from walrusos.core.models.memory import MemoryEvent

logger = logging.getLogger(__name__)


class EventMesh:
    """
    Central event routing layer for the WalrusOS multi-agent runtime.
    """

    def __init__(self) -> None:
        # stream_id (str) → [(agent_id, callback | None)]
        self._stream_subs: Dict[str, List[tuple]] = {}
        # pattern (str)   → [(agent_id, callback)]
        self._topic_subs:  Dict[str, List[tuple]] = {}
        # "agent_id:stream_id" → asyncio.Queue  (poll mode)
        self._queues:      Dict[str, asyncio.Queue] = {}
        self._lock         = asyncio.Lock()
        self._bridge_url:  Optional[str] = None

    def set_bridge_url(self, url: str) -> None:
        self._bridge_url = url

    # ── Stream subscriptions ──────────────────────────────────────────────────

    async def subscribe(
        self,
        agent_id:  str,
        stream_id: Any,
        callback:  Optional[Callable] = None,
    ) -> None:
        """Register a callback for events on stream_id.

        If callback is None, events are queued — call poll() to retrieve them.
        """
        sid = str(stream_id)
        async with self._lock:
            if sid not in self._stream_subs:
                self._stream_subs[sid] = []
            self._stream_subs[sid].append((agent_id, callback))
            if callback is None:
                key = f"{agent_id}:{sid}"
                if key not in self._queues:
                    self._queues[key] = asyncio.Queue()

    async def unsubscribe(self, agent_id: str, stream_id: Any) -> None:
        """Remove all subscriptions for agent_id on stream_id."""
        sid = str(stream_id)
        async with self._lock:
            if sid in self._stream_subs:
                self._stream_subs[sid] = [
                    (aid, cb) for aid, cb in self._stream_subs[sid]
                    if aid != agent_id
                ]
                if not self._stream_subs[sid]:
                    del self._stream_subs[sid]
            self._queues.pop(f"{agent_id}:{sid}", None)

    # ── Topic subscriptions ───────────────────────────────────────────────────

    async def subscribe_topic(
        self,
        agent_id: str,
        topic:    str,
        callback: Callable,
    ) -> None:
        """Subscribe to a topic pattern.

        Patterns:
            "memory.created"           — exact match
            "memory.*"                 — all memory.* topics
            "*"                        — everything
        """
        async with self._lock:
            if topic not in self._topic_subs:
                self._topic_subs[topic] = []
            self._topic_subs[topic].append((agent_id, callback))

    async def unsubscribe_topic(self, agent_id: str, topic: str) -> None:
        async with self._lock:
            if topic in self._topic_subs:
                self._topic_subs[topic] = [
                    (aid, cb) for aid, cb in self._topic_subs[topic]
                    if aid != agent_id
                ]

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish_event(self, event: MemoryEvent) -> None:
        """Called after every memory write.  Notifies stream subscribers and
        fires memory.created / memory.created.{stream_id} topics."""
        sid = str(event.stream_id)

        async with self._lock:
            subs = list(self._stream_subs.get(sid, []))

        for agent_id, callback in subs:
            if callback is not None:
                try:
                    result = callback(event)
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
                except Exception as exc:
                    logger.debug("stream callback error: %s", exc)
            else:
                key = f"{agent_id}:{sid}"
                queue = self._queues.get(key)
                if queue is not None:
                    await queue.put(event)

        # Fire topic events
        await self.emit("memory.created", {
            "event_id":       str(event.event_id),
            "stream_id":      sid,
            "agent_id":       event.agent_id,
            "content_preview": getattr(event, "content_blob_id", "")[:100],
        })
        await self.emit(f"memory.created.{sid}", {
            "event_id": str(event.event_id),
            "agent_id": event.agent_id,
        })

    async def publish(self, event: MemoryEvent) -> None:
        """Backward-compat alias for publish_event."""
        await self.publish_event(event)

    async def emit(self, topic: str, data: dict) -> None:
        """Fire a named topic event to all matching subscribers."""
        async with self._lock:
            matched: List[tuple] = []
            for pattern, subs in self._topic_subs.items():
                if self._matches(pattern, topic):
                    matched.extend(subs)

        for agent_id, callback in matched:
            try:
                result = callback({"topic": topic, **data})
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as exc:
                logger.debug("topic callback error: %s", exc)

        # Forward to bridge dashboard (fire-and-forget)
        if self._bridge_url:
            try:
                import httpx as _httpx
                async with _httpx.AsyncClient(timeout=2.0) as client:
                    await client.post(
                        f"{self._bridge_url}/internal/event",
                        json={"topic": topic, **data},
                    )
            except Exception:
                pass

    # ── Poll / Watch ──────────────────────────────────────────────────────────

    def poll(self, agent_id: str, stream_id: Any) -> List[MemoryEvent]:
        """Drain queued events for agent_id on stream_id (non-blocking)."""
        sid  = str(stream_id)
        key  = f"{agent_id}:{sid}"
        queue = self._queues.get(key)
        if queue is None:
            return []
        events: List[MemoryEvent] = []
        while not queue.empty():
            try:
                events.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    async def watch(
        self, agent_id: str, stream_id: Any
    ) -> AsyncIterator[MemoryEvent]:
        """Async generator: yield events as they arrive on stream_id."""
        sid = str(stream_id)
        key = f"{agent_id}:{sid}"
        if key not in self._queues:
            self._queues[key] = asyncio.Queue()
            # Register in stream_subs with no callback so publish_event routes here
            async with self._lock:
                if sid not in self._stream_subs:
                    self._stream_subs[sid] = []
                if not any(aid == agent_id for aid, _ in self._stream_subs[sid]):
                    self._stream_subs[sid].append((agent_id, None))
        queue = self._queues[key]
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                if sid in self._stream_subs:
                    self._stream_subs[sid] = [
                        (aid, cb) for aid, cb in self._stream_subs[sid]
                        if aid != agent_id
                    ]
            self._queues.pop(key, None)

    # ── Introspection ─────────────────────────────────────────────────────────

    async def subscribers(self, stream_id: Any) -> List[str]:
        """Return agent_ids subscribed to stream_id (backward compat)."""
        sid = str(stream_id)
        async with self._lock:
            return [aid for aid, _ in self._stream_subs.get(sid, [])]

    async def clear(self) -> None:
        """Remove all subscriptions (for tests)."""
        async with self._lock:
            self._stream_subs.clear()
            self._topic_subs.clear()
            self._queues.clear()

    # ── Wildcard matching ─────────────────────────────────────────────────────

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        if pattern == "*":
            return True
        if pattern == topic:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return topic.startswith(prefix + ".")
        return False


# Backward-compat alias — existing code that imports EventBus keeps working.
EventBus = EventMesh
