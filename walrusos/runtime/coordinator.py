"""
Coordinator — autonomous task decomposition, matching, and execution.

Four steps:
  1. DECOMPOSE  — LLM breaks a goal into capability-tagged tasks
  2. MATCH      — Registry finds the best online agent per task
  3. EXECUTE    — Tasks run in parallel where possible, respecting depends_on
  4. SYNTHESIZE — LLM combines results into a final summary

Sits on top of the existing runtime without replacing it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from walrusos.core.models.coordination import (
    CoordinationPlan,
    CoordinationTask,
)

logger = logging.getLogger(__name__)


class Coordinator:
    def __init__(
        self,
        workspace:  Any,
        registry:   Any,
        event_mesh: Any,
        llm:        Optional[Any] = None,
    ) -> None:
        self.workspace  = workspace
        self.registry   = registry
        self.event_mesh = event_mesh
        self.llm        = llm

    # ── Step 1: DECOMPOSE ─────────────────────────────────────────────────────

    async def decompose(
        self,
        goal: str,
        available_capabilities: List[str],
    ) -> CoordinationPlan:
        """Use LLM to break a goal into capability-tagged tasks."""
        plan = CoordinationPlan(goal=goal)

        if not self.llm:
            plan.tasks = [CoordinationTask(
                goal_id=plan.goal_id,
                title=goal[:60],
                description=goal,
                required_capability=(
                    available_capabilities[0] if available_capabilities else "general"
                ),
            )]
            return plan

        cap_list = ", ".join(available_capabilities) if available_capabilities else "general"
        prompt = (
            f"You are a task planner for a multi-agent AI system.\n\n"
            f"Goal: {goal}\n\n"
            f"Available agent capabilities: {cap_list}\n\n"
            f"Break this goal into 3-5 tasks. Assign each to ONE capability from the list.\n"
            f"Keep each description under 200 characters. Tasks may depend on earlier ones.\n\n"
            f"Return ONLY a JSON array (no prose, no markdown):\n"
            f"[\n"
            f'  {{"title": "...", "description": "...", "required_capability": "...", "depends_on": []}}\n'
            f"]\n\n"
            f"depends_on uses 0-based indices of prerequisite tasks (e.g. [0, 1])."
        )

        def _extract_json_array(text: str) -> list:
            text = text.replace("```json", "").replace("```", "").strip()
            start = text.find("[")
            end   = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]
            return json.loads(text)

        try:
            response   = await self.llm.generate(prompt, max_tokens=2048, json_mode=True)
            task_dicts = _extract_json_array(response)

            if not isinstance(task_dicts, list) or len(task_dicts) == 0:
                raise ValueError("Empty or non-list response")

            created: List[CoordinationTask] = []
            for i, td in enumerate(task_dicts):
                task = CoordinationTask(
                    goal_id=plan.goal_id,
                    title=td.get("title", f"Task {i + 1}"),
                    description=td.get("description", ""),
                    required_capability=td.get("required_capability", "general"),
                )
                created.append(task)

            # Second pass: resolve integer indices → task_ids
            for i, td in enumerate(task_dicts):
                dep_indices = td.get("depends_on", [])
                created[i].depends_on = [
                    created[j].task_id
                    for j in dep_indices
                    if isinstance(j, int) and 0 <= j < len(created)
                ]

            plan.tasks = created

        except Exception as exc:
            logger.warning("decompose failed (%s) — falling back to single task", exc)
            print(f"decompose JSON parse failed: {exc}")
            if "response" in dir():
                print(f"  raw response (first 300 chars): {response[:300]}")  # type: ignore[possibly-undefined]
            plan.tasks = [CoordinationTask(
                goal_id=plan.goal_id,
                title=goal[:60],
                description=goal,
                required_capability=(
                    available_capabilities[0] if available_capabilities else "general"
                ),
            )]

        return plan

    # ── Step 2: MATCH ─────────────────────────────────────────────────────────

    def match_agent(
        self,
        task:          CoordinationTask,
        online_agents: List[Dict[str, Any]],
    ) -> Optional[Tuple[str, str]]:
        """
        Find the best agent for a task by capability.
        Returns (agent_id_str, agent_name) or None.
        """
        online_ids = {a.get("agent_id") for a in online_agents}

        # Prefer agents that explicitly advertise the required capability
        candidates = self.registry.find_by_capability(task.required_capability)
        online_candidates = [c for c in candidates if c.agent_id in online_ids]

        if online_candidates:
            chosen = online_candidates[0]
            return (chosen.agent_id, chosen.agent_name)

        # Fallback: any online agent
        if online_agents:
            a = online_agents[0]
            return (a.get("agent_id"), a.get("agent_name"))

        return None

    # ── Step 3: EXECUTE ───────────────────────────────────────────────────────

    async def execute(
        self,
        plan:             CoordinationPlan,
        agents:           Dict[str, Any],   # agent_id_str → AgentClient
        stream:           Any,
        on_task_complete: Optional[Callable] = None,
    ) -> List[Any]:
        """Execute the plan respecting depends_on. Parallel where possible."""
        all_events:   List[Any] = []
        completed_ids: set[str] = set()
        max_iterations = max(len(plan.tasks) * 3, 6)

        for _ in range(max_iterations):
            ready = [
                t for t in plan.tasks
                if t.status == "pending"
                and all(dep in completed_ids for dep in t.depends_on)
            ]

            if not ready:
                remaining = [t for t in plan.tasks if t.status == "pending"]
                for t in remaining:
                    t.status = "blocked"
                break

            results = await asyncio.gather(
                *[self._run_task(t, plan, agents, stream) for t in ready],
                return_exceptions=True,
            )

            for task, result in zip(ready, results):
                if isinstance(result, Exception):
                    logger.warning("task %s failed: %s", task.title, result)
                    task.status = "failed"
                elif task.status == "done":
                    completed_ids.add(task.task_id)
                    if result is not None:
                        all_events.append(result)
                    if on_task_complete:
                        try:
                            on_task_complete(task)
                        except Exception:
                            pass

            if all(t.status in ("done", "failed", "blocked") for t in plan.tasks):
                break

        return all_events

    async def _run_task(
        self,
        task:   CoordinationTask,
        plan:   CoordinationPlan,
        agents: Dict[str, Any],
        stream: Any,
    ) -> Optional[Any]:
        agent = agents.get(task.assigned_to)
        if not agent:
            task.status = "failed"
            return None

        task.status = "in_progress"
        try:
            await agent.set_status("working")
        except Exception:
            pass

        # Build context from completed dependency results.
        # When total content exceeds ~1000 chars, rank pieces by relevance to
        # this task and compress within a 250-token budget so prompts stay bounded.
        dep_pieces = []
        for dep_id in task.depends_on:
            dep_task = next((t for t in plan.tasks if t.task_id == dep_id), None)
            if dep_task and dep_task.result_content:
                dep_pieces.append(f"[{dep_task.title}]: {dep_task.result_content}")

        if not dep_pieces:
            dep_context = ""
        elif sum(len(p) for p in dep_pieces) <= 1000:
            dep_context = "\n".join(dep_pieces)
        else:
            from walrusos.engine.token_budget import TokenBudget
            from walrusos.engine.ranking import keyword_overlap_score
            ranked_pieces = sorted(
                dep_pieces,
                key=lambda p: keyword_overlap_score(task.title, p),
                reverse=True,
            )
            budget = TokenBudget(250)
            dep_context = "\n".join(p for p in ranked_pieces if budget.add(p))

        # Recall relevant prior team memory (Sprint 6 context builder).
        # The agent reads what the WHOLE team — including other vendors — has
        # written to the shared stream, so its contribution builds on prior
        # work instead of being a parallel monologue.
        recall_context = ""
        if hasattr(agent, "recall_detailed"):
            try:
                recall_query = (
                    f"{task.title} {task.required_capability or ''} {task.description}"
                ).strip()
                recall_result = await agent.recall_detailed(
                    stream, recall_query, max_tokens=1200,
                )
                if recall_result.get("events_included", 0) > 0:
                    ctx = recall_result.get("context", "")
                    if ctx and ctx.strip():
                        recall_context = ctx
            except Exception as exc:
                logger.debug("recall failed for task %s: %s", task.title, exc)

        prompt = (
            f"You are {agent.agent_name}.\n\n"
            f"Overall goal: {plan.goal}\n\n"
            f"Your task: {task.title}\n"
            f"{task.description}\n\n"
            f"Relevant prior team memory:\n"
            f"{recall_context if recall_context else '(no relevant prior memory found — this is the first contribution on this topic.)'}\n\n"
            f"Results from prerequisite tasks:\n"
            f"{dep_context if dep_context else 'None - you are starting fresh.'}\n\n"
            f"Provide your concrete contribution to this task, building on the prior memory above."
        )

        if self.llm:
            try:
                response = await self.llm.generate(prompt, max_tokens=600)
            except Exception as exc:
                response = f"[{agent.agent_name}] Error: {exc}"
        else:
            response = f"[{agent.agent_name}] Completed: {task.title}"

        # Write to Walrus + Sui via the existing pipeline
        result = await agent._write_event(
            stream,
            {"text": response, "task_title": task.title,
             "capability": task.required_capability},
            memory_type="observation",
            tags=["coordination", task.required_capability],
            importance=0.8,
        )

        task.status          = "done"
        task.result_content  = response
        task.result_event_id = getattr(result, "event_id", None)
        task.completed_at    = datetime.utcnow()

        try:
            await agent.set_status("idle")
        except Exception:
            pass

        await self.event_mesh.emit("task.completed", {
            "task_id":    task.task_id,
            "title":      task.title,
            "agent_id":   task.assigned_to,
            "agent_name": task.assigned_to_name,
        })

        return result

    # ── Step 4: SYNTHESIZE ────────────────────────────────────────────────────

    async def synthesize(self, plan: CoordinationPlan) -> str:
        """Combine task results into a final summary."""
        completed = [t for t in plan.tasks if t.status == "done"]

        if not completed:
            return f"Goal '{plan.goal}': no tasks completed."

        if not self.llm:
            agents_used = len(set(t.assigned_to for t in completed))
            return (
                f"Goal '{plan.goal}': {len(completed)}/{len(plan.tasks)} tasks completed "
                f"by {agents_used} agent(s)."
            )

        results_text = "\n\n".join(
            f"[{t.title}] ({t.assigned_to_name}): {(t.result_content or '')[:300]}"
            for t in completed
        )
        prompt = (
            f"Goal: {plan.goal}\n\n"
            f"Task results:\n{results_text}\n\n"
            f"Write a 2-3 sentence summary of what was accomplished toward the goal."
        )

        try:
            return await self.llm.generate(prompt, max_tokens=300)
        except Exception:
            agents_used = len(set(t.assigned_to for t in completed))
            return (
                f"Goal '{plan.goal}': {len(completed)} tasks completed "
                f"by {agents_used} agent(s)."
            )
