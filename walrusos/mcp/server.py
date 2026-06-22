"""
MCP stdio server for WalrusOS.
"""
import asyncio
import os
import sys
import uuid
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from walrusos.mcp.config import MCPConfig
from walrusos.engine.search import MemorySearch
from walrusos.core.models.memory import MemoryEvent

app = Server("walrusos")

# We hold a global runtime initialized on startup
config = MCPConfig.load()
runtime = config.get_runtime()
workspace = runtime.workspace(config.workspace_id)


# ── Real-agent presence (Sprint 7) ────────────────────────────────────────────
#
# When a real external AI tool (Claude Code, Cursor, …) launches this MCP
# server, it represents ONE agent: that tool itself. We register a presence
# session on the first tool call, send heartbeats every 10s, and end the
# session on shutdown — so the dashboard shows the real agent live.
#
# All bridge calls are best-effort: a presence failure must never break a
# tool call.

_BRIDGE_URL = os.environ.get("WALRUSOS_MCP_BRIDGE_URL", "http://localhost:8787")
_AGENT_NAME = os.environ.get("WALRUSOS_MCP_AGENT_NAME", "Claude Code")
_FRAMEWORK  = os.environ.get("WALRUSOS_MCP_FRAMEWORK",  "claude-code")
_AGENT_ID   = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                             f"mcp.{config.workspace_id}.{_AGENT_NAME}"))

_agent_state: Dict[str, Any] = {
    "registered":     False,
    "session_token":  None,
    "heartbeat_task": None,
    "register_lock":  None,
}


def _capabilities_for_framework(framework: str) -> list[dict]:
    """Map framework → default capabilities. Mirrors integrations/connect.py."""
    if framework == "claude-code":
        return [
            {"name": "code_generation"},
            {"name": "code_review"},
            {"name": "debugging"},
            {"name": "research"},
        ]
    if framework == "cursor":
        return [
            {"name": "code_generation"},
            {"name": "code_review"},
            {"name": "file_editing"},
        ]
    if framework == "gemini":
        return [{"name": "research"}, {"name": "reasoning"}, {"name": "code_generation"}]
    if framework == "antigravity":
        return [{"name": "code_generation"}, {"name": "planning"}, {"name": "architecture"}]
    return [{"name": "general"}]


_TOOLS_EXPOSED = [
    "memory_search", "memory_append", "memory_latest", "memory_context",
    "memory_timeline", "workspace_sync", "agent_status",
    "task_claim", "task_complete", "agent_discover",
]


async def _post_session_start() -> Optional[str]:
    """POST /agent/session/start. Returns session_token or None on failure."""
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{_BRIDGE_URL}/agent/session/start",
                json={
                    "agent_id":     _AGENT_ID,
                    "agent_name":   _AGENT_NAME,
                    "workspace_id": str(workspace.workspace_id),
                    "framework":    _FRAMEWORK,
                    "capabilities": _capabilities_for_framework(_FRAMEWORK),
                    "tools":        _TOOLS_EXPOSED,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("session_token", _AGENT_ID)
    except Exception:
        return None


async def _post_session_heartbeat(
    status: Optional[str] = None,
    memory_writes_delta: int = 0,
    memory_reads_delta: int  = 0,
    tasks_delta: int         = 0,
) -> None:
    """POST /agent/session/heartbeat. Silent on failure."""
    if not _agent_state.get("session_token"):
        return
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_BRIDGE_URL}/agent/session/heartbeat",
                json={
                    "session_token":       _agent_state["session_token"],
                    "agent_id":            _AGENT_ID,
                    "status":              status,
                    "memory_writes_delta": memory_writes_delta,
                    "memory_reads_delta":  memory_reads_delta,
                    "tasks_delta":         tasks_delta,
                },
            )
    except Exception:
        pass


async def _post_session_end() -> None:
    """POST /agent/session/end. Silent on failure."""
    if not _agent_state.get("session_token"):
        return
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_BRIDGE_URL}/agent/session/end",
                json={
                    "session_token": _agent_state["session_token"],
                    "agent_id":      _AGENT_ID,
                },
            )
    except Exception:
        pass


