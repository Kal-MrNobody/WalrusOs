"""
Tests for the Sprint 5 Coordination Engine.

All tests use WALRUSOS_USE_MOCKS=1 — no network calls.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from walrusos.core.models.coordination import (
    CoordinationPlan,
    CoordinationTask,
    CoordinationResult,
)
from walrusos.runtime.coordinator import Coordinator
from walrusos.runtime.registry import AgentRegistry, AgentRegistration, AgentCapability


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_registry(*agents: tuple) -> AgentRegistry:
    """Create a registry with given (agent_id, agent_name, capabilities) tuples."""
    reg = AgentRegistry()

    async def _fill() -> None:
        for agent_id, agent_name, caps in agents:
            await reg.register(AgentRegistration(
                agent_id=agent_id,
                agent_name=agent_name,
                framework="custom",
                workspace_id="test-ws",
                capabilities=[AgentCapability(name=c) for c in caps],
            ))

    asyncio.run(_fill())
    return reg


def _make_coordinator(llm=None, registry=None) -> Coordinator:
    ws        = MagicMock()
    registry  = registry or AgentRegistry()
    mesh      = MagicMock()
    mesh.emit = AsyncMock()
    return Coordinator(ws, registry, mesh, llm=llm)


def _stub_agent(agent_id: str, name: str) -> MagicMock:
    agent              = MagicMock()
    agent._agent_id_str = agent_id
    agent.agent_name    = name
    agent.set_status    = AsyncMock()
    proto              = MagicMock()
    proto.event_id     = f"evt-{agent_id}"
    proto.blob_id      = f"blob-{agent_id}"
    proto.transaction_digest = None
    agent._write_event  = AsyncMock(return_value=proto)
    return agent


# ── Part A: model smoke test ──────────────────────────────────────────────────

def test_coordination_models_instantiate():
    plan = CoordinationPlan(goal="test goal")
    assert plan.goal_id
    assert plan.status == "planning"

    task = CoordinationTask(
        goal_id=plan.goal_id,
        title="do work",
        description="detailed work",
        required_capability="research",
    )
    assert task.task_id
    assert task.status == "pending"
    assert task.depends_on == []


# ── Part B: DECOMPOSE ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_with_stub_fallback():
    """No LLM → single task with the first available capability."""
    coord = _make_coordinator(llm=None)
    plan  = await coord.decompose("build oauth", ["code_generation"])
    assert len(plan.tasks) >= 1
    assert plan.tasks[0].required_capability == "code_generation"


@pytest.mark.asyncio
async def test_decompose_with_llm():
    """LLM returns valid JSON → tasks are created correctly."""
    llm_json = (
        '[{"title":"Research","description":"research it","required_capability":"research","depends_on":[]},'
        '{"title":"Code","description":"write it","required_capability":"code_generation","depends_on":[]},'
        '{"title":"Review","description":"review it","required_capability":"review","depends_on":[1]}]'
    )
    llm       = MagicMock()
    llm.generate = AsyncMock(return_value=llm_json)
    coord     = _make_coordinator(llm=llm)
    plan      = await coord.decompose("build oauth", ["research", "code_generation", "review"])
    assert len(plan.tasks) == 3
    assert all(t.required_capability in ["research", "code_generation", "review"] for t in plan.tasks)


@pytest.mark.asyncio
async def test_decompose_resolves_dependencies():
    """depends_on indices are converted to task_ids."""
    llm_json = (
        '[{"title":"T0","description":"first","required_capability":"research","depends_on":[]},'
        '{"title":"T1","description":"second","required_capability":"code_generation","depends_on":[]},'
        '{"title":"T2","description":"third","required_capability":"review","depends_on":[0,1]}]'
    )
    llm       = MagicMock()
    llm.generate = AsyncMock(return_value=llm_json)
    coord = _make_coordinator(llm=llm)
    plan  = await coord.decompose("goal", ["research", "code_generation", "review"])
    assert len(plan.tasks[2].depends_on) == 2
    assert plan.tasks[0].task_id in plan.tasks[2].depends_on
    assert plan.tasks[1].task_id in plan.tasks[2].depends_on


@pytest.mark.asyncio
async def test_decompose_handles_bad_json():
    """Bad JSON from LLM → fallback to single task."""
    llm       = MagicMock()
    llm.generate = AsyncMock(return_value="not valid json at all!!")
    coord = _make_coordinator(llm=llm)
    plan  = await coord.decompose("goal", ["general"])
    assert len(plan.tasks) == 1


@pytest.mark.asyncio
async def test_decompose_handles_markdown_fences():
    """LLM wraps JSON in markdown fences — should still parse."""
    llm_json = '```json\n[{"title":"T","description":"d","required_capability":"general","depends_on":[]}]\n```'
    llm      = MagicMock()
    llm.generate = AsyncMock(return_value=llm_json)
    coord = _make_coordinator(llm=llm)
    plan  = await coord.decompose("goal", ["general"])
    assert len(plan.tasks) == 1
    assert plan.tasks[0].title == "T"


# ── Part B: MATCH ─────────────────────────────────────────────────────────────

def test_match_agent_by_capability():
    """Agent with the required capability is preferred."""
    registry = _make_registry(
        ("gemini-id",  "Gemini",  ["research", "reasoning"]),
        ("claude-id",  "Claude",  ["code_generation", "review"]),
    )
    coord    = _make_coordinator(registry=registry)
    task     = CoordinationTask(
        goal_id="g", title="t", description="d", required_capability="research"
    )
    online   = [
        {"agent_id": "gemini-id", "agent_name": "Gemini"},
        {"agent_id": "claude-id", "agent_name": "Claude"},
    ]
    match = coord.match_agent(task, online)
    assert match is not None
    assert match[1] == "Gemini"


def test_match_agent_code_generation():
    """Capability match routes code task to the code agent."""
    registry = _make_registry(
        ("gemini-id", "Gemini", ["research"]),
        ("claude-id", "Claude", ["code_generation"]),
    )
    coord  = _make_coordinator(registry=registry)
    task   = CoordinationTask(
        goal_id="g", title="t", description="d", required_capability="code_generation"
    )
    online = [
        {"agent_id": "gemini-id", "agent_name": "Gemini"},
        {"agent_id": "claude-id", "agent_name": "Claude"},
    ]
    match = coord.match_agent(task, online)
    assert match is not None
    assert match[1] == "Claude"


def test_match_agent_fallback_when_no_capability():
    """No capability match → returns any online agent."""
    registry = _make_registry(
        ("agent-id", "Agent", ["planning"]),
    )
    coord  = _make_coordinator(registry=registry)
    task   = CoordinationTask(
        goal_id="g", title="t", description="d", required_capability="nonexistent"
    )
    online = [{"agent_id": "agent-id", "agent_name": "Agent"}]
    match  = coord.match_agent(task, online)
    assert match is not None


def test_match_agent_none_when_no_online():
    """Empty online list → None."""
    coord = _make_coordinator()
    task  = CoordinationTask(
        goal_id="g", title="t", description="d", required_capability="research"
    )
    assert coord.match_agent(task, []) is None


# ── Part B: EXECUTE ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_parallel_independent_tasks():
    """Three tasks with no dependencies → all reach 'done'."""
    coord  = _make_coordinator()
    agents = {
        "a1": _stub_agent("a1", "Alice"),
        "a2": _stub_agent("a2", "Bob"),
        "a3": _stub_agent("a3", "Carol"),
    }
    plan = CoordinationPlan(goal="test")
    plan.tasks = [
        CoordinationTask(goal_id=plan.goal_id, title=f"Task {i}",
                         description="", required_capability="general",
                         assigned_to=list(agents.keys())[i], status="pending")
        for i in range(3)
    ]
    stream = MagicMock()
    stream._ensure_initialized = AsyncMock()
    stream.stream_id = "stream-uuid"

    await coord.execute(plan, agents, stream)
    assert all(t.status == "done" for t in plan.tasks)


@pytest.mark.asyncio
async def test_execute_respects_dependencies():
    """Task B with depends_on=[task_A.task_id] must finish after task A."""
    coord   = _make_coordinator()
    agent_a = _stub_agent("a1", "Alice")
    agent_b = _stub_agent("a2", "Bob")
    agents  = {"a1": agent_a, "a2": agent_b}

    plan   = CoordinationPlan(goal="test")
    task_a = CoordinationTask(goal_id=plan.goal_id, title="A",
                               description="", required_capability="general",
                               assigned_to="a1", status="pending")
    task_b = CoordinationTask(goal_id=plan.goal_id, title="B",
                               description="", required_capability="general",
                               assigned_to="a2", status="pending",
                               depends_on=[task_a.task_id])
    plan.tasks = [task_a, task_b]

    stream = MagicMock()
    stream._ensure_initialized = AsyncMock()
    stream.stream_id = "stream-uuid"

    await coord.execute(plan, agents, stream)

    assert task_a.status == "done"
    assert task_b.status == "done"
    assert task_a.completed_at <= task_b.completed_at


@pytest.mark.asyncio
async def test_execute_blocks_on_failed_dependency():
    """Task B is blocked when its dependency task A has no assigned agent."""
    coord  = _make_coordinator()
    agents = {}  # no agents → task_a fails

    plan   = CoordinationPlan(goal="test")
    task_a = CoordinationTask(goal_id=plan.goal_id, title="A",
                               description="", required_capability="general",
                               assigned_to="missing-id", status="pending")
    task_b = CoordinationTask(goal_id=plan.goal_id, title="B",
                               description="", required_capability="general",
                               assigned_to="also-missing", status="pending",
                               depends_on=[task_a.task_id])
    plan.tasks = [task_a, task_b]

    stream = MagicMock()
    stream._ensure_initialized = AsyncMock()
    stream.stream_id = "stream-uuid"

    await coord.execute(plan, agents, stream)
    assert task_b.status == "blocked"


# ── Part C: workspace.coordinate() end-to-end ────────────────────────────────

@pytest.mark.asyncio
async def test_coordinate_end_to_end_stub():
    """workspace.coordinate() with stub LLM produces a valid CoordinationResult."""
    import os
    os.environ["WALRUSOS_USE_MOCKS"] = "1"

    from walrusos import WalrusOS
    from walrusos.runtime.registry import get_registry, AgentRegistration, AgentCapability

    rt = WalrusOS(use_mocks=True)
    ws = rt.workspace("coord-test")

    # Register two agents in the registry so coordinate() can find them
    registry = get_registry()
    a1 = ws.agent("Researcher")
    a2 = ws.agent("Writer")
    await registry.register(AgentRegistration(
        agent_id=a1._agent_id_str,
        agent_name="Researcher",
        framework="custom",
        workspace_id=ws.workspace_id,
        capabilities=[AgentCapability(name="research")],
    ))
    await registry.register(AgentRegistration(
        agent_id=a2._agent_id_str,
        agent_name="Writer",
        framework="custom",
        workspace_id=ws.workspace_id,
        capabilities=[AgentCapability(name="writing")],
    ))

    result = await ws.coordinate(goal="Explain quantum computing")

    assert isinstance(result, CoordinationResult)
    assert result.tasks_completed >= 1
    assert isinstance(result.final_summary, str)
    assert len(result.final_summary) > 0

    # Clean up registry so other tests aren't affected
    await registry.unregister(a1._agent_id_str)
    await registry.unregister(a2._agent_id_str)


# ── Part B: SYNTHESIZE ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_combines_results():
    """LLM synthesize is called with completed task content."""
    llm          = MagicMock()
    llm.generate = AsyncMock(return_value="Combined summary from LLM.")
    coord        = _make_coordinator(llm=llm)

    plan = CoordinationPlan(goal="do stuff")
    plan.tasks = [
        CoordinationTask(goal_id=plan.goal_id, title="T1", description="",
                         required_capability="r", assigned_to="a1",
                         assigned_to_name="Alice", status="done",
                         result_content="Result A"),
        CoordinationTask(goal_id=plan.goal_id, title="T2", description="",
                         required_capability="r", assigned_to="a2",
                         assigned_to_name="Bob", status="done",
                         result_content="Result B"),
    ]

    summary = await coord.synthesize(plan)
    assert summary == "Combined summary from LLM."
    llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_fallback_no_llm():
    """No LLM → deterministic fallback string mentioning tasks completed."""
    coord = _make_coordinator(llm=None)
    plan  = CoordinationPlan(goal="do something")
    plan.tasks = [
        CoordinationTask(goal_id=plan.goal_id, title="T", description="",
                         required_capability="r", assigned_to="a1", status="done")
    ]
    summary = await coord.synthesize(plan)
    assert "tasks completed" in summary.lower() or "1/" in summary or "1 task" in summary


@pytest.mark.asyncio
async def test_synthesize_no_completed_tasks():
    """All tasks failed → graceful fallback message."""
    coord = _make_coordinator(llm=None)
    plan  = CoordinationPlan(goal="do something")
    plan.tasks = [
        CoordinationTask(goal_id=plan.goal_id, title="T", description="",
                         required_capability="r", assigned_to="a1", status="failed")
    ]
    summary = await coord.synthesize(plan)
    assert isinstance(summary, str)
    assert len(summary) > 0


# ── Part E: AGENTS RECALL BEFORE WRITING (Sprint 8 — quality lift) ────────────

@pytest.mark.asyncio
async def test_agent_recalls_before_writing():
    """The per-task prompt must include 'Relevant prior team memory:' populated
    by agent.recall_detailed() — not an empty header.

    Setup: pre-seed the shared stream with 3 memories. Run one task through
    workspace.coordinate(). Capture the LLM prompts. Assert the recall section
    in the per-task prompt contains text drawn from the seeded memories.
    """
    import json as _json
    import os as _os
    _os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

    from walrusos import WalrusOS

    captured_prompts: list[str] = []

    class CapturePromptLLM:
        """LLM stub: returns a single-task JSON plan, captures every prompt."""
        async def generate(
            self, prompt: str, max_tokens: int = 500, json_mode: bool = False
        ) -> str:
            captured_prompts.append(prompt)
            if json_mode or "task planner" in prompt.lower():
                return _json.dumps([{
                    "title": "Synthesize the OAuth strategy",
                    "description": "Combine the team's OAuth findings.",
                    "required_capability": "synthesis",
                    "depends_on": [],
                }])
            return "Synthesizer contribution."

    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("test-recall-before-writing")

    # Connect the synthesizer so coordinate can match the task to it.
    synth = workspace.agent("Synthesizer")
    await synth.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",  # unreachable — bridge POST fails fast
        capabilities=[{"name": "synthesis"}],
    )

    # Pre-seed the shared stream with 3 memories from a different agent.
    seeder = workspace.agent("Seeder")
    stream = seeder.stream("test-recall-stream")
    await stream.append({"content": "OAuth 2.0 with PKCE prevents auth-code interception."})
    await stream.append({"content": "JWT tokens should be short-lived (15 min) to limit blast radius."})
    await stream.append({"content": "Refresh tokens must rotate on each use to detect theft."})

    # Run a single task through the full coordinate path.
    await workspace.coordinate(
        goal="Synthesize the team's OAuth strategy.",
        agents=[synth],
        stream=stream,
        llm=CapturePromptLLM(),
    )

    await synth.go_offline()

    # The decompose prompt and one per-task prompt should be captured.
    task_prompts = [p for p in captured_prompts if "Your task:" in p]
    assert task_prompts, f"No per-task prompt captured; saw {len(captured_prompts)} prompts total"

    p = task_prompts[0]

    # Section header is present, in the correct order (before deps).
    assert "Relevant prior team memory:" in p
    assert p.index("Relevant prior team memory:") < p.index("Results from prerequisite tasks:")

    # Pull the recall section's content out and check it actually has the seeds.
    after_header = p.split("Relevant prior team memory:", 1)[1]
    recall_section = after_header.split("Results from prerequisite tasks:", 1)[0]
    # Must NOT be the empty fallback when the stream had relevant content.
    assert "no relevant prior memory" not in recall_section.lower(), (
        f"Recall section is empty fallback despite seeded stream: {recall_section[:200]!r}"
    )
    # At least one of the seeded keywords must surface.
    matched = any(
        kw in recall_section
        for kw in ("OAuth", "PKCE", "JWT", "Refresh tokens")
    )
    assert matched, f"None of the seeded memory keywords in recall section: {recall_section!r}"
