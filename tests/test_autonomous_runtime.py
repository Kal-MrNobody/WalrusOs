"""
Tests for the Autonomous Runtime.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_autonomous_runtime.py -v
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

from walrusos.client import WalrusOS
from walrusos.core.models.run_result import RunResult


# ── Shared fixture ─────────────────────────────────────────────────────────────

@pytest.fixture
def runtime():
    return WalrusOS(use_mocks=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ws(runtime, name: str = "test-auto"):
    return runtime.workspace(name)


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_completes_within_max_rounds(runtime):
    """3 agents × max_rounds=2 → at most 6 events, rounds_completed ≤ 2."""
    ws     = _ws(runtime, "test-max-rounds")
    agents = [ws.agent("AlphaAgent"), ws.agent("BetaAgent"), ws.agent("GammaAgent")]

    result = await ws.run(
        goal="Explore the concept of decentralized memory",
        agents=agents,
        max_rounds=2,
    )

    assert isinstance(result, RunResult)
    assert result.rounds_completed <= 2
    assert len(result.events) == len(agents) * result.rounds_completed


@pytest.mark.asyncio
async def test_run_stops_on_done_signal(runtime):
    """Callback returns 'DONE' on the second call → completed=True, rounds_completed=1."""
    ws    = _ws(runtime, "test-done-signal")
    a1    = ws.agent("PlannerAgent")
    a2    = ws.agent("ExecutorAgent")

    call_count = [0]

    def on_event(agent, prompt, context):
        call_count[0] += 1
        if call_count[0] == 2:
            return "The goal is now fully addressed. DONE"
        return f"[{agent.agent_name}] Progressing toward the goal."

    result = await ws.run(
        goal="Build a simple key-value store",
        agents=[a1, a2],
        max_rounds=5,
        on_event=on_event,
    )

    assert result.completed is True
    assert result.rounds_completed == 1
    # Only the first two calls happened (a1 and a2 of round 1, stopped on a2)
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_run_with_callback(runtime):
    """Callback is called with (agent, prompt_str, context_str); all must be strings."""
    ws     = _ws(runtime, "test-callback-types")
    agents = [ws.agent("TypeCheckAgent")]
    calls  = []

    def on_event(agent, prompt, context):
        calls.append((agent, prompt, context))
        return "Contribution complete."

    await ws.run(
        goal="Verify callback signature",
        agents=agents,
        max_rounds=1,
        on_event=on_event,
    )

    assert len(calls) >= 1
    for agent, prompt, context in calls:
        # All three positional args must be the right types
        assert hasattr(agent, "agent_name"), "first arg should be an AgentClient"
        assert isinstance(prompt,  str), f"prompt should be str, got {type(prompt)}"
        assert isinstance(context, str), f"context should be str, got {type(context)}"


@pytest.mark.asyncio
async def test_run_saves_events_to_stream(runtime):
    """Events written during the run appear in stream.latest() with memory_type='observation'."""
    ws     = _ws(runtime, "test-saves-events")
    agent  = ws.agent("WriteAgent")
    stream = agent.stream("auto-run-stream")

    await ws.run(
        goal="Write a memory event and verify it persists",
        agents=[agent],
        stream=stream,
        max_rounds=2,
    )

    results = await stream.latest(20)
    # Filter to observation events (checkpoint writes a 'summary' event too)
    obs = [(ev, p) for ev, p in results if getattr(ev, "memory_type", None) == "observation"]

    assert len(obs) >= 1, "Expected at least one observation event in the stream"
    for ev, _ in obs:
        assert ev.memory_type == "observation"


@pytest.mark.asyncio
async def test_run_result_structure(runtime):
    """All RunResult fields are present and have sane values."""
    ws     = _ws(runtime, "test-result-struct")
    agents = [ws.agent("StructAgent1"), ws.agent("StructAgent2")]

    result = await ws.run(
        goal="Validate RunResult structure",
        agents=agents,
        max_rounds=1,
    )

    assert isinstance(result, RunResult)
    assert isinstance(result.goal,             str)   and result.goal
    assert isinstance(result.rounds_completed, int)   and result.rounds_completed >= 1
    assert isinstance(result.events,           list)
    assert isinstance(result.agents_involved,  list)
    assert isinstance(result.final_summary,    str)   and result.final_summary
    assert isinstance(result.completed,        bool)
    assert isinstance(result.duration_seconds, float) and result.duration_seconds > 0
    assert isinstance(result.blob_ids,         list)
    assert isinstance(result.sui_anchors,      list)

    # agents_involved must contain all agent IDs
    for agent in agents:
        assert agent._agent_id_str in result.agents_involved


@pytest.mark.asyncio
async def test_run_single_agent(runtime):
    """Single agent, max_rounds=3 — runs cleanly, rounds_completed ≤ 3."""
    ws    = _ws(runtime, "test-single-agent")
    agent = ws.agent("SoloAgent")

    result = await ws.run(
        goal="Think through a problem alone",
        agents=[agent],
        max_rounds=3,
    )

    assert isinstance(result, RunResult)
    assert result.rounds_completed <= 3
    assert len(result.agents_involved) == 1
    assert agent._agent_id_str in result.agents_involved
    assert len(result.events) == result.rounds_completed


@pytest.mark.asyncio
async def test_stub_mode_no_callback(runtime):
    """Stub mode (no on_event): produces events without raising."""
    ws     = _ws(runtime, "test-stub-mode")
    agents = [ws.agent("StubA"), ws.agent("StubB")]

    result = await ws.run(
        goal="Test stub mode produces events",
        agents=agents,
        max_rounds=2,
        # on_event intentionally omitted
    )

    assert isinstance(result, RunResult)
    assert len(result.events) > 0
    assert result.duration_seconds > 0
    # Stub responses should NOT accidentally trigger completion
    assert result.rounds_completed == 2