async def _heartbeat_loop() -> None:
    """Background: keepalive every 10s while server is alive."""
    while True:
        try:
            await asyncio.sleep(10)
            await _post_session_heartbeat()
        except asyncio.CancelledError:
            return
        except Exception:
            # Never let a heartbeat error kill the loop
            pass


async def _ensure_agent_session() -> None:
    """Register this MCP client as a live agent. Idempotent + safe under concurrency."""
    if _agent_state.get("registered"):
        return
    # Lock so concurrent first calls don't double-register
    if _agent_state.get("register_lock") is None:
        _agent_state["register_lock"] = asyncio.Lock()
    async with _agent_state["register_lock"]:
        if _agent_state.get("registered"):
            return
        token = await _post_session_start()
        # Even if bridge is offline, mark registered with a local token so
        # later tool calls don't keep retrying the start endpoint.
        _agent_state["session_token"] = token or _AGENT_ID
        _agent_state["registered"]    = True
        if token is not None:
            try:
                _agent_state["heartbeat_task"] = asyncio.create_task(_heartbeat_loop())
            except Exception:
                _agent_state["heartbeat_task"] = None


# Tool → (status, deltas) — drives the activity feed on the dashboard.
_TOOL_ACTIVITY: Dict[str, Dict[str, Any]] = {
    "memory_append":   {"status": "working",  "memory_writes_delta": 1},
    "memory_search":   {"status": "thinking", "memory_reads_delta":  1},
    "memory_context":  {"status": "thinking", "memory_reads_delta":  1},
    "memory_latest":   {"status": "thinking", "memory_reads_delta":  1},
    "memory_timeline": {"status": "thinking", "memory_reads_delta":  1},
    "task_claim":      {"status": "working"},
    "task_complete":   {"status": "idle",     "tasks_delta": 1},
    "workspace_sync":  {"status": "thinking"},
    "agent_status":    {"status": "idle"},
    "agent_discover":  {"status": "thinking"},
}


async def _report_activity(tool_name: str) -> None:
    """Send a heartbeat with status/delta appropriate to the tool just called."""
    info = _TOOL_ACTIVITY.get(tool_name)
    if not info:
        return
    await _post_session_heartbeat(**info)


