# WalrusOS MCP Setup

WalrusOS works with any AI tool that supports the Model Context Protocol (MCP).
Install once, connect anywhere.

## Quick Install

```bash
pip install walrusos
walrusos login
```

## Claude Desktop / Claude Code

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

Or auto-generate:
```bash
walrusos connect claude-code
```

Restart Claude Desktop. You will see WalrusOS tools in the tool picker.

## Cursor

Add to `.cursor/mcp.json` in your project root:
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

Or auto-generate:
```bash
walrusos connect cursor
```

## Windsurf / VS Code

Same pattern as Cursor — refer to your editor's MCP documentation.
The command is always: `walrusos mcp start`

## Gemini CLI

```bash
gemini --mcp walrusos mcp start
```

## Available Tools (10 total)

| Tool | Description |
|------|-------------|
| `memory_search` | Semantic search across all agent memories |
| `memory_append` | Save a finding, decision, or output |
| `memory_latest` | Get the most recent memories |
| `memory_context` | Build a formatted context block for prompts |
| `memory_timeline` | Events from a specific time window |
| `workspace_sync` | Sync from Walrus on a new machine |
| `agent_status` | List agents and their activity stats |
| `task_claim` | Claim the next pending task from the queue |
| `task_complete` | Mark a claimed task as done |
| `agent_discover` | Find online agents by capability or framework |

## Testing the MCP server

```bash
walrusos connect --verify
```

Should confirm all 10 tools respond. If it does, the server is ready.

## Listing supported frameworks

```bash
walrusos connect --list
```
