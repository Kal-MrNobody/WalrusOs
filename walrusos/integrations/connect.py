"""
Framework-specific connection helpers.

Convenience functions that call go_online() with the right capabilities
for each supported AI tool, so callers don't need to remember the schema.

Usage::

    from walrusos.integrations.connect import connect_claude_code

    claude = await connect_claude_code(workspace)
    # Claude is now online with code_generation, review, debugging capabilities

    reviewers = await workspace.discover(capability="code_review")
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from walrusos.sdk.workspace import WorkspaceClient
    from walrusos.sdk.agent import AgentClient


async def connect_claude_code(
    workspace:  "WorkspaceClient",
    agent_name: str = "Claude Code",
    bridge_url: str = "http://localhost:8787",
) -> "AgentClient":
    """Connect Claude Code to a WalrusOS workspace."""
    agent = workspace.agent(agent_name)
    await agent.go_online(
        framework="claude-code",
        bridge_url=bridge_url,
        capabilities=[
            {"name": "code_generation", "languages": ["python", "typescript", "rust"]},
            {"name": "code_review"},
            {"name": "debugging"},
            {"name": "research"},
        ],
        tools=["memory_search", "memory_append", "memory_context",
               "task_claim", "task_complete", "agent_discover"],
    )
    return agent


async def connect_cursor(
    workspace:  "WorkspaceClient",
    agent_name: str = "Cursor",
    bridge_url: str = "http://localhost:8787",
) -> "AgentClient":
    """Connect Cursor to a WalrusOS workspace."""
    agent = workspace.agent(agent_name)
    await agent.go_online(
        framework="cursor",
        bridge_url=bridge_url,
        capabilities=[
            {"name": "code_generation", "languages": ["python", "typescript", "javascript"]},
            {"name": "code_review"},
            {"name": "file_editing"},
        ],
    )
    return agent


async def connect_gemini(
    workspace:  "WorkspaceClient",
    agent_name: str = "Gemini",
    bridge_url: str = "http://localhost:8787",
) -> "AgentClient":
    """Connect Gemini to a WalrusOS workspace."""
    agent = workspace.agent(agent_name)
    await agent.go_online(
        framework="gemini",
        bridge_url=bridge_url,
        capabilities=[
            {"name": "research"},
            {"name": "reasoning"},
            {"name": "code_generation", "languages": ["python", "java", "go"]},
        ],
    )
    return agent


async def connect_antigravity(
    workspace:  "WorkspaceClient",
    agent_name: str = "Antigravity",
    bridge_url: str = "http://localhost:8787",
) -> "AgentClient":
    """Connect Antigravity to a WalrusOS workspace."""
    agent = workspace.agent(agent_name)
    await agent.go_online(
        framework="antigravity",
        bridge_url=bridge_url,
        capabilities=[
            {"name": "code_generation"},
            {"name": "planning"},
            {"name": "architecture"},
        ],
    )
    return agent


async def connect_custom(
    workspace:    "WorkspaceClient",
    agent_name:   str,
    framework:    str = "custom",
    capabilities: Optional[list] = None,
    tools:        Optional[list] = None,
    bridge_url:   str = "http://localhost:8787",
) -> "AgentClient":
    """Connect any custom agent to a WalrusOS workspace."""
    agent = workspace.agent(agent_name)
    await agent.go_online(
        framework=framework,
        bridge_url=bridge_url,
        capabilities=capabilities or [],
        tools=tools or [],
    )
    return agent
