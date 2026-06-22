"""
AgentRegistry — capability-based agent discovery.

Agents register their capabilities on go_online() and can be discovered
by other agents or the dashboard. In-process singleton, not persisted.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field


class AgentCapability(BaseModel):
    name: str
    languages: list[str] = Field(default_factory=list)
    description: str = ""


class AgentRegistration(BaseModel):
    agent_id:             str
    agent_name:           str
    framework:            str
    workspace_id:         str
    capabilities:         list[AgentCapability] = Field(default_factory=list)
    tools_exposed:        list[str]             = Field(default_factory=list)
    max_concurrent_tasks: int                   = 1


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}
        self._lock   = asyncio.Lock()

    async def register(self, registration: AgentRegistration) -> None:
        async with self._lock:
            self._agents[registration.agent_id] = registration

    async def unregister(self, agent_id: str) -> None:
        async with self._lock:
            self._agents.pop(agent_id, None)

    def find_by_capability(self, capability_name: str) -> list[AgentRegistration]:
        return [
            a for a in self._agents.values()
            if any(c.name == capability_name for c in a.capabilities)
        ]

    def find_by_framework(self, framework: str) -> list[AgentRegistration]:
        return [
            a for a in self._agents.values()
            if a.framework == framework
        ]

    def list_all(self) -> list[AgentRegistration]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> Optional[AgentRegistration]:
        return self._agents.get(agent_id)


# ── Module-level singleton ─────────────────────────────────────────────────────

_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
