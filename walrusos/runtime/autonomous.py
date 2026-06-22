"""
AutonomousRuntime — multi-agent goal-driven execution loop.

Every contribution is signed and stored on Walrus, anchored on Sui.
An agent signals completion by including "DONE" in its response.
Without an LLM callback, stub responses are used (useful for testing).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, List, Optional
from uuid import uuid4


def _summarize_run(goal: str, event_texts: list[tuple[str, str]]) -> str:
    """Build a short human-readable summary from (agent_name, response) pairs."""
    if not event_texts:
        return f"No contributions recorded for: {goal}"
    agents = list(dict.fromkeys(name for name, _ in event_texts))
    tail = event_texts[-3:]
    lines = [f"  [{name}] {text[:100]}" for name, text in tail]
    return (
        f"Goal: {goal}\n"
        f"Agents involved: {', '.join(agents)}\n"
        f"Latest contributions:\n" + "\n".join(lines)
    )


class AutonomousRuntime:
    """Stateless executor — instantiate once, call run() many times."""

    async def _get_all_agents(self, workspace: Any) -> list:
        """Return AgentClient objects for every non-system agent in the workspace."""
        identities = await workspace.list_agents()
        return [
            workspace.agent(ident.agent_name)
            for ident in identities
            if ident.agent_name != "_workspace_system"
        ]

    async def run(
        self,
        workspace:         Any,
        goal:              str,
        agents:            Optional[List[Any]],
        stream:            Optional[Any],
        max_rounds:        int,
        on_event:          Optional[Callable],
        on_round_complete: Optional[Callable],
        llm:               Optional[Any] = None,
    ) -> Any:
        from walrusos.core.models.memory    import MemoryEvent
        from walrusos.core.models.run_result import RunResult

        start_time    = time.time()
        all_mem_events: List[MemoryEvent] = []
        all_blob_ids:   List[str]         = []
        all_anchors:    List[str]         = []
        event_texts:    list[tuple[str, str]] = []   # (agent_name, response)
        completed      = False
        round_num      = 1   # keeps the last value even if the loop body never executes

        # ── Resolve agents ────────────────────────────────────────────────────
        if agents is None:
            agents = await self._get_all_agents(workspace)
        if not agents:
            raise ValueError(
                "No agents available for autonomous run. "
                "Pass agents=[...] or register agents in the workspace first."
            )

        # ── Resolve stream ────────────────────────────────────────────────────
        if stream is None:
            stream_name = f"run-{uuid4().hex[:8]}"
            stream = agents[0].stream(stream_name)

        # ── Main loop ─────────────────────────────────────────────────────────
        for round_num in range(1, max_rounds + 1):
            round_mem_events: List[MemoryEvent] = []

            for agent in agents:
                # Build context from everything written so far
                try:
                    context = await agent.build_context(
                        stream,
                        query=goal,
                        max_tokens=1500,
                        strategy="smart",
                    )
                except Exception:
                    context = ""

                prompt = (
                    f"You are {agent.agent_name}.\n\n"
                    f"Goal: {goal}\n\n"
                    f"What has been done so far:\n"
                    f"{context if context else 'Nothing yet — you are first.'}\n\n"
                    f"Your role: Contribute your specific expertise toward the goal.\n"
                    f"Be concrete and specific. Build directly on what others have done.\n"
                    f"Do not repeat what others have already said.\n"
                    f"If the goal is fully complete, end your response with: DONE\n\n"
                    f"Your contribution:"
                )

                # ── Get response — priority: on_event > llm > stub ───────────
                if on_event is not None:
                    try:
                        response = on_event(agent, prompt, context or "")
                        if asyncio.iscoroutine(response):
                            response = await response
                    except Exception as exc:
                        response = f"[{agent.agent_name}] Error: {exc}"
                elif llm is not None:
                    try:
                        response = await llm.generate(prompt, max_tokens=500)
                    except Exception as exc:
                        response = f"[{agent.agent_name}] LLM error: {exc}"
                else:
                    # Stub mode — no LLM required
                    response = (
                        f"[{agent.agent_name}] Round {round_num}: "
                        f"Contributing to '{goal[:40]}...'"
                    )

                # ── Write event to Walrus + Sui ───────────────────────────────
                proto_event = await agent._write_event(
                    stream,
                    {"text": response, "round": round_num},
                    memory_type="observation",
                    tags=["autonomous-run", f"round-{round_num}"],
                    importance=0.8,
                )

                # ── Wrap as MemoryEvent for RunResult ─────────────────────────
                mem_event = MemoryEvent(
                    id=proto_event.event_id,
                    stream_id=stream.stream_id,
                    parent_id=proto_event.parent_event or "genesis",
                    epoch=round_num,
                    content_blob_id=proto_event.blob_id or proto_event.event_id,
                    agent_id=agent._agent_id_str,
                    memory_type="observation",
                    tags=["autonomous-run", f"round-{round_num}"],
                    importance=0.8,
                )

                round_mem_events.append(mem_event)
                all_mem_events.append(mem_event)
                all_blob_ids.append(mem_event.content_blob_id)
                if proto_event.transaction_digest:
                    all_anchors.append(proto_event.transaction_digest)
                event_texts.append((agent.agent_name, response))

                # ── Completion check ──────────────────────────────────────────
                if "DONE" in response.upper():
                    completed = True
                    break

            # ── Round-complete callback ───────────────────────────────────────
            if on_round_complete is not None:
                result = on_round_complete(round_num, round_mem_events)
                if asyncio.iscoroutine(result):
                    await result

            if completed:
                break

        # ── Checkpoint the run ────────────────────────────────────────────────
        try:
            await stream.checkpoint(f"Run complete: {goal[:50]}")
        except Exception:
            pass

        return RunResult(
            goal=goal,
            rounds_completed=round_num,
            events=all_mem_events,
            agents_involved=[agent._agent_id_str for agent in agents],
            final_summary=_summarize_run(goal, event_texts),
            completed=completed,
            duration_seconds=time.time() - start_time,
            blob_ids=all_blob_ids,
            sui_anchors=all_anchors,
        )
