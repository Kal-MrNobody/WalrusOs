# Changelog

All notable changes to WalrusOS will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.1.0] — 2024-06-17

### 🎉 Initial Public Release

This is the inaugural release of WalrusOS — the decentralized AI memory infrastructure library.

### Added

#### Core Domain Layer
- `User`, `Workspace`, `Agent` identity models (Pydantic v2 + SQLModel)
- `MemoryStream`, `MemoryEvent`, `Checkpoint` memory models
- `Artifact`, `Capability`, `Permission`, `Subscription` models
- Full validation with Pydantic v2 validators and discriminated unions

#### Memory Engine
- Append-only DAG with parent-pointer lineage tracking
- `create_stream()`, `append()`, `read()`, `timeline()`, `replay()`
- `checkpoint()`, `fork()`, `merge()`, `snapshot()`, `resume()`
- `summarize()` for long-context compression
- `semantic_search()` via pluggable vector adapter
- Clean dependency inversion: engine knows nothing about Walrus or Sui

#### Walrus Storage Adapter
- AES-256-GCM encryption before upload
- zstd compression (up to 10x size reduction)
- Automatic chunking for blobs > 4MB
- tenacity retry with exponential backoff
- `upload_blob()`, `download_blob()`, `metadata()`, `version()`, `delete()`, `shred_key()`

#### Sui Identity Adapter
- Lazy pysui import with graceful fallback
- `SuiIdentityAdapter` for wallet login and workspace creation
- `SuiLedgerAdapter` implementing `LedgerAdapter` interface
- Move smart contracts: `walrusos::identity`, `walrusos::capability`
- Python PTB (Programmable Transaction Block) bindings

#### Public SDK (Firebase-like API)
- `WalrusOS(use_mocks=True)` for zero-config local development
- `runtime.workspace(name)` → `WorkspaceClient`
- `workspace.agent(name)` → `AgentClient`
- `workspace.stream(name)` → `StreamClient`
- `agent.publish(stream, payload)` → `MemoryEvent`
- `agent.subscribe(stream, callback)` → background `asyncio.Task`
- `stream.timeline()`, `stream.merge()`, `stream.fork()`

#### Framework Integrations
- **LangGraph**: `AsyncWalrusSaver` replacing `MemorySaver`
- **CrewAI**: `WalrusMemory` replacing `InMemory`
- **OpenAI Agents**: `WalrusConversationStore`
- **AutoGen**: `WalrusMessageStore`
- **LlamaIndex**: `WalrusChatStore` and `WalrusDocumentStore`

#### Dashboard
- Next.js 14 (App Router) with dark Tailwind theme
- 7 pages: Workspace Explorer, Agent Graph, Memory Timeline, Artifacts, Search, Permissions, Live Events
- React Flow interactive DAG visualizer
- WebSocket live event feed
- FastAPI bridge server (`dashboard/walrusos_bridge.py`)

#### CLI
- 11 commands: `init`, `login`, `status`, `workspace`, `agent`, `memory`, `replay`, `search`, `artifacts`, `permissions`, `events`, `logs`
- Rich terminal output with color-coded agents and streams
- Shell completion for Bash, Zsh, Fish, PowerShell
- `walrusos --install-completion`

#### Examples
- `01_research_team/` — Multi-agent shared memory
- `02_software_engineering/` — Fork/merge DAG
- `03_trading_team/` — Real-time pub/sub
- `04_customer_support/` — Semantic search
- `05_scientific_research/` — Checkpoint & crash recovery

#### Infrastructure
- `pyproject.toml` with `hatchling` build backend
- `ruff` linting + formatting (line-length: 100)
- `mypy` strict type checking
- `pytest-asyncio` with auto mode
- `pre-commit` hooks
- GitHub Actions CI: lint → type-check → test → coverage
- GitHub Actions Release: tag → build → publish to PyPI

### Performance (in-memory adapters, AMD Ryzen 7 5800X)

| Benchmark | Result |
|---|---|
| Memory append throughput | ~45,000 ops/sec |
| Cold startup time | < 120ms |
| Semantic search (1K events) | < 8ms p99 |
| Stream timeline (1K events) | < 2ms |

### Security

- AES-256-GCM encryption on all blobs before upload
- Sui Move capability contracts enforce per-stream access control
- `shred_key()` method for cryptographic "delete" (key destruction)
- No private keys ever transmitted or logged

---

## [Unreleased]

### Planned for v0.2.0
- Walrus mainnet integration
- MemoryStream encryption key rotation
- TypeScript SDK
- Multi-region replication
- OpenTelemetry tracing

---

[0.1.0]: https://github.com/walrusos/walrusos/releases/tag/v0.1.0
