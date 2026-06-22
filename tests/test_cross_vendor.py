"""
Sprint 8 — Tests for the cross-vendor agent collaboration demo.

Verifies:
  1. Two Gemini-framework agents can co-exist on a shared workspace with
     distinct capabilities.
  2. A subscribed agent's callback fires when another agent writes to the
     shared stream (event-mesh propagation).
  3. The reacting agent calls recall_detailed and the resulting prompt
     contains BOTH the triggering memory AND recalled prior context.
  4. The full Analyst → Critic chain runs autonomously from a single seed.

Run with:
    $env:WALRUSOS_USE_MOCKS="1"
    python -m pytest tests/test_cross_vendor.py -v
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("WALRUSOS_USE_MOCKS", "1")

import pytest

from walrusos import WalrusOS
from walrusos.runtime.registry import get_registry


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def _clean_registry():
    """Each test starts with an empty in-process registry."""
    registry = get_registry()
    registry._agents.clear()
    yield
    registry._agents.clear()


async def _connect_pair(workspace) -> tuple:
    """Spin up Gemini Analyst + Gemini Critic, both go_online. Returns
    (analyst, critic)."""
    analyst = workspace.agent("Gemini Analyst")
    critic  = workspace.agent("Gemini Critic")

    await analyst.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",  # unreachable in tests — HTTP fails fast
        capabilities=[{"name": "analysis"}, {"name": "research"}],
    )
    await critic.go_online(
        framework="gemini",
        bridge_url="http://127.0.0.1:1",
        capabilities=[{"name": "review"}, {"name": "critique"}],
    )
    return analyst, critic


# ── Test 1: registration on shared workspace ─────────────────────────────────

class TestSharedWorkspaceRegistration:
    async def test_two_gemini_agents_register_on_shared_workspace(self):
        """Both agents go_online → registry has 2 entries with framework=gemini
        and the declared capabilities, sharing the same workspace_id."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("default")  # SHARED workspace name
        analyst, critic = await _connect_pair(workspace)

        registry = get_registry()
        all_regs = registry.list_all()
        assert len(all_regs) == 2

        names_to_reg = {r.agent_name: r for r in all_regs}
        assert "Gemini Analyst" in names_to_reg
        assert "Gemini Critic"  in names_to_reg

        for r in all_regs:
            assert r.framework == "gemini"
            assert r.workspace_id == str(workspace.workspace_id)

        assert {c.name for c in names_to_reg["Gemini Analyst"].capabilities} == {
            "analysis", "research",
        }
        assert {c.name for c in names_to_reg["Gemini Critic"].capabilities} == {
            "review", "critique",
        }

        await analyst.go_offline()
        await critic.go_offline()


# ── Test 2: subscribe triggers reaction ───────────────────────────────────────

class TestSubscribeTriggersReaction:
    async def test_writing_invokes_subscribed_callback(self):
        """When another agent writes to the shared stream, the subscriber's
        callback is invoked with the new event."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("default")
        analyst, critic = await _connect_pair(workspace)

        # Both agents bind to the SAME stream name → same stream_id
        stream      = analyst.stream("cross-vendor-collab")
        critic_view = critic.stream("cross-vendor-collab")
        assert stream.stream_id == critic_view.stream_id

        received: list = []

        async def critic_callback(event):
            received.append(event)

        await critic.subscribe(stream, critic_callback)
        # Give the subscription a moment to register
        await asyncio.sleep(0.05)

        # Analyst writes; Critic's callback should fire (in-process EventBus)
        await stream.append({"content": "Analyst's first finding."})
        await asyncio.sleep(0.2)  # let async callback drain

        assert len(received) >= 1, (
            "Critic's subscription callback was not invoked after Analyst's write"
        )

        await analyst.unsubscribe(stream)
        await critic.unsubscribe(stream)
        await analyst.go_offline()
        await critic.go_offline()


# ── Test 3: recall populates the reacting agent's prompt ─────────────────────

class TestRecallUsedInReaction:
    async def test_reacting_agent_recalls_prior_context(self):
        """When Critic reacts to Analyst, the prompt it builds via
        recall_detailed must contain BOTH the triggering memory AND prior
        context from the seeded stream."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("default")
        analyst, critic = await _connect_pair(workspace)

        stream = analyst.stream("cross-vendor-collab")

        # Seed the shared stream with 3 prior memories so recall finds something
        await stream.append({"content": "OAuth 2.0 with PKCE is the recommended auth flow."})
        await stream.append({"content": "JWT tokens must be short-lived to limit blast radius."})
        await stream.append({"content": "Refresh tokens require rotation on each use."})

        captured_prompts: list[str] = []

        # Simulate Critic's reaction: when Analyst writes, Critic recalls and
        # we capture the resulting prompt (same shape as the demo script's
        # _react_as helper)
        triggering_content_hint = (
            "Analyst's contribution: prefer short JWT lifetimes for security."
        )

        async def critic_react(event):
            # Pull the triggering payload
            payload = {}
            try:
                if hasattr(stream._memory, "read"):
                    payload = await stream._memory.read(event.event_id) or {}
            except Exception:
                pass
            triggering_text = (
                payload.get("content") or payload.get("text") or ""
            )
            # Recall — Sprint 6
            recall = await critic.recall_detailed(
                stream,
                f"critical review {triggering_text}",
                max_tokens=1200,
            )
            prompt = (
                f"You are {critic.agent_name}, the critical reviewer.\n"
                f"Triggering memory: {triggering_text}\n"
                f"Relevant prior team memory:\n{recall.get('context', '')}\n"
            )
            captured_prompts.append(prompt)

        await critic.subscribe(stream, critic_react)
        await asyncio.sleep(0.05)

        # Analyst writes — Critic should react
        await stream.append({"content": triggering_content_hint})
        await asyncio.sleep(0.4)  # let the async callback finish recall + build

        await critic.unsubscribe(stream)
        await analyst.go_offline()
        await critic.go_offline()

        assert captured_prompts, "Critic's reaction was not captured"
        prompt = captured_prompts[0]

        # Triggering memory present
        assert "prefer short JWT lifetimes" in prompt or "JWT lifetimes" in prompt, (
            f"Triggering memory not in prompt: {prompt[:300]!r}"
        )
        # Recalled prior context present (at least one of the seeds)
        recall_section = prompt.split("Relevant prior team memory:", 1)[1] if "Relevant prior team memory:" in prompt else ""
        matched_seed = any(
            kw in recall_section
            for kw in ("OAuth", "PKCE", "JWT", "Refresh tokens")
        )
        assert matched_seed, (
            f"No seeded prior-memory keywords found in recall section: "
            f"{recall_section[:300]!r}"
        )