async def _shutdown_agent_session() -> None:
    """End the session and cancel the heartbeat task. Idempotent."""
    task = _agent_state.get("heartbeat_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _agent_state["heartbeat_task"] = None
    await _post_session_end()
    _agent_state["session_token"] = None
    _agent_state["registered"]    = False

@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="memory_search",
            description="Search agent memory for relevant context. Use this when you need to find past decisions, implementations, or discussions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "stream": {"type": "string"},
                    "agent": {"type": "string"}
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="memory_append",
            description="Save a new memory to the workspace. Use this to persist important findings, decisions, or outputs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "stream": {"type": "string", "default": "default"},
                    "agent": {"type": "string", "default": "mcp-agent"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "number", "default": 0.5},
                    "memory_type": {"type": "string", "default": "observation"}
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="memory_latest",
            description="Get the most recent memories from the workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "default": 5},
                    "stream": {"type": "string"},
                    "agent": {"type": "string"}
                }
            }
        ),
        Tool(
            name="memory_context",
            description="Get a formatted memory context block ready to inject into your prompt. Respects token limits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_tokens": {"type": "integer", "default": 2000},
                    "stream": {"type": "string"}
                }
            }
        ),
        Tool(
            name="workspace_sync",
            description="Sync workspace state from Walrus and Sui. Call this on a new machine or after an outage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"}
                }
            }
        ),
        Tool(
            name="agent_status",
            description="List all agents in the workspace with their activity stats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string"}
                }
            }
        ),
        Tool(
            name="memory_timeline",
            description="Get memory events from a specific time window.",
            inputSchema={
                "type": "object",
                "properties": {
                    "hours_ago": {"type": "integer", "default": 24},
                    "stream": {"type": "string"},
                    "memory_type": {"type": "string"}
                }
            }
        ),
        Tool(
            name="task_claim",
            description="Claim the next pending task from the workspace queue. Call this to pick up work without manual coordination.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "default": "mcp-agent"}
                }
            }
        ),
        Tool(
            name="task_complete",
            description="Mark a claimed task as complete. Call this when you finish a task claimed via task_claim.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "notes":   {"type": "string", "default": ""}
                },
                "required": ["task_id"]
            }
        ),
        Tool(
            name="agent_discover",
            description="Find online agents by capability or framework. Use when you need help from another agent (e.g., find a code reviewer or researcher).",
            inputSchema={
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "description": "e.g. 'review', 'research', 'code_generation'"},
                    "framework":  {"type": "string", "description": "e.g. 'claude-code', 'cursor', 'gemini'"}
                }
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Best-effort presence reporting — never let it block or break the tool.
    try:
        await _ensure_agent_session()
        await _report_activity(name)
    except Exception:
        pass

    if name == "memory_search":
        query = arguments.get("query")
        limit = arguments.get("limit", 10)
        stream_name = arguments.get("stream")
        
        # If stream specified, search it. Otherwise we simulate workspace search via "default"
        s = workspace.stream(stream_name or "default")
        results = await MemorySearch(s._memory, s.stream_id).search(query, limit=limit)
            
        formatted = []
        for ev, payload in results:
            agent_name = ev.agent_id or "Unknown"
            ts = ev.timestamp or "Unknown time"
            content = payload.get("content", payload.get("msg", str(payload)))
            formatted.append(f"Agent: {agent_name}\nTime: {ts}\n{content}\n---")
            
        res_str = "\n".join(formatted) if formatted else "No results found."
        return [TextContent(type="text", text=res_str)]
        
    elif name == "memory_append":
        content = arguments.get("content")
        stream_name = arguments.get("stream", "default")
        agent_name = arguments.get("agent", "mcp-agent")
        tags = arguments.get("tags", [])
        importance = arguments.get("importance", 0.5)
        memory_type = arguments.get("memory_type", "observation")
        
        agent = workspace.agent(agent_name)
        stream = agent.stream(stream_name)
        
        ev = await stream.append(
            {"content": content}, 
            memory_type=memory_type, 
            tags=tags, 
            importance=importance
        )
        
        if getattr(runtime, "_use_mocks", False):
            return [TextContent(type="text", text=f"Saved. Blob: mock_blob_{ev.event_id[:8]} | Sui: mock_tx_{ev.event_id[:8]}")]
        return [TextContent(type="text", text=f"Saved. Blob: {ev.event_id} | Sui: {ev.event_id}")]
        
    elif name == "memory_latest":
        n = arguments.get("n", 5)
        stream_name = arguments.get("stream")
        
        s = workspace.stream(stream_name or "default")
        results = await MemorySearch(s._memory, s.stream_id).latest(n)
        
        formatted = []
        for ev, payload in results:
            agent_name = ev.agent_id or "Unknown"
            ts = ev.timestamp or "Unknown time"
            content = payload.get("content", payload.get("msg", str(payload)))
            formatted.append(f"Agent: {agent_name}\nTime: {ts}\n{content}\n---")
            
        res_str = "\n".join(formatted) if formatted else "No recent events."
        return [TextContent(type="text", text=res_str)]
        
    elif name == "memory_context":
        query = arguments.get("query", "")
        max_tokens = arguments.get("max_tokens", 2000)
        stream_name = arguments.get("stream", "default")
        
        agent = workspace.agent("mcp-agent")
        stream = agent.stream(stream_name)
        
        ctx = await agent.build_context(stream, query=query, max_tokens=max_tokens, strategy="smart")
        return [TextContent(type="text", text=ctx)]
        
    elif name == "workspace_sync":
        ws_id = arguments.get("workspace_id", config.workspace_id)
        ws = runtime.workspace(ws_id)
        res = await ws.sync()
        return [TextContent(type="text", text=f"Synced. New events: {res.events_added} | Downloaded: {res.bytes_downloaded} bytes | Time: {res.time_ms / 1000}s")]
        
    elif name == "agent_status":
        ledger = workspace._get_sqlite_ledger()
        if hasattr(ledger, "get_events_for_workspace"):
            events = await ledger.get_events_for_workspace(workspace.workspace_id)
        else:
            events = []
            
        from collections import defaultdict
        counts = defaultdict(int)
        last_active = {}
        for ev in events:
            a_id = ev.agent_id
            if not a_id: continue
            counts[a_id] += 1
            last_active[a_id] = ev.timestamp
            
        formatted = []
        for a_id, count in counts.items():
            la = last_active[a_id]
            formatted.append(f"Name: {a_id} | Events: {count} | Last active: {la} | Trust: 0xa3f...")
            
        res_str = "\n".join(formatted) if formatted else ""
        return [TextContent(type="text", text=res_str)]
        
    elif name == "memory_timeline":
        hours = arguments.get("hours_ago", 24)
        stream_name = arguments.get("stream", "default")
        
        s = workspace.stream(stream_name)
        results = await MemorySearch(s._memory, s.stream_id).latest(50)
        
        formatted = []
        for ev, payload in results:
            agent_name = ev.agent_id or "Unknown"
            ts = ev.timestamp or "Unknown time"
            content = payload.get("content", payload.get("msg", str(payload)))
            formatted.append(f"Agent: {agent_name}\nTime: {ts}\n{content}\n---")
            
        res_str = "\n".join(formatted) if formatted else "No events in timeline."
        return [TextContent(type="text", text=res_str)]

    elif name == "task_claim":
        agent_name = arguments.get("agent_name", "mcp-agent")
        ledger = workspace._get_sqlite_ledger()
        if not hasattr(ledger, "list_tasks"):
            return [TextContent(type="text", text="Task management not available.")]
        pending = ledger.list_tasks(workspace.workspace_id, status="pending")
        if not pending:
            return [TextContent(type="text", text="No pending tasks.")]
        task = pending[0]
        task.status = "in_progress"
        task.assigned_to = agent_name
        ledger.save_task(task)
        asyncio.create_task(runtime.event_mesh.emit(
            "task.claimed",
            {"task_id": task.task_id, "title": task.title, "agent_id": agent_name},
        ))
        return [TextContent(type="text", text=f"Claimed: {task.title} (task_id: {task.task_id})")]

    elif name == "task_complete":
        task_id = arguments.get("task_id")
        notes   = arguments.get("notes", "")
        ledger  = workspace._get_sqlite_ledger()
        if not hasattr(ledger, "get_task"):
            return [TextContent(type="text", text="Task management not available.")]
        task = ledger.get_task(task_id)
        if not task:
            return [TextContent(type="text", text=f"Task {task_id} not found.")]
        task.status = "done"
        if notes:
            task.description = (task.description or "") + f"\n\nCompletion notes: {notes}"
        ledger.save_task(task)
        asyncio.create_task(runtime.event_mesh.emit(
            "task.completed",
            {"task_id": task.task_id, "title": task.title},
        ))
        return [TextContent(type="text", text=f"Completed: {task.title}")]

    elif name == "agent_discover":
        capability = arguments.get("capability")
        framework  = arguments.get("framework")
        import httpx as _httpx
        try:
            params: dict = {}
            if capability:
                params["capability"] = capability
            if framework:
                params["framework"]  = framework
            async with _httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get("http://localhost:8787/agent/discover", params=params)
                agents = resp.json()
        except Exception:
            agents = []
        if not agents:
            q = capability or framework or "any"
            return [TextContent(type="text", text=f"No agents found matching '{q}'.")]
        lines = [f"Found {len(agents)} agent(s):"]
        for a in agents:
            caps = ", ".join(c.get("name", "") for c in a.get("capabilities", []))
            lines.append(f"  • {a['agent_name']} ({a['framework']}) — {caps or 'no capabilities listed'}")
        return [TextContent(type="text", text="\n".join(lines))]

    raise ValueError(f"Unknown tool: {name}")

async def run_stdio_async() -> None:
    # Try to register up-front so the dashboard sees the agent immediately,
    # even before the first tool call.
    try:
        await _ensure_agent_session()
    except Exception:
        pass
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        try:
            await _shutdown_agent_session()
        except Exception:
            pass
