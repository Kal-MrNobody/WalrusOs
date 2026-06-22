# Connecting Real AI Agents to WalrusOS

WalrusOS works with any AI tool that supports MCP.
Install once, connect anywhere.

## Quick Setup (any MCP-compatible tool)

```bash
pip install walrusos
walrusos login
```

Add to your tool's MCP config:
```json
{
  "mcpServers": {
    "walrusos": {
      "command": "walrusos",
      "args": ["mcp", "start"]
    }
  }
}
```

That's it. Your AI tool now has:
- Persistent memory backed by Walrus
- Cryptographic identity on Sui
- Real-time collaboration with other agents
- Task coordination via shared queue

## Claude Code / Claude Desktop

Config location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/claude/claude_desktop_config.json`

Add:
```json
{
  "mcpServers": {
    "walrusos": {
      "command": "walrusos",
      "args": ["mcp", "start"],
      "env": {}
    }
  }
}
```

Available tools:
- `memory_search`  — search past decisions, implementations
- `memory_append`  — save findings and decisions
- `memory_latest`  — see recent activity
- `memory_context` — get formatted context for prompts
- `workspace_sync` — sync from Walrus on new machine
- `agent_status`   — see who's online
- `agent_discover` — find agents by capability
- `task_claim`     — pick up work from the queue
- `task_complete`  — mark work done

## Cursor

Config: `.cursor/mcp.json` in project root

```json
{
  "mcpServers": {
    "walrusos": {
      "command": "walrusos",
      "args": ["mcp", "start"]
    }
  }
}
```

## Windsurf

Same MCP config pattern as Cursor.

## Antigravity

Same MCP config pattern. Antigravity supports MCP servers natively.

## Gemini CLI

Gemini CLI supports MCP via `--mcp` flag.

## Programmatic Connection (Python SDK)

```python
from walrusos import WalrusOS
from walrusos.integrations.connect import connect_claude_code

os_instance = WalrusOS()
workspace = os_instance.workspace("my-project")

claude = await connect_claude_code(workspace)
# Claude is now online with code_generation, review, debugging capabilities

# Other agents can discover Claude:
reviewers = await workspace.discover(capability="code_review")
# Returns: [{"agent_name": "Claude Code", "framework": "claude-code", ...}]
```

## Running Multiple Agents Simultaneously

```
Terminal 1: Claude Code with WalrusOS MCP
Terminal 2: Cursor with WalrusOS MCP
Terminal 3: python scripts/demo_mesh.py (custom agents)
```

All three share the same workspace, same memory, same task queue.
Open `http://localhost:3000` to watch them collaborate live.

## Auto-generate configs

```bash
walrusos connect claude-code   # print + optionally write Claude Desktop config
walrusos connect cursor        # print + optionally write .cursor/mcp.json
walrusos connect --list        # list all supported frameworks
walrusos connect --verify      # verify MCP server + all 10 tools respond
```