# ── Test 4: full Analyst → Critic chain runs autonomously from a seed ────────

class TestCrossVendorChainAutonomous:
    async def test_seed_produces_two_downstream_reactions(self):
        """In auto mode, a single seed write to the shared stream must trigger
        Analyst (1 reaction) and then Critic (1 reaction) — at least 2
        downstream reactions in total."""
        runtime   = WalrusOS(use_mocks=True)
        workspace = runtime.workspace("default")
        analyst, critic = await _connect_pair(workspace)

        # Also need a third "Coordinator" agent to write the seed
        coordinator = workspace.agent("Coordinator")
        await coordinator.go_online(
            framework="custom",
            bridge_url="http://127.0.0.1:1",
            capabilities=[{"name": "planning"}],
        )

        stream      = coordinator.stream("cross-vendor-collab")
        analyst_view = analyst.stream("cross-vendor-collab")
        critic_view  = critic.stream("cross-vendor-collab")
        assert stream.stream_id == analyst_view.stream_id == critic_view.stream_id

        analyst_done = asyncio.Event()
        critic_done  = asyncio.Event()
        reactions: list[str] = []

        async def analyst_callback(event):
            if analyst_done.is_set():
                return
            if str(getattr(event, "agent_id", "")) == analyst._agent_id_str:
                return
            if str(getattr(event, "agent_id", "")) == critic._agent_id_str:
                return
            # Recall (Sprint 6) — works fine even on a near-empty stream
            await analyst.recall_detailed(stream, "analysis", max_tokens=600)
            await analyst_view.append({
                "content": "Analyst's response: building on the seed.",
                "reactor": analyst.agent_name,
            })
            reactions.append("analyst")
            analyst_done.set()

        async def critic_callback(event):
            if critic_done.is_set():
                return
            if str(getattr(event, "agent_id", "")) == critic._agent_id_str:
                return
            # Critic only reacts to Analyst's writes (not the seed)
            if str(getattr(event, "agent_id", "")) != analyst._agent_id_str:
                return
            await critic.recall_detailed(stream, "critique", max_tokens=600)
            await critic_view.append({
                "content": "Critic's refinement: building on Analyst.",
                "reactor": critic.agent_name,
            })
            reactions.append("critic")
            critic_done.set()

        await analyst_view.subscribe(stream, analyst_callback) if False else None  # noqa
        await analyst.subscribe(analyst_view, analyst_callback)
        await critic.subscribe(critic_view, critic_callback)
        await asyncio.sleep(0.05)

        # Coordinator writes the seed
        await stream.append({
            "content": "Kickoff seed: should we adopt zero-trust networking?",
            "role": "seed",
        })

        # Wait for the chain
        try:
            await asyncio.wait_for(critic_done.wait(), timeout=10)
        except asyncio.TimeoutError:
            pytest.fail(
                f"Chain timed out. Reactions so far: {reactions}. "
                f"analyst_done={analyst_done.is_set()}, "
                f"critic_done={critic_done.is_set()}"
            )

        assert "analyst" in reactions, f"Analyst did not react. Reactions: {reactions}"
        assert "critic"  in reactions, f"Critic did not react. Reactions: {reactions}"
        assert reactions.index("analyst") < reactions.index("critic"), (
            f"Critic reacted before Analyst. Order: {reactions}"
        )
        assert len(reactions) >= 2

        # Cleanup
        await analyst.unsubscribe(analyst_view)
        await critic.unsubscribe(critic_view)
        await analyst.go_offline()
        await critic.go_offline()
        await coordinator.go_offline()
