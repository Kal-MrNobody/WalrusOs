"""
PresenceStore — in-process, ephemeral agent presence registry.

Not persisted to SQLite. Lives for the lifetime of the bridge process.
Subscribers (WebSocket handlers) receive JSON-encoded messages on any change.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Callable, List, Optional

from walrusos.core.models.session import AgentSession, SessionAction, SessionStatus

# ── PresenceStore ─────────────────────────────────────────────────────────────

class PresenceStore:
    def __init__(self) -> None:
        self._sessions:    dict[str, AgentSession] = {}
        self._lock:        asyncio.Lock            = asyncio.Lock()
        self._subscribers: List[Callable]          = []

    # ── Registration ──────────────────────────────────────────────────────────

    async def register(
        self,
        agent_id:    str,
        agent_name:  str,
        workspace_id: str,
        framework:   str = "custom",
        session_id:  Optional[str] = None,
    ) -> AgentSession:
        async with self._lock:
            session = AgentSession(
                agent_id=agent_id,
                agent_name=agent_name,
                workspace_id=workspace_id,
                framework=framework,
            )
            if session_id:
                session.session_id = session_id
            self._sessions[agent_id] = session

        await self._broadcast("agent_joined", session.model_dump(mode="json"))
        return session

    async def heartbeat(
        self,
        agent_id:    str,
        status:      Optional[SessionStatus]  = None,
        current_task_id:      Optional[str]   = None,
        current_task_label:   Optional[str]   = None,
        current_file:         Optional[str]   = None,
        current_memory_query: Optional[str]   = None,
        memory_reads_delta:   int = 0,
        memory_writes_delta:  int = 0,
        artifacts_delta:      int = 0,
        tasks_delta:          int = 0,
    ) -> AgentSession:
        async with self._lock:
            if agent_id not in self._sessions:
                raise KeyError(f"Unknown agent: {agent_id}")

            s = self._sessions[agent_id]
            s.last_heartbeat = datetime.utcnow()
            if status              is not None: s.status               = status
            if current_task_id    is not None: s.current_task_id      = current_task_id
            if current_task_label is not None: s.current_task_label   = current_task_label
            if current_file       is not None: s.current_file         = current_file
            if current_memory_query is not None: s.current_memory_query = current_memory_query
            s.memory_reads        += memory_reads_delta
            s.memory_writes       += memory_writes_delta
            s.artifacts_published += artifacts_delta
            s.tasks_completed     += tasks_delta

        await self._broadcast("agent_heartbeat", s.model_dump(mode="json"))
        return s

    async def unregister(self, agent_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(agent_id, None)
        if session:
            session.ended_at = datetime.utcnow()
            session.status   = "offline"
            await self._broadcast("agent_left", session.model_dump(mode="json"))

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_sessions(
        self, workspace_id: Optional[str] = None
    ) -> List[AgentSession]:
        sessions = list(self._sessions.values())
        if workspace_id:
            sessions = [s for s in sessions if s.workspace_id == workspace_id]
        return sessions

    def get_session(self, agent_id: str) -> Optional[AgentSession]:
        return self._sessions.get(agent_id)

    # ── Pub/sub ───────────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    async def _broadcast(self, event_type: str, data: dict) -> None:
        if not self._subscribers:
            return
        message = json.dumps({"type": event_type, **data})
        dead: list[Callable] = []
        for cb in list(self._subscribers):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(message)
                else:
                    cb(message)
            except Exception:
                dead.append(cb)
        for cb in dead:
            try:
                self._subscribers.remove(cb)
            except ValueError:
                pass


# ── Module-level singleton ────────────────────────────────────────────────────

_presence_store: Optional[PresenceStore] = None


def get_presence_store() -> PresenceStore:
    global _presence_store
    if _presence_store is None:
        _presence_store = PresenceStore()
    return _presence_store
