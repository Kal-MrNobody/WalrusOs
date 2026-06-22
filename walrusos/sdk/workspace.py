"""
WorkspaceClient — Public SDK facade for an Event-Sourced Workspace.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from walrusos.engine.event_store import EventStoreEngine
from walrusos.core.models.events import EventType
from walrusos.sdk.agent import AgentClient
from walrusos.sdk.stream import StreamClient


class WorkspaceClient:
    """
    A workspace groups agents and streams.

    Obtain via ``runtime.workspace(name)``.

    Example::

        workspace  = runtime.workspace("research")
        researcher = workspace.agent("Researcher")
        stream     = workspace.stream("shared-notes")   # readable AND writeable

    Workspaces are lazily initialized — the workspace is registered in the
    ledger only when the first event is written.
    """

    def __init__(
        self,
        event_store:   EventStoreEngine,
        memory_engine: Any,
        name:          str,
        owner_wallet:  str = "",
        event_bus:     Any = None,
    ) -> None:
        self._engine      = event_store
        self._memory      = memory_engine
        self.name         = name
        self.owner_wallet = owner_wallet
        self._event_bus   = event_bus
        self.workspace_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
        self._initialized = False
        # Implicit system agent used for workspace-level streams.
        # Lazily created on first workspace.stream() call.
        self._system_agent: Optional[AgentClient] = None

    async def _ensure_initialized(self) -> None:
        """Internal method to ensure the workspace is registered on the ledger."""
        if self._initialized:
            return
        proj = await self._engine.replay_workspace(self.workspace_id)
        if proj is None:
            await self._engine.append(
                event_type=EventType.WorkspaceCreated,
                workspace_id=self.workspace_id,
                wallet=self.owner_wallet,
                payload_dict={"name": self.name}
            )
        self._initialized = True

    def agent(self, name: str) -> AgentClient:
        """
        Return an :class:`~walrusos.sdk.agent.AgentClient` for the named agent.

        Agents are lazily initialized — registration happens on the first
        write.  Calling ``workspace.agent('Alice')`` twice returns equivalent
        clients bound to the same underlying identity.

        Parameters
        ----------
        name:
            Human-readable agent name.  Must be consistent across process
            restarts — ``workspace.agent('Alice')`` always resolves to the
            same identity.

        Example
        -------
        ::

            researcher = workspace.agent("Researcher")
            stream     = researcher.stream("findings")
            await stream.append({"title": "Attention Is All You Need"})
        """
        return AgentClient(
            self._engine,
            self._memory,
            self.name,
            name,
            owner_wallet=self.owner_wallet,
            event_bus=self._event_bus,
        )

    def stream(self, name: str) -> StreamClient:
        """
        Return a :class:`~walrusos.sdk.stream.StreamClient` for the named stream.

        Workspace streams are **writeable** — they are backed by an implicit
        ``_workspace_system`` agent so you can call ``stream.append()`` without
        creating a named agent first.

        For agent-specific streams (with explicit signing identity) use
        ``workspace.agent('name').stream('name')`` instead.

        Parameters
        ----------
        name:
            Human-readable stream name.  The same name always resolves to
            the same stream UUID across process restarts.

        Example
        -------
        ::

            notes = workspace.stream("shared-notes")
            await notes.append({"msg": "Shared context for all agents."})

            for event, payload in await notes.timeline():
                print(payload["msg"])
        """
        # Lazily create the implicit system agent
        if self._system_agent is None:
            self._system_agent = AgentClient(
                self._engine,
                self._memory,
                self.name,
                "_workspace_system",
                owner_wallet=self.owner_wallet,
            )
        client = StreamClient(self._memory, self.name, name)
        client._bound_agent = self._system_agent
        return client

    async def list_agents(self) -> list:
        """Return all persistent AgentIdentity records for this workspace."""
        await self._ensure_initialized()
        if hasattr(self._engine.ledger, "list_agent_identities"):
            return self._engine.ledger.list_agent_identities(workspace_id=self.workspace_id)
        return []

    # ── Tasks (Phase 2) ───────────────────────────────────────────────────────

    def _get_sqlite_ledger(self) -> Any:
        ledger = self._engine.ledger
        if hasattr(ledger, "_sqlite"):
            ledger = ledger._sqlite
        return ledger

    def create_task(
        self,
        title: str,
        description: str = "",
        assigned_to: Optional["AgentClient"] = None,
        priority: int = 3,
        tags: Optional[List[str]] = None,
    ) -> "TaskClient":
        """Create a new task in the workspace."""
        from walrusos.core.models.task import Task
        from walrusos.sdk.task import TaskClient
        
        ledger = self._get_sqlite_ledger()
        if not hasattr(ledger, "save_task"):
            raise NotImplementedError("Task management requires SQLite ledger.")
            
        task = Task(
            workspace_id=self.workspace_id,
            title=title,
            description=description,
            created_by=f"workspace:{self.name}",
            assigned_to=assigned_to._agent_id_str if assigned_to else None,
            priority=priority,
            tags=tags or [],
        )
        ledger.save_task(task)

        if self._event_bus and hasattr(self._event_bus, "emit"):
            asyncio.create_task(self._event_bus.emit(
                "task.created",
                {"task_id": task.task_id, "title": title, "workspace_id": self.workspace_id},
            ))

        return TaskClient(task, ledger)

    def tasks(
        self,
        status: Optional[str] = None,
        assigned_to: Optional["AgentClient"] = None,
        tag: Optional[str] = None,
    ) -> List["TaskClient"]:
        """List tasks matching the filters."""
        from walrusos.sdk.task import TaskClient
        ledger = self._get_sqlite_ledger()
        if not hasattr(ledger, "list_tasks"):
            raise NotImplementedError("Task management requires SQLite ledger.")
            
        agent_id = assigned_to._agent_id_str if assigned_to else None
        tasks = ledger.list_tasks(self.workspace_id, status=status, assigned_to=agent_id, tag=tag)
        return [TaskClient(t, ledger) for t in tasks]

    def task(self, task_id: str) -> "TaskClient":
        """Retrieve a specific task by ID."""
        from walrusos.sdk.task import TaskClient
        ledger = self._get_sqlite_ledger()
        if not hasattr(ledger, "get_task"):
            raise NotImplementedError("Task management requires SQLite ledger.")
            
        task = ledger.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found.")
        return TaskClient(task, ledger)

    # ── Collaboration Patterns (Phase 2) ──────────────────────────────────────

    def pipeline(self, agents: List["AgentClient"], stream: "StreamClient") -> "Pipeline":
        from walrusos.runtime.collaboration import Pipeline
        return Pipeline(agents, stream)

    def broadcast(self, from_agent: "AgentClient", to_agents: List["AgentClient"], stream: "StreamClient") -> "Broadcast":
        from walrusos.runtime.collaboration import Broadcast
        return Broadcast(from_agent, to_agents, stream)

    def consensus(self, agents: List["AgentClient"], stream: "StreamClient") -> "Consensus":
        from walrusos.runtime.collaboration import Consensus
        return Consensus(agents, stream)

    # ── Synchronization (Phase 2) ─────────────────────────────────────────────

    async def sync(self) -> Any:
        from dataclasses import dataclass
        @dataclass
        class SyncResult:
            new_events: int
            bytes_downloaded: int
            time_seconds: float
            
        import time
        start_time = time.time()
        
        # In mock mode, skip synchronization logic
        if hasattr(self._engine.ledger, "_sqlite"):
            # Minimal mock implementation of sync loop
            return SyncResult(0, 0, time.time() - start_time)
            
        return SyncResult(0, 0, 0.0)

    async def checkpoint(self, label: Optional[str] = None) -> "MemoryEvent":
        from walrusos.engine.summarizer import MemorySummarizer
        from walrusos.core.models.memory import MemoryEvent
        
        # In a real implementation this would query all streams in the workspace
        # For phase 2 mock mode, we use the workspace system stream.
        sys_stream = self.stream("_workspace_system")
        summarizer = MemorySummarizer(self._memory)
        
        # This will create a checkpoint event on the stream
        title = label or f"Workspace Checkpoint {self.name}"
        cp_id = await summarizer.create_checkpoint(sys_stream.stream_id, title)
        
        mem_ev = await self._memory.ledger.get_event(cp_id)
        if mem_ev is None:
            # Fallback mock return
            return MemoryEvent(stream_id=sys_stream.stream_id, parent_id="genesis", epoch=0, content_blob_id="")
        return mem_ev

    # ── Agent Discovery (Phase 4) ─────────────────────────────────────────────

    async def discover(
        self,
        capability: Optional[str] = None,
        framework:  Optional[str] = None,
        bridge_url: str = "http://localhost:8787",
    ) -> list[dict]:
        """Find online agents by capability or framework via the bridge registry.

        Example::

            reviewers = await workspace.discover(capability="code_review")
            claude_agents = await workspace.discover(framework="claude-code")
        """
        import httpx as _httpx
        try:
            params: dict = {}
            if capability:
                params["capability"] = capability
            if framework:
                params["framework"]  = framework
            async with _httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{bridge_url}/agent/discover", params=params
                )
                return resp.json()
        except Exception:
            return []

    async def online_agents(self, bridge_url: str = "http://localhost:8787") -> list[dict]:
        """List all currently online agents from the bridge presence store."""
        import httpx as _httpx
        try:
            async with _httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{bridge_url}/agent/presence")
                return resp.json()
        except Exception:
            return []

    # ── Autonomous Runtime (Phase 4) ──────────────────────────────────────────

    async def run(
        self,
        goal:              str,
        agents:            "Optional[list[AgentClient]]" = None,
        stream:            "Optional[StreamClient]"      = None,
        max_rounds:        int                           = 10,
        on_event:          "Optional[Callable]"          = None,
        on_round_complete: "Optional[Callable]"          = None,
        llm:               "Optional[Any]"               = None,
    ) -> "RunResult":
        """
        Launch an autonomous multi-agent run toward ``goal``.

        Parameters
        ----------
        goal:
            Plain-English description of what the agents should accomplish.
        agents:
            List of AgentClient instances to involve.  Defaults to all agents
            registered in this workspace.
        stream:
            Stream to write to.  A dedicated ``run-<id>`` stream is created
            automatically when omitted.
        max_rounds:
            Maximum number of complete agent-loop iterations before stopping.
        on_event:
            Called for each agent each round: ``(agent, prompt, context) -> str``.
            The return value is written to the stream as the agent's contribution.
            Omit for stub mode (useful for testing without an LLM).
        on_round_complete:
            Called after every round: ``(round_num, list[MemoryEvent]) -> None``.
            May be a coroutine function.

        Returns
        -------
        RunResult
            Full outcome including all events, blob IDs, and Sui anchors.

        Example
        -------
        ::

            import anthropic

            client = anthropic.Anthropic()

            def call_llm(agent, prompt, context):
                msg = client.messages.create(
                    model="claude-opus-4-8",
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text

            result = await workspace.run(
                goal="Write a Python web scraper for news headlines",
                agents=[researcher, coder, writer],
                max_rounds=3,
                on_event=call_llm,
            )
            print(result.final_summary)
        """
        from walrusos.runtime.autonomous  import AutonomousRuntime
        from walrusos.core.models.run_result import RunResult  # noqa: F401 (re-export)
        return await AutonomousRuntime().run(
            self, goal, agents, stream, max_rounds, on_event, on_round_complete, llm
        )

    async def run_with_gemini(
        self,
        goal:       str,
        agents:     "Optional[list[AgentClient]]" = None,
        stream:     "Optional[StreamClient]"      = None,
        max_rounds: int                           = 5,
        api_key:    Optional[str]                 = None,
        model:      str                           = "gemini-2.5-flash",
    ) -> "RunResult":
        """Convenience wrapper: run() pre-wired with GeminiProvider."""
        from walrusos.runtime.llm import GeminiProvider
        llm = GeminiProvider(api_key=api_key, model=model)
        return await self.run(
            goal=goal, agents=agents, stream=stream,
            max_rounds=max_rounds, llm=llm,
        )

    async def coordinate(
        self,
        goal:             str,
        agents:           "Optional[list[AgentClient]]" = None,
        stream:           "Optional[StreamClient]"      = None,
        llm:              "Optional[Any]"               = None,
        on_task_complete: "Optional[Any]"               = None,
    ) -> "CoordinationResult":
        """
        Autonomously coordinate agents to achieve a goal.

        Unlike :meth:`run`, you do **not** specify which agent does what.
        The coordinator decomposes the goal into tasks, matches each to the
        best-capable online agent, and executes respecting dependencies.

        Parameters
        ----------
        goal:
            Plain-English description of what should be accomplished.
        agents:
            Optional subset of agents to use.  ``None`` uses every agent
            registered with the in-process registry (or all workspace agents
            when the registry is empty).
        stream:
            Stream to write results to.  Auto-created when omitted.
        llm:
            LLM provider for decomposition, execution, and synthesis.
            When omitted, stub responses are used (useful for testing).
        on_task_complete:
            Called after each task finishes: ``(task: CoordinationTask) -> None``.

        Returns
        -------
        CoordinationResult
            Full outcome including task graph, events, blob IDs, and Sui anchors.

        Example
        -------
        ::

            from walrusos.runtime.llm import GeminiProvider

            result = await workspace.coordinate(
                goal="Build an OAuth authentication system",
                llm=GeminiProvider(api_key="..."),
            )
            print(result.final_summary)
        """
        import time as _time
        from uuid import uuid4 as _uuid4
        from walrusos.runtime.coordinator import Coordinator
        from walrusos.runtime.registry import get_registry
        from walrusos.core.models.coordination import CoordinationResult

        start = _time.time()

        if stream is None:
            stream_name = f"coordinate-{_uuid4().hex[:8]}"
            stream = (agents[0] if agents else self._get_system_agent()).stream(stream_name)

        registry    = get_registry()
        coordinator = Coordinator(self, registry, self._event_bus, llm=llm)

        # Build agent_id_str -> AgentClient map from registry or explicit list
        agent_map: dict = {}
        if agents:
            for a in agents:
                agent_map[a._agent_id_str] = a
        else:
            for reg in registry.list_all():
                ac = self.agent(reg.agent_name)
                agent_map[ac._agent_id_str] = ac

        # Final fallback: all persisted workspace agents
        if not agent_map:
            identities = await self.list_agents()
            for ident in identities:
                if ident.agent_name != "_workspace_system":
                    ac = self.agent(ident.agent_name)
                    agent_map[ac._agent_id_str] = ac

        if not agent_map:
            raise ValueError(
                "No agents available for coordination. "
                "Register agents with workspace.agent() or connect them via go_online()."
            )

        # Collect available capabilities from registry
        available_caps: list = []
        for reg in registry.list_all():
            for cap in reg.capabilities:
                if cap.name not in available_caps:
                    available_caps.append(cap.name)
        if not available_caps:
            available_caps = ["general"]

        online_agents = [
            {"agent_id": aid, "agent_name": ac.agent_name}
            for aid, ac in agent_map.items()
        ]

        # Step 1: Decompose
        plan = await coordinator.decompose(goal, available_caps)
        plan.status = "executing"

        # Step 2: Match agents to tasks
        for task in plan.tasks:
            match = coordinator.match_agent(task, online_agents)
            if match:
                task.assigned_to, task.assigned_to_name = match

        # Notify event mesh (best-effort)
        await self._event_bus.emit("coordination.plan", {
            "goal_id": plan.goal_id,
            "goal":    goal,
            "tasks":   len(plan.tasks),
        })

        # Set pending/blocked before execution loop
        for task in plan.tasks:
            task.status = "pending" if task.assigned_to else "blocked"

        # Step 3: Execute
        events = await coordinator.execute(
            plan, agent_map, stream, on_task_complete=on_task_complete
        )

        # Step 4: Synthesize
        summary     = await coordinator.synthesize(plan)
        plan.status = "completed"

        completed = [t for t in plan.tasks if t.status == "done"]
        failed    = [t for t in plan.tasks if t.status in ("failed", "blocked")]

        await self._event_bus.emit("coordination.completed", {
            "goal_id":         plan.goal_id,
            "tasks_completed": len(completed),
            "tasks_failed":    len(failed),
        })

        return CoordinationResult(
            goal_id=plan.goal_id,
            goal=goal,
            plan=plan,
            tasks_completed=len(completed),
            tasks_failed=len(failed),
            agents_used=list({t.assigned_to for t in completed if t.assigned_to}),
            events=events,
            final_summary=summary,
            duration_seconds=_time.time() - start,
            blob_ids=[
                getattr(e, "blob_id", None) for e in events
                if getattr(e, "blob_id", None)
            ],
            sui_anchors=[
                getattr(e, "transaction_digest", None) for e in events
                if getattr(e, "transaction_digest", None)
            ],
            completed=(len(failed) == 0),
        )

    def _get_system_agent(self) -> "AgentClient":
        if self._system_agent is None:
            self._system_agent = AgentClient(
                self._engine,
                self._memory,
                self.name,
                "_workspace_system",
                owner_wallet=self.owner_wallet,
            )
        return self._system_agent

    def __repr__(self) -> str:
        return f"<WorkspaceClient {self.name!r} id={self.workspace_id}>"
