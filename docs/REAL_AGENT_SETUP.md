# Connecting a Real AI Agent to WalrusOS

This guide connects an **actual** external AI tool (Claude Code, Claude
Desktop, or Cursor) to WalrusOS — not a simulation. The connecting tool
runs as its own process, talks to the MCP server over stdio, and produces
memories on real Walrus + Sui that are visible live on the dashboard.

After completing the steps below you will see:

- the external tool appear as an **ONLINE** agent in the WalrusOS dashboard
- every memory the tool writes show up in the activity feed in real time
- each memory's blob ID resolvable on the Walrus aggregator
- each event anchored on Sui testnet, verifiable in Sui Explorer

---

## 1. Install

From the WalrusOS repo:

```powershell
pip install -e .
walrusos login
```

`walrusos login` configures the Sui wallet used to anchor events. If you
do not yet have a Sui keypair, the CLI walks you through creating one.

---

## 2. Start the dashboard so you can watch

In one terminal, start the bridge:

```powershell
python -m uvicorn dashboard.walrusos_bridge:app --port 8787
```

In a second terminal, start the Next.js dashboard:

```powershell
cd dashboard
npm run dev
```

Open <http://localhost:3000>. The presence panel will be empty — that is
expected. No agent is connected yet.

---

## 3. Connect Claude Code

Write the MCP config in one command:

```powershell
walrusos connect claude-code --write
```

This writes (or merges into) Claude Desktop's `claude_desktop_config.json`
with an entry like:

```json
{
  "mcpServers": {
    "walrusos": {
      "command": "walrusos",
      "args": ["mcp", "start"],
      "env": {
        "WALRUSOS_MCP_AGENT_NAME": "Claude Code",
        "WALRUSOS_MCP_FRAMEWORK":  "claude-code",
        "WALRUSOS_USE_MOCKS":      "0"
      }
    }
  }
}
```

The `env` block matters: it is how the MCP server knows which name and
framework to publish to the dashboard.

Now **restart Claude Code** so it picks up the new MCP server.

For Cursor:

```powershell
walrusos connect cursor --write
```

The same idea — Cursor reads `.cursor/mcp.json` from the project root.

---

## 4. Verify it is real

Inside Claude Code, ask it something like:

> Use the `memory_append` tool to save: "OAuth uses PKCE for security."

Claude Code calls the WalrusOS MCP tool. Now:

- **The dashboard:** "Claude Code" appears as an online agent. The
  activity feed shows a `write_memory` event with the preview you wrote.
- **Walrus:** the blob ID returned by `memory_append` is fetchable at
  <https://aggregator.walrus-testnet.walrus.space/v1/blobs/{blob_id}>
- **Sui:** the anchoring transaction is searchable in Sui Explorer
  (testnet) under the deployer wallet.

If you want a preflight check before connecting any tool, run:

```powershell
walrusos connect --verify
```

It reports:

```
✓ MCP server starts
✓ 10 tools registered
✓ Walrus reachable
✓ Sui CLI available
✓ Bridge reachable
```

If the bridge is offline you will see `! Bridge offline — dashboard won't
show presence` instead. Memory operations still work; only live presence
is gated on the bridge.

---

## 5. Prove persistence

Quit Claude Code. Reopen it. Ask in the new session:

> Use `memory_search` to find what we know about OAuth.

It retrieves the memory from the previous session. The memory lives on
Walrus, the ownership proof lives on Sui — nothing was kept locally.

This is the credibility check: a real third-party AI tool, persistent
memory, on-chain, recoverable, visible live.
