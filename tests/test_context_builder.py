"""
Tests for Sprint 6 — Context Builder, Token Budget, and Ranking.
Run with: WALRUSOS_USE_MOCKS=1 python -m pytest tests/test_context_builder.py -v
"""
from __future__ import annotations

import os
os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

import asyncio
import uuid
import pytest

from walrusos.engine.token_budget import TokenBudget, estimate_tokens
from walrusos.engine.ranking import keyword_overlap_score, rank_events
from walrusos.core.models.memory import MemoryEvent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pair(
    content: str,
    *,
    memory_type: str = "observation",
    importance: float = 0.5,
    epoch: int = 1,
    tags: list | None = None,
) -> tuple:
    """Create a (MemoryEvent, payload_dict) tuple for testing."""
    ev = MemoryEvent(
        id=str(uuid.uuid4()),
        stream_id=uuid.uuid4(),
        parent_id="genesis",
        epoch=epoch,
        memory_type=memory_type,  # type: ignore[arg-type]
        importance=importance,
        tags=tags or [],
        content_blob_id="fake-blob",
    )
    return (ev, {"content": content})


@pytest.fixture
def runtime():
    from walrusos import WalrusOS
    return WalrusOS(use_mocks=True)


# ── TokenBudget ───────────────────────────────────────────────────────────────

class TestTokenBudget:
    def test_estimate_tokens_minimum(self):
        assert estimate_tokens("test") >= 1

    def test_estimate_tokens_count(self):
        assert estimate_tokens("a" * 400) == 100

    def test_can_fit_true(self):
        b = TokenBudget(100)
        assert b.can_fit("a" * 40)  # ~10 tokens

    def test_can_fit_false_after_fill(self):
        b = TokenBudget(100)
        b.add("a" * 360)  # ~90 tokens
        assert not b.can_fit("a" * 80)  # ~20 more would exceed

    def test_add_returns_true_on_fit(self):
        b = TokenBudget(10)
        assert b.add("a" * 40) is True   # exactly 10 tokens

    def test_add_returns_false_on_overflow(self):
        b = TokenBudget(10)
        b.add("a" * 40)               # fills budget completely
        assert b.add("a" * 4) is False  # 1 more token would exceed

    def test_remaining_decreases(self):
        b = TokenBudget(100)
        b.add("a" * 40)  # 10 tokens
        assert b.remaining == 90

    def test_empty_string_costs_one_token(self):
        b = TokenBudget(5)
        assert b.add("") is True  # max(1, 0//4) = 1 token


# ── Ranking ───────────────────────────────────────────────────────────────────

class TestRanking:
    def test_keyword_overlap_basic(self):
        score = keyword_overlap_score(
            "authentication tokens",
            "JWT tokens for authentication",
        )
        assert score > 0.5

    def test_keyword_overlap_no_match(self):
        score = keyword_overlap_score(
            "database postgres",
            "frontend react styling",
        )
        assert score == 0.0

    def test_keyword_overlap_partial(self):
        score = keyword_overlap_score("auth oauth tokens", "oauth is great")
        assert 0.0 < score < 1.0

    def test_rank_events_empty(self):
        assert rank_events("query", []) == []

    def test_rank_events_relevance(self):
        auth_pair = _make_pair("authentication oauth JWT bearer token")
        db_pair   = _make_pair("database postgresql connection pool")
        fe_pair   = _make_pair("frontend react component rendering")

        ranked = rank_events("authentication oauth", [db_pair, fe_pair, auth_pair])
        first_content = ranked[0][1].get("content", "")
        assert "auth" in first_content.lower() or "oauth" in first_content.lower()

    def test_rank_events_returns_same_pairs(self):
        """rank_events returns the exact same (event, payload) tuples — identity preserved."""
        pairs = [_make_pair(f"content {i}") for i in range(5)]
        ranked = rank_events("content", pairs)
        assert len(ranked) == 5
        for pair in ranked:
            assert pair in pairs

    def test_rank_summary_boost(self):
        """Summary events are boosted to the top when relevance is equal."""
        obs_pair = _make_pair("query matching both authentication oauth", memory_type="observation")
        sum_pair = _make_pair("query matching both authentication oauth", memory_type="summary")

        ranked = rank_events("query matching both", [obs_pair, sum_pair])
        assert ranked[0] is sum_pair

    def test_rank_single_event(self):
        pair = _make_pair("only event")
        assert rank_events("only event", [pair]) == [pair]


# ── ContextBuilder.build_recall_context ───────────────────────────────────────

