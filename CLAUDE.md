# WalrusOS — Project Context for Claude Code

## What This Is
WalrusOS is a persistent memory runtime for autonomous AI agents.
Agents register on-chain identities via Sui, sign memory with Ed25519 keys,
store compressed blobs on Walrus, and recover complete state from the network
alone — no central server, no local database required.

## Live Infrastructure
- **Package ID**: `0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8`
- **LedgerAnchor**: `0x0f96188ee403ecc58bd498fb874ef3037078775deb68e2061964ac1d3827e27d`
- **Workspace**: `0x3e315db3dad1cc8bb38d3a92db3324040d87235ff4b25d55848b140ded495092`
- **Network**: Sui Testnet
- **Deployer wallet**: `0x114702611c4e6411af933347f2268b32f286af5a05478af8516e670aeb756de1`

## Completed Phases
- **Phase 1 — Memory Intelligence**: search, summarizer, context builder, embeddings
- **Phase 2 — Multi-Agent Runtime**: event bus, subscriptions, tasks, pipeline/broadcast/consensus, workspace.sync()
- **Phase 3 — MCP Server**: 7 tools, walrusos mcp start, Claude Desktop config docs

## Architecture
- `walrusos/adapters/` — `walrus_real.py` (httpx to Walrus), `sui_real.py` (subprocess sui CLI), `sqlite_ledger.py` (local cache/index), `key_store.py` (Ed25519 key encryption)
- `walrusos/sdk/` — `agent.py`, `stream.py`, `workspace.py`, `task.py` (developer-facing API)
- `walrusos/engine/` — `memory.py`, `search.py`, `summarizer.py`, `context.py`, `recovery.py`, `time_travel.py`
- `walrusos/runtime/` — `event_bus.py`, `collaboration.py` (Pipeline, Broadcast, Consensus)
- `walrusos/integrations/` — `langgraph.py`, `crewai.py`, `autogen.py`, `llamaindex.py`, `openai.py`, `pydantic_ai.py`
- `walrusos/mcp/` — `server.py`, `config.py` (MCP stdio server, 7 tools)
- `walrusos/core/` — `models/` (MemoryEvent, AgentIdentity, Workspace, Task domain objects)
- `walrusos/cli/` — `cmd_*.py` (Typer CLI commands)
- `move/walrusos/` — `identity.move`, `memory.move`, `protocol.move` (deployed Move contracts)
- `dashboard/` — Next.js dashboard (needs Phase 4 completion)
- `scripts/` — `demo_recovery.py`, `demo_migration.py`, `deploy_contracts.sh`
- `tests/` — unit tests (mocked), integration tests (real network)

## What Needs Building Next
- **Phase 4 — Dashboard** (Next.js, GitHub meets Linear aesthetic)
- **Phase 5 — PyPI packaging** (`pip install walrusos`)
- **Phase 6 — Multi-machine migration** (`workspace.export_config()`, delegated execution keys)

## Key Design Decisions
- **SQLite is cache only**. Walrus is source of truth for content. Sui is source of truth for ownership.
- All Sui calls go through subprocess `sui` CLI (not pysui) — avoids dependency conflicts
- Walrus calls use `httpx` async — publisher for upload, aggregator for download
- Ed25519 signing on every memory event — verified on recovery
- Event sourcing: state is always a projection of immutable protocol events
- MCP server uses stdio transport — works with Claude Desktop, Cursor, Windsurf

## Running Tests
```powershell
$env:WALRUSOS_USE_MOCKS="1"
python -m pytest tests/ --ignore=tests/integration -v
```

## Running the Full Demo
```powershell
python scripts/demo_recovery.py
```

## Running the MCP Server
```powershell
walrusos mcp start
```

## Important Files to Read First
- `walrusos/client.py` — WalrusOS main class, entry point
- `walrusos/sdk/agent.py` — AgentClient, the primary developer interface
- `walrusos/adapters/walrus_real.py` — real Walrus HTTP calls
- `walrusos/adapters/sui_real.py` — real Sui PTB execution
- `move/walrusos/sources/protocol.move` — on-chain event structure

## Current Test Status
- All unit tests pass with `WALRUSOS_USE_MOCKS=1`
- Integration tests require `SUI_INTEGRATION=1` and `WALRUS_INTEGRATION=1`

## Hackathon Submission
- **Sui Overflow 2025 — Walrus Track**
- **Deadline**: [check hackathon page]
- **Submission needs**: GitHub repo, demo video, deployed package ID
