"""
StreamClient — Public SDK facade for a WalrusOS MemoryStream.

A stream is an ordered, append-only log of memory events.  Every write
is signed, hashed, and stored on the Walrus network.

Quick start::

    stream = runtime.workspace("myapp").agent("Alice").stream("memory")
    event  = await stream.append({"thought": "Hello WalrusOS!"})
    for event, payload in await stream.timeline():
        print(payload["thought"])
"""
from __future__ import annotations

import uuid
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

from walrusos.core.models.events import ProtocolEvent
from walrusos.types import MemoryType

if TYPE_CHECKING:
    from walrusos.sdk.agent import AgentClient

# Fields injected by the SDK that are NOT part of the developer's payload.
# These are stripped from timeline() results and accessible via event.metadata.
_INTERNAL_PAYLOAD_KEYS = frozenset({
    "author",
    "agent_id",
    "trust_root",
    "public_key",
    "workspace_id",
    "stream_id",
    "class_type",
    "memory_type",
})


def _strip_internal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the developer-written keys from a payload dict."""
    return {k: v for k, v in payload.items() if k not in _INTERNAL_PAYLOAD_KEYS}


class StreamClient:
    """
    Append-only memory stream within a workspace.

    Obtain via ``agent.stream(name)`` or ``workspace.stream(name)``::

        # Agent-owned stream (preferred for writes)
        stream = workspace.agent("Alice").stream("research")

        # Workspace stream (readable by all agents; also writeable)
        stream = workspace.stream("shared-notes")

    Core API:

    - :meth:`append`   — write a memory event
    - :meth:`timeline` — read the full ordered history
    - :meth:`search`   — semantic search across events
    - :meth:`replay`   — time-travel to any past state
    - :meth:`fork`     — branch the stream
    - :meth:`snapshot` — point-in-time snapshot

    Stream IDs are deterministic from ``<workspace>.<stream_name>`` so the
    same name always resolves to the same UUID across process restarts.
    """

    def __init__(
        self,
        memory_engine:  Any,
        workspace_name: str,
        stream_name:    str,
    ) -> None:
        self._memory        = memory_engine
        self.workspace_name = workspace_name
        self.stream_name    = stream_name
        self.stream_id      = uuid.uuid5(
            uuid.NAMESPACE_DNS, f"{workspace_name}.stream.{stream_name}"
        )
        self._initialized   = False
        self._bound_agent: Optional[AgentClient] = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _ensure_initialized(self, agent_id: Optional[uuid.UUID] = None) -> None:
        """Register the stream in the ledger on first use. Idempotent."""
        if self._initialized:
            return
        if agent_id is None and self._bound_agent is not None:
            agent_id = self._bound_agent.agent_id
        if agent_id is not None and hasattr(self._memory, "register_stream"):
            await self._memory.register_stream(self.stream_id, agent_id)  # type: ignore
        self._initialized = True

    @property
    def _is_writeable(self) -> bool:
        """True if this stream has a bound agent and can accept writes."""
        return self._bound_agent is not None

    # ── Write ─────────────────────────────────────────────────────────────────

    async def append(
        self,
        payload:     Dict[str, Any],
        *,
        memory_type: Union[MemoryType, str] = MemoryType.EPISODIC,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        summary: Optional[str] = None,
        project: Optional[str] = None,
    ) -> ProtocolEvent:
        """
        Append a new memory event to this stream.

        Parameters
        ----------
        payload:
            Any JSON-serialisable dictionary.  Only your keys are returned
            when you call :meth:`timeline` — WalrusOS metadata is stored
            separately on the event object.

        memory_type:
            Optional classification.  Use :class:`~walrusos.MemoryType`
            values or pass the string directly.  Defaults to ``"episodic"``.

            =====================  ========================
            ``MemoryType.SEMANTIC``     Facts, long-term knowledge
            ``MemoryType.EPISODIC``     Experiences, conversations  *(default)*
            ``MemoryType.PROCEDURAL``   Learned skills
            ``MemoryType.WORKING``      Short-term scratchpad
            ``MemoryType.SYSTEM``       Infrastructure events
            =====================  ========================

        Returns
        -------
        ProtocolEvent
            The signed and persisted event.  Use ``event.event_id``,
            ``event.timestamp``, ``event.blob_hash``, ``event.signature``.

        Raises
        ------
        WalrusOSError
            If the stream has no bound agent.  Create the stream via
            ``workspace.agent("name").stream("name")`` to write.

        Example
        -------
        ::

            event = await stream.append(
                {"insight": "Attention is all you need.", "year": 2017},
                memory_type=MemoryType.SEMANTIC,
            )
            print(event.event_id)   # SHA-256 content hash
        """
        if self._bound_agent is None:
            from walrusos.sdk.exceptions import WalrusOSError
            raise WalrusOSError(
                "This stream has no writing agent.\n\n"
                "Fix: create the stream from an agent instead of directly from the workspace:\n\n"
                "    # Before (read-only):\n"
                "    stream = workspace.stream('my-stream')\n\n"
                "    # After (writeable):\n"
                "    stream = workspace.agent('my-agent').stream('my-stream')\n\n"
                "Both streams share the same underlying data — only the write binding differs."
            )
        return await self._bound_agent._write_event(
            self, 
            payload, 
            memory_type=memory_type,
            tags=tags,
            importance=importance,
            summary=summary,
            project=project,
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    async def timeline(
        self,
        *,
        include_metadata: bool = False,
    ) -> List[Tuple[ProtocolEvent, Dict[str, Any]]]:
        """
        Return the full ordered history of this stream.

        Parameters
        ----------
        include_metadata:
            If ``True``, payloads include WalrusOS internal fields
            (``author``, ``agent_id``, ``trust_root``, etc.).
            Defaults to ``False`` — only your keys are returned.

        Returns
        -------
        List of ``(ProtocolEvent, payload_dict)`` tuples, oldest first.

        Example
        -------
        ::

            timeline = await stream.timeline()
            for event, payload in timeline:
                print(f"[{event.timestamp}] {payload}")
                # payload contains only what you wrote — no internal fields
        """
        await self._ensure_initialized()

        if hasattr(self._memory, "timeline"):
            raw = await self._memory.timeline(self.stream_id)  # type: ignore
        else:
            raw = []

        if include_metadata:
            return raw

        return [(ev, _strip_internal(payload)) for ev, payload in raw]

    async def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single event's payload by event ID.

        Returns ``None`` if the event is not found.

        Example
        -------
        ::

            payload = await stream.get("a3f8b2...")
            if payload is None:
                print("Event not found")
        """
        if hasattr(self._memory, "read"):
            raw = await self._memory.read(event_id)  # type: ignore
            return _strip_internal(raw) if raw else None
        return None

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        Semantic search over this stream's events.
        """
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        results = await MemorySearch(self._memory, self.stream_id).search(query, limit=limit)
        return [(_strip_internal(p), 1.0) for ev, p in results]

    async def latest(self, n: int = 10) -> List[Tuple[Any, Dict[str, Any]]]:
        """Get the n most recent events."""
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        return [(ev, _strip_internal(p)) for ev, p in await MemorySearch(self._memory, self.stream_id).latest(n)]

    async def by_agent(self, agent_id: str, limit: int = 20) -> List[Tuple[Any, Dict[str, Any]]]:
        """Filter events by the authoring agent."""
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        return [(ev, _strip_internal(p)) for ev, p in await MemorySearch(self._memory, self.stream_id).by_agent(agent_id, limit)]

    async def by_type(self, memory_type: str, limit: int = 20) -> List[Tuple[Any, Dict[str, Any]]]:
        """Filter events by memory_type."""
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        return [(ev, _strip_internal(p)) for ev, p in await MemorySearch(self._memory, self.stream_id).by_type(memory_type, limit)]

    async def by_tag(self, tag: str, limit: int = 20) -> List[Tuple[Any, Dict[str, Any]]]:
        """Filter events that contain the specified tag."""
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        return [(ev, _strip_internal(p)) for ev, p in await MemorySearch(self._memory, self.stream_id).by_tag(tag, limit)]

    async def timeline_range(self, start: Any, end: Any) -> List[Tuple[Any, Dict[str, Any]]]:
        """Get events between two timestamps."""
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        return [(ev, _strip_internal(p)) for ev, p in await MemorySearch(self._memory, self.stream_id).timeline(start, end)]

    async def related(self, event_id: str, limit: int = 5) -> List[Tuple[Any, Dict[str, Any]]]:
        """Fetch nearby/related events."""
        await self._ensure_initialized()
        from walrusos.engine.search import MemorySearch
        return [(ev, _strip_internal(p)) for ev, p in await MemorySearch(self._memory, self.stream_id).related(event_id, limit)]

    # ── Replay ────────────────────────────────────────────────────────────────

    async def replay(
        self,
        *,
        from_epoch:  int          = 1,
        up_to_epoch: Optional[int] = None,
    ) -> List[Tuple[ProtocolEvent, Dict[str, Any]]]:
        """
        Replay events, optionally bounded by epoch range.

        Use :meth:`timeline` for reading the full history.
        Use this method for time-travel to a specific window.

        Example
        -------
        ::

            # Replay the first 50 events
            past = await stream.replay(up_to_epoch=50)
        """
        await self._ensure_initialized()

        # Use timeline() and filter by epoch — gives consistent (event, payload) tuples
        # MemoryEngine.replay() returns payloads-only; we re-derive from timeline for type safety
        full = await self.timeline()
        if not full:
            return full

        # Assign synthetic epochs if the event object doesn't have one (InMemory mock)
        result = []
        for i, (ev, payload) in enumerate(full, start=1):
            # Use index as synthetic epoch when epoch is 0 (mock adapter) or missing
            epoch = getattr(ev, "epoch", None) or i
            if epoch >= from_epoch and (up_to_epoch is None or epoch <= up_to_epoch):
                result.append((ev, payload))
        return result

    # ── Branching ─────────────────────────────────────────────────────────────

    async def fork(
        self,
        from_event_id: str,
        new_agent_id:  Optional[uuid.UUID] = None,
    ) -> "StreamClient":
        """
        Create a new branch of this stream starting at ``from_event_id``.

        Parameters
        ----------
        from_event_id:
            The event ID to branch from.
        new_agent_id:
            UUID for the agent that will own the fork.  Defaults to the
            current stream's bound agent.

        Returns
        -------
        A new :class:`StreamClient` pointing at the forked stream.

        Example
        -------
        ::

            fork = await stream.fork(from_event_id=event.event_id)
            await fork.append({"experiment": "trying approach B"})
            await stream.merge(fork)
        """
        if not hasattr(self._memory, "fork"):
            raise NotImplementedError("Forking is not supported by this engine.")

        if new_agent_id is None and self._bound_agent is not None:
            new_agent_id = self._bound_agent.agent_id
        if new_agent_id is None:
            new_agent_id = uuid.uuid4()

        new_stream_id = await self._memory.fork(  # type: ignore
            self.stream_id, from_event_id, new_agent_id
        )
        client = StreamClient(self._memory, self.workspace_name, f"{self.stream_name}__fork__{new_stream_id.hex[:8]}")
        client.stream_id    = new_stream_id
        client._bound_agent = self._bound_agent
        client._initialized = True
        return client

    async def merge(self, source: Union["StreamClient", uuid.UUID]) -> ProtocolEvent:
        """
        Merge a forked branch into this stream.

        Parameters
        ----------
        source:
            Either a :class:`StreamClient` returned by :meth:`fork`,
            or the UUID of the source stream.

        Example
        -------
        ::

            fork = await stream.fork(from_event_id=event.event_id)
            # ... write to fork ...
            merge_event = await stream.merge(fork)
        """
        if not hasattr(self._memory, "merge"):
            raise NotImplementedError("Merging is not supported by this engine.")

        source_id = source.stream_id if isinstance(source, StreamClient) else source
        return await self._memory.merge(self.stream_id, source_id)  # type: ignore

    # ── Checkpoint / Snapshot ─────────────────────────────────────────────────

    async def checkpoint(self, label: str = "Manual Checkpoint") -> str:
        """
        Save a checkpoint: appends a summary event to the stream (for context
        builders) AND stores a lightweight head+epoch blob (for :meth:`resume`).

        Returns the blob_id so callers can restore epoch state via :meth:`resume`.
        """
        await self._ensure_initialized()

        # 1) Append a summary event so context builders can find it
        from walrusos.engine.summarizer import MemorySummarizer
        await MemorySummarizer().create_checkpoint(self, label)

        # 2) Store a restorable checkpoint blob and return its blob_id
        if hasattr(self._memory, "checkpoint"):
            return await self._memory.checkpoint(self.stream_id)  # type: ignore
        return ""

    async def auto_checkpoint(self, every_n_events: int = 50) -> None:
        """
        Automatically generate a summary checkpoint if enough events have passed.
        """
        await self._ensure_initialized()
        from walrusos.engine.summarizer import MemorySummarizer
        await MemorySummarizer().auto_checkpoint(self, every_n_events)

    async def resume(self, checkpoint_blob_id: str) -> None:
        """
        Restore the stream's epoch state from a checkpoint blob.

        Example
        -------
        ::

            await stream.resume("Qm...abc123")
        """
        if hasattr(self._memory, "resume"):
            await self._memory.resume(self.stream_id, checkpoint_blob_id)  # type: ignore

    async def snapshot(self) -> str:
        """
        Save a full snapshot of all events in this stream.

        A snapshot is a single Walrus blob containing all events — useful
        for cloning streams or archiving completed projects.

        Returns the Walrus blob ID of the snapshot.

        Example
        -------
        ::

            blob_id = await stream.snapshot()
        """
        if hasattr(self._memory, "snapshot"):
            return await self._memory.snapshot(self.stream_id)  # type: ignore
        return ""

    # ── Summarise ─────────────────────────────────────────────────────────────

    async def summarize(self, max_events: int = 20) -> str:
        """
        Return a human-readable summary of the most recent stream events.

        Useful for feeding a compact stream digest into an LLM prompt.

        Example
        -------
        ::

            summary = await stream.summarize(max_events=10)
            prompt  = f"Recent agent activity:\\n{summary}\\n\\nNew task: ..."
        """
        if hasattr(self._memory, "summarize"):
            return await self._memory.summarize(self.stream_id, max_events=max_events)  # type: ignore
        return ""

    # ── Dunder ────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        mode = "writeable" if self._is_writeable else "read-only"
        return (
            f"<StreamClient {self.workspace_name!r}/{self.stream_name!r}"
            f" id={self.stream_id} [{mode}]>"
        )
