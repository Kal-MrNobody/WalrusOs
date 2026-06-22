"""
walrusos mcp — MCP Server entry point.
"""
from __future__ import annotations

import asyncio
import sys
import typer
from rich.console import Console

from walrusos.cli._state import get_config

app = typer.Typer(help="Run the MCP Server.")
err_console = Console(stderr=True)

@app.command("start")
def start() -> None:
    """Start the MCP server on stdio."""
    err_console.print("WalrusOS MCP Server v0.1.0")
    ws_name = get_config("workspace", "default")
    net = get_config("network", "testnet")
    err_console.print(f"Workspace: {ws_name}")
    err_console.print(f"Network: {net}")
    err_console.print("Tools: memory_search, memory_append, memory_latest, memory_context, workspace_sync, agent_status, memory_timeline")
    err_console.print("Ready. Listening on stdio.")
    
    from walrusos.mcp.server import run_stdio_async
    asyncio.run(run_stdio_async())

@app.command("list-tools")
def list_tools() -> None:
    """List all available MCP tools."""
    from walrusos.mcp.server import list_tools as mcp_list_tools
    tools = asyncio.run(mcp_list_tools())
    for t in tools:
        print(f"- {t.name}: {t.description}")
