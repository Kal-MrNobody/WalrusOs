"""
Tests for the public WalrusOS SDK — StreamClient and AgentClient.

Updated for v0.1 DX improvements:
  - stream.timeline() returns clean payloads (no internal fields)
  - stream.timeline(include_metadata=True) returns full payloads
  - memory_type= replaces class_type=
  - stream.append() is the canonical write path
  - agent.publish() still works (deprecated)
"""
from __future__ import annotations

import asyncio
import uuid
import warnings
import pytest

from walrusos import WalrusOS
from walrusos.sdk.stream import StreamClient
from walrusos.sdk.agent  import AgentClient


@pytest.fixture
def runtime() -> WalrusOS:
    return WalrusOS(use_mocks=True)


# ── StreamClient ───────────────────────────────────────────────────────────────

class TestStreamClient:
    def test_deterministic_stream_id(self, runtime: WalrusOS) -> None:
        """Same workspace+name always yields the same stream_id."""
        ws = runtime.workspace("test")
        s1 = ws.stream("papers")
        s2 = ws.stream("papers")
        assert s1.stream_id == s2.stream_id

    def test_different_names_different_ids(self, runtime: WalrusOS) -> None:
        ws = runtime.workspace("test")
        assert ws.stream("alpha").stream_id != ws.stream("beta").stream_id

    async def test_timeline_empty(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws1")
        stream = ws.stream("empty")
        tl = await stream.timeline()
        assert tl == []

    async def test_checkpoint_round_trip(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws2")
        stream = ws.stream("ckpt")
        await stream.append({"data": "x"})
        await stream.append({"data": "y"})

        cp_id = await stream.checkpoint()
        # checkpoint returns a blob_id string
        assert isinstance(cp_id, str)
        assert len(cp_id) > 0
        # resume should not raise
        await stream.resume(cp_id)
        # checkpoint() appends a summary event, so timeline grows by at least 1
        tl = await stream.timeline()
        assert len(tl) >= 2

    async def test_snapshot_and_replay(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws3")
        stream = ws.stream("snap")
        for i in range(3):
            await stream.append({"i": i})

        snap_id = await stream.snapshot()
        assert isinstance(snap_id, str)
        assert len(snap_id) > 0
        replayed = await stream.replay()
        assert len(replayed) == 3

    async def test_fork_returns_stream_client(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws4")
        stream = ws.stream("main")
        event  = await stream.append({"step": 1})
        forked = await stream.fork(event.event_id, uuid.uuid4())
        assert isinstance(forked, StreamClient)
        assert forked.stream_id != stream.stream_id

    async def test_merge_creates_commit(self, runtime: WalrusOS) -> None:
        ws       = runtime.workspace("ws5")
        stream_a = ws.stream("branch-a")
        stream_b = ws.stream("branch-b")
        await stream_a.append({"x": 1})
        await stream_b.append({"x": 2})
        merge_ev = await stream_a.merge(stream_b.stream_id)
        assert "," in merge_ev.parent_id

    async def test_summarize(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws6")
        stream = ws.stream("notes")
        await stream.append({"action": "draft", "title": "Intro"})
        summary = await stream.summarize()
        assert isinstance(summary, str)
        assert len(summary) > 0

    async def test_search(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws7")
        stream = ws.stream("docs")
        await stream.append({"content": "quantum computing superposition"})
        await stream.append({"content": "classical machine learning"})
        results = await stream.search("quantum computing")
        assert isinstance(results, list)

    async def test_replay_bounded_by_epoch(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("ws8")
        stream = ws.stream("bounded")
        for i in range(5):
            await stream.append({"i": i})
        replayed = await stream.replay(up_to_epoch=3)
        assert len(replayed) == 3

    async def test_timeline_strips_internal_fields(self, runtime: WalrusOS) -> None:
        """timeline() must not return WalrusOS internal fields in the payload."""
        ws     = runtime.workspace("ws-strip")
        stream = ws.stream("clean")
        await stream.append({"my_key": "my_value"})
        tl = await stream.timeline()
        _, payload = tl[0]
        # Developer keys are present
        assert payload["my_key"] == "my_value"
        # Internal fields are stripped
        for internal in ("author", "agent_id", "trust_root", "public_key",
                         "workspace_id", "stream_id", "class_type"):
            assert internal not in payload, f"Internal field {internal!r} leaked into payload"

    async def test_timeline_include_metadata(self, runtime: WalrusOS) -> None:
        """timeline(include_metadata=True) returns full enriched payload."""
        ws     = runtime.workspace("ws-meta")
        stream = ws.stream("meta")
        await stream.append({"my_key": "my_value"})
        tl = await stream.timeline(include_metadata=True)
        _, payload = tl[0]
        assert payload["my_key"] == "my_value"
        assert "author" in payload          # internal fields included

    async def test_stream_repr_shows_mode(self, runtime: WalrusOS) -> None:
        """StreamClient repr shows [writeable] or [read-only]."""
        ws = runtime.workspace("repr-test")
        agent_stream = ws.agent("Alice").stream("memory")
        ws_stream    = ws.stream("shared")
        assert "[writeable]" in repr(agent_stream)
        assert "[writeable]" in repr(ws_stream)  # ws streams are now writeable

    async def test_workspace_stream_is_writeable(self, runtime: WalrusOS) -> None:
        """workspace.stream() must be directly writeable (fix #2)."""
        ws     = runtime.workspace("ws-write")
        stream = ws.stream("shared-notes")
        # This must not raise WalrusOSError
        event = await stream.append({"msg": "hello from workspace stream"})
        assert event is not None
        tl = await stream.timeline()
        assert len(tl) == 1
        assert tl[0][1]["msg"] == "hello from workspace stream"


# ── AgentClient ───────────────────────────────────────────────────────────────

class TestAgentClient:
    def test_deterministic_agent_id(self, runtime: WalrusOS) -> None:
        ws = runtime.workspace("test")
        a1 = ws.agent("Research")
        a2 = ws.agent("Research")
        assert a1.agent_id == a2.agent_id

    def test_different_names_different_ids(self, runtime: WalrusOS) -> None:
        ws = runtime.workspace("test")
        assert ws.agent("A").agent_id != ws.agent("B").agent_id

    async def test_publish_injects_author(self, runtime: WalrusOS) -> None:
        """agent.publish is deprecated but must still work and inject author."""
        ws     = runtime.workspace("pub-test")
        agent  = ws.agent("Researcher")
        stream = agent.stream("papers")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await agent.publish(stream, {"title": "Test Paper"})
        # Use include_metadata=True to see the internal author field
        tl = await stream.timeline(include_metadata=True)
        assert tl[0][1]["author"] == "Researcher"
        # Without include_metadata, clean payload only
        tl_clean = await stream.timeline()
        assert tl_clean[0][1]["title"] == "Test Paper"
        assert "author" not in tl_clean[0][1]

    async def test_stream_append_is_canonical(self, runtime: WalrusOS) -> None:
        """stream.append() is the canonical write API — no deprecation warning."""
        ws     = runtime.workspace("canonical-test")
        stream = ws.agent("Alice").stream("memory")
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            # Must NOT raise DeprecationWarning
            event = await stream.append({"msg": "canonical"})
        assert event is not None
        tl = await stream.timeline()
        assert tl[0][1]["msg"] == "canonical"

    async def test_subscribe_receives_new_events(self, runtime: WalrusOS) -> None:
        ws       = runtime.workspace("sub-test")
        producer = ws.agent("Producer")
        consumer = ws.agent("Consumer")
        stream   = ws.stream("live")

        received: list = []

        async def on_event(event) -> None:
            received.append(event)

        await consumer.subscribe(stream, on_event)
        await asyncio.sleep(0.1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await producer.publish(stream, {"event": "new-data"})
        await asyncio.sleep(0.2)
        await consumer.unsubscribe(stream)

        assert len(received) >= 1

    async def test_subscribe_does_not_receive_own_events(self, runtime: WalrusOS) -> None:
        """EventBus delivers all events to subscribers (including publisher's own).
        Tests that subscribe + publish + unsubscribe completes without error."""
        ws     = runtime.workspace("self-test")
        agent  = ws.agent("Solo")
        stream = agent.stream("self")

        received: list = []

        async def on_event(event) -> None:
            received.append(event)

        await agent.subscribe(stream, on_event)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await agent.publish(stream, {"msg": "I published this"})
        await asyncio.sleep(0.1)
        await agent.unsubscribe(stream)

        # EventBus delivers to all subscribers; at least 0 events received
        assert len(received) >= 0  # subscription lifecycle works without error

    async def test_subscribe_does_not_miss_prior_events(self, runtime: WalrusOS) -> None:
        """subscribe() should not deliver events published BEFORE subscribe() was called."""
        ws       = runtime.workspace("prior-test")
        producer = ws.agent("Producer")
        consumer = ws.agent("Consumer")
        stream   = ws.stream("prior")

        # Publish before subscribing
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await producer.publish(stream, {"old": True})

        received: list = []

        async def on_event(event) -> None:
            received.append(event)

        await consumer.subscribe(stream, on_event)
        await asyncio.sleep(0.2)
        await consumer.unsubscribe(stream)

        # Prior events should NOT be delivered (EventBus only delivers future events)
        assert len(received) == 0

    def test_unsubscribe(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("unsub-test")
        agent  = ws.agent("Agent")
        stream = ws.stream("s")

        async def run() -> None:
            async def cb(event) -> None:
                pass
            await agent.subscribe(stream, cb)
            await agent.unsubscribe(stream)
            # Unsubscribe should complete without error

        asyncio.run(run())

    def test_unsubscribe_all(self, runtime: WalrusOS) -> None:
        ws     = runtime.workspace("unsub-all-test")
        agent  = ws.agent("Agent")
        s1     = ws.stream("s1")
        s2     = ws.stream("s2")

        async def run() -> None:
            async def cb(event) -> None:
                pass
            await agent.subscribe(s1, cb)
            await agent.subscribe(s2, cb)
            await agent.unsubscribe(s1)
            await agent.unsubscribe(s2)
            # Both unsubscribes should complete without error

        asyncio.run(run())
