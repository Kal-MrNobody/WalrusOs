"""
Sprint 8 — Tests for the end-to-end multi-agent workflow.

Verifies that four agents with distinct capabilities can register and that
workspace.coordinate() routes each decomposed task to the agent whose
declared capability matches the required_capability.

Trading Agent safety: this test ALSO verifies the trading agent is
configured as analysis-only — its tools list contains no execution
verbs, and its capabilities are restricted to market_analysis and
risk_assessment. This is enforced by code, not just convention.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_full_workflow.py -v
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

import pytest

from walrusos import WalrusOS
from walrusos.runtime.registry import get_registry


# ── Fake planner LLM: returns a 4-task JSON array for the decompose step ─────

class FakePlannerLLM:
    """LLM stub that returns a 4-task plan for decompose, plain strings for
    per-task execution. Lets us verify routing without hitting Gemini."""

    PLAN = [
        {
            "title": "Market landscape research",
            "description": "Survey the decentralized data-storage market.",
            "required_capability": "research",
            "depends_on": [],
        },
        {
            "title": "Hypothetical risk/opportunity analysis",
            "description": "Write a HYPOTHETICAL risk/opportunity memo — analysis only.",
            "required_capability": "risk_assessment",
            "depends_on": [0],
        },
        {
            "title": "Technical implementation outline",
            "description": "Outline an implementation approach in pseudocode.",
            "required_capability": "code_generation",
            "depends_on": [0],
        },
        {
            "title": "Final go/no-go synthesis",
            "description": "Synthesize the research, risk memo, and tech outline.",
            "required_capability": "synthesis",
            "depends_on": [0, 1, 2],
        },
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def generate(
        self, prompt: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str:
        self.calls.append((prompt[:80], {"json_mode": json_mode}))
        if "task planner" in prompt.lower() or json_mode:
            return json.dumps(self.PLAN)
        # Per-task execution prompt
        if "You are " in prompt:
            agent_line = prompt.split("\n", 1)[0]
            return f"{agent_line.replace('You are ', '').strip().rstrip('.')} contribution."
        return "ok"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _connect_four(workspace) -> dict:
    """Spin up Research, Trading (analysis-only), Coding, Chief and go_online.
    Returns a name → AgentClient map."""
    research = workspace.agent("Research")
    trading  = workspace.agent("Trading")
    coding   = workspace.agent("Coding")
    chief    = workspace.agent("Chief")

    # bridge_url points at a non-existent port in tests so the HTTP call fails
    # fast; go_online still registers in the in-process AgentRegistry.
    await research.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",
        capabilities=[
            {"name": "research"},
            {"name": "analysis"},
            {"name": "summarization"},
        ],
    )
    # Trading agent — ANALYSIS ONLY. No execution capabilities, no order-placing tools.
    await trading.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",
        capabilities=[
            {"name": "market_analysis"},
            {"name": "risk_assessment"},
        ],
        tools=[],  # explicitly no tools — analysis output only, no actions
    )
    await coding.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",
        capabilities=[
            {"name": "code_generation"},
            {"name": "code_review"},
            {"name": "debugging"},
        ],
    )
    await chief.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",
        capabilities=[
            {"name": "planning"},
            {"name": "synthesis"},
            {"name": "decision_making"},
        ],
    )

    return {
        "Research": research,
        "Trading":  trading,
        "Coding":   coding,
        "Chief":    chief,
    }


@pytest.fixture(autouse=True)
async def _clean_registry():
    """Each test starts with an empty registry."""
    registry = get_registry()
    registry._agents.clear()
    yield
    registry._agents.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFourAgentsRegister:
    async def test_four_agents_register(self) -> None:
        """All four agents go_online → registry has 4 entries with declared caps."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("workflow-test-register")
        agents    = await _connect_four(workspace)

        registry = get_registry()
        all_regs = registry.list_all()
        assert len(all_regs) == 4
        names = {r.agent_name for r in all_regs}
        assert names == {"Research", "Trading", "Coding", "Chief"}

        for agent in agents.values():
            await agent.go_offline()

    async def test_each_agent_declares_correct_capabilities(self) -> None:
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("workflow-test-caps")
        agents    = await _connect_four(workspace)

        registry = get_registry()
        by_name  = {r.agent_name: r for r in registry.list_all()}

        assert {c.name for c in by_name["Research"].capabilities} == {
            "research", "analysis", "summarization",
        }
        assert {c.name for c in by_name["Coding"].capabilities} == {
            "code_generation", "code_review", "debugging",
        }
        assert {c.name for c in by_name["Chief"].capabilities} == {
            "planning", "synthesis", "decision_making",
        }

        for agent in agents.values():
            await agent.go_offline()

    async def test_trading_agent_is_analysis_only(self) -> None:
        """SAFETY: Trading agent must never carry execution capabilities or tools.
        Asserted in code so the constraint can't drift silently."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("workflow-test-trading-safety")
        agents    = await _connect_four(workspace)

        registry = get_registry()
        trading  = next(r for r in registry.list_all() if r.agent_name == "Trading")

        cap_names = {c.name for c in trading.capabilities}
        # Allowed analyst-only capabilities
        assert cap_names == {"market_analysis", "risk_assessment"}

        # No execution capability words allowed
        forbidden = {
            "trade", "order_placement", "trade_execution",
            "withdraw", "transfer", "execute", "buy", "sell",
        }
        assert cap_names.isdisjoint(forbidden), (
            f"Trading agent must be analysis-only; found execution capability: "
            f"{cap_names & forbidden}"
        )
        # Tools list must be empty (no exchange clients, no order APIs)
        assert trading.tools_exposed == [], (
            f"Trading agent must expose no tools; found {trading.tools_exposed}"
        )

        for agent in agents.values():
            await agent.go_offline()


class TestCoordinateRoutesByCapability:
    async def test_coordinate_routes_each_task_to_matching_capability(self) -> None:
        """Stub planner returns 4 tasks; each must be routed to the agent
        whose declared capability matches required_capability."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("workflow-test-route")
        agents    = await _connect_four(workspace)

        fake_llm = FakePlannerLLM()
        result = await workspace.coordinate(
            goal="Produce a research brief on a decentralized data-storage startup.",
            llm=fake_llm,
        )

        # The plan must have 4 tasks with the expected capabilities
        plan_caps = [t.required_capability for t in result.plan.tasks]
        assert plan_caps == [
            "research", "risk_assessment", "code_generation", "synthesis",
        ]

        # Each task must be routed to the agent whose capability matches
        expected_assignment = {
            "research":        "Research",
            "risk_assessment": "Trading",
            "code_generation": "Coding",
            "synthesis":       "Chief",
        }
        for task in result.plan.tasks:
            assert task.assigned_to_name == expected_assignment[task.required_capability], (
                f"Task {task.title!r} (cap={task.required_capability}) "
                f"should be routed to {expected_assignment[task.required_capability]} "
                f"but went to {task.assigned_to_name}"
            )

        # All 4 should complete with the stub LLM
        assert result.tasks_completed == 4
        assert result.tasks_failed    == 0
        assert len(result.agents_used) == 4  # all four agents touched the plan

        for agent in agents.values():
            await agent.go_offline()

    async def test_coordinate_respects_task_dependencies(self) -> None:
        """The Chief synthesis task depends on the other three; it must complete
        AFTER the other three are marked done."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("workflow-test-deps")
        agents    = await _connect_four(workspace)

        completion_order: list[str] = []

        def on_task(task) -> None:
            completion_order.append(task.required_capability)

        await workspace.coordinate(
            goal="Goal.",
            llm=FakePlannerLLM(),
            on_task_complete=on_task,
        )

        # Synthesis must finish last (depends on the other three)
        assert completion_order[-1] == "synthesis"
        # Research has no deps and must finish first
        assert completion_order[0] == "research"

        for agent in agents.values():
            await agent.go_offline()