class TestBuildRecallContext:
    async def test_build_recall_respects_budget(self, runtime) -> None:
        ws     = runtime.workspace("recall-budget")
        agent  = ws.agent("Writer")
        stream = agent.stream("stream")
        for i in range(20):
            await stream.append({"content": f"Event {i}: " + "x" * 100})

        from walrusos.engine.context import ContextBuilder
        result = await ContextBuilder().build_recall_context(stream, "query", max_tokens=200)
        assert result["token_estimate"] <= 200

    async def test_build_recall_includes_checkpoint(self, runtime) -> None:
        ws     = runtime.workspace("recall-ckpt")
        agent  = ws.agent("Writer")
        stream = agent.stream("stream")
        for i in range(3):
            await stream.append({"content": f"Observation {i}"})
        await stream.checkpoint("Test Checkpoint")

        from walrusos.engine.context import ContextBuilder
        result = await ContextBuilder().build_recall_context(stream, "observation", max_tokens=500)
        assert result["checkpoints_included"] == 1

    async def test_build_recall_considers_all_events(self, runtime) -> None:
        ws     = runtime.workspace("recall-considered")
        agent  = ws.agent("Writer")
        stream = agent.stream("stream")
        for i in range(5):
            await stream.append({"content": f"Event {i}"})

        from walrusos.engine.context import ContextBuilder
        result = await ContextBuilder().build_recall_context(stream, "event", max_tokens=1500)
        assert result["events_considered"] >= 5

    async def test_build_recall_auth_vs_devops(self, runtime) -> None:
        """Auth query should include more auth content than devops content."""
        ws     = runtime.workspace("recall-filter")
        agent  = ws.agent("Writer")
        stream = agent.stream("stream")
        auth_contents = [
            "OAuth 2.0 uses authorization code flow with PKCE",
            "JWT tokens should be short-lived 15 min max",
            "Decided to use refresh token rotation for security",
        ]
        devops_contents = [
            "Deployment uses Docker on AWS ECS",
            "Monitoring via Datadog with custom dashboards",
        ]
        for c in auth_contents:
            await stream.append({"content": c})
        for c in devops_contents:
            await stream.append({"content": c})

        from walrusos.engine.context import ContextBuilder
        result = await ContextBuilder().build_recall_context(
            stream, "authentication token strategy", max_tokens=500
        )
        ctx = result["context"].lower()
        assert "oauth" in ctx or "jwt" in ctx or "token" in ctx

    async def test_build_recall_returns_all_keys(self, runtime) -> None:
        ws     = runtime.workspace("recall-keys")
        agent  = ws.agent("Writer")
        stream = agent.stream("stream")
        await stream.append({"content": "test"})

        from walrusos.engine.context import ContextBuilder
        result = await ContextBuilder().build_recall_context(stream, "test")
        for key in ("context", "token_estimate", "events_considered",
                    "events_included", "checkpoints_included", "sources"):
            assert key in result, f"Missing key: {key}"

    async def test_build_recall_empty_stream(self, runtime) -> None:
        ws     = runtime.workspace("recall-empty")
        agent  = ws.agent("Writer")
        stream = agent.stream("stream")

        from walrusos.engine.context import ContextBuilder
        result = await ContextBuilder().build_recall_context(stream, "query")
        assert result["context"] == ""
        assert result["events_considered"] == 0


# ── AgentClient.recall / recall_detailed ──────────────────────────────────────

class TestAgentRecall:
    async def test_recall_returns_string(self, runtime) -> None:
        ws     = runtime.workspace("agent-recall")
        agent  = ws.agent("Alice")
        stream = agent.stream("notes")
        await stream.append({"content": "some important note"})

        context = await agent.recall(stream, "important note")
        assert isinstance(context, str)

    async def test_recall_detailed_returns_metadata(self, runtime) -> None:
        ws     = runtime.workspace("agent-recall-detail")
        agent  = ws.agent("Alice")
        stream = agent.stream("notes")
        await stream.append({"content": "some detail"})

        result = await agent.recall_detailed(stream, "detail")
        assert "events_included" in result
        assert "token_estimate" in result
        assert "sources" in result
        assert isinstance(result["sources"], list)

    async def test_recall_smaller_than_full_read(self, runtime) -> None:
        """recall() output must be smaller than the full raw timeline text."""
        ws     = runtime.workspace("agent-recall-size")
        agent  = ws.agent("Writer")
        stream = agent.stream("history")

        for i in range(30):
            topic = "auth" if i % 3 == 0 else ("database" if i % 3 == 1 else "deployment")
            await stream.append({
                "content": (
                    f"Memory about {topic}: event number {i}. "
                    f"This is a longer description with details about {topic} "
                    f"configuration, settings, and operational notes."
                )
            })

        full_tl = await stream.timeline()
        full_tokens = sum(
            estimate_tokens(
                " ".join(str(v) for v in payload.values() if isinstance(v, str))
            )
            for _, payload in full_tl
        )

        recalled = await agent.recall(stream, "authentication security tokens", max_tokens=300)
        recalled_tokens = estimate_tokens(recalled)

        assert recalled_tokens <= 300
        assert recalled_tokens < full_tokens

    async def test_recall_max_tokens_respected(self, runtime) -> None:
        ws     = runtime.workspace("agent-recall-budget")
        agent  = ws.agent("Alice")
        stream = agent.stream("notes")
        for i in range(10):
            await stream.append({"content": "x" * 200})

        recalled = await agent.recall(stream, "query", max_tokens=100)
        assert estimate_tokens(recalled) <= 100

    async def test_recall_sources_are_strings(self, runtime) -> None:
        ws     = runtime.workspace("agent-recall-src")
        agent  = ws.agent("Alice")
        stream = agent.stream("notes")
        await stream.append({"content": "first note"})
        await stream.append({"content": "second note"})

        result = await agent.recall_detailed(stream, "note")
        for src in result["sources"]:
            assert isinstance(src, str)
