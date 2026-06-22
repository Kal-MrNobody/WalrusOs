<div align="center">

# WalrusOS 🦭

**Persistent, verifiable memory for AI agents.**

[![PyPI](https://img.shields.io/pypi/v/walrusos.svg)](https://pypi.org/project/walrusos/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen.svg)]()

[Docs](docs/) · [Quick Start](docs/quickstart.md) · [Examples](examples/) · [Discord](https://discord.gg/walrusos)

</div>

---

Your agents forget everything when they restart. WalrusOS fixes that.

WalrusOS is a Python library that gives your LangGraph, CrewAI, AutoGen, or custom agents **durable, append-only memory** that survives crashes, scales across machines, and can be replayed, branched, and recovered — exactly like Git.

```python
pip install walrusos
```

```python
from walrusos import WalrusOS

runtime   = WalrusOS(use_mocks=True)   # → WalrusOS() for production
workspace = runtime.workspace("research")
agent     = workspace.agent("Researcher")
stream    = agent.stream("findings")

await stream.append({"insight": "Transformers outperform RNNs on long contexts."})

timeline = await stream.timeline()   # every event, forever
```

**It takes five minutes to get started. [→ Quick Start](docs/quickstart.md)**

---

## Why WalrusOS?

| Problem | WalrusOS |
|---------|----------|
| Agent memory disappears on restart | Append-only stream persisted to decentralized storage |
| No audit trail for agent decisions | Every event is immutable, timestamped, and signed |
| Agents overwrite each other's state | Fork/merge semantics, one stream per agent |
| Hard to debug what an agent did | `stream.replay()` — deterministic event replay |
| No access control between agents | Capability tokens, on-chain permissions |
| Locked into one framework | Integrations for LangGraph, CrewAI, AutoGen, and more |

---

## Documentation

| | |
|--|--|
| [**Quick Start**](docs/quickstart.md) | Install, run your first agent in 5 minutes |
| [**Concepts**](docs/concepts.md) | Memory, Agents, Streams, Trust — how it works |
| [**Framework Integrations**](docs/integrations.md) | LangGraph, CrewAI, AutoGen, OpenAI, LlamaIndex, PydanticAI |
| [**API Reference**](docs/api-reference.md) | Complete Python SDK reference |
| [**Walrus & Sui**](docs/infrastructure.md) | The storage and identity layers explained |
| [**Recovery & Replay**](docs/recovery.md) | Time travel, branching, crash recovery |
| [**Architecture**](docs/architecture.md) | How everything fits together |
| [**FAQ**](docs/faq.md) | Common questions |
| [**Migration Guide**](docs/migration.md) | Upgrading from older versions |

---

## Framework Integrations

### LangGraph — 3 lines

```python
from walrusos.integrations.langgraph import AsyncWalrusSaver
from walrusos import WalrusOS

memory = AsyncWalrusSaver(WalrusOS().workspace("app").stream("checkpoints"))
graph  = builder.compile(checkpointer=memory)
```

### CrewAI — 2 lines

```python
from walrusos.integrations.crewai import WalrusMemory
memory = WalrusMemory(WalrusOS().workspace("crew").stream("episodes"))
```

### OpenAI Agents SDK — 2 lines

```python
from walrusos.integrations.openai import WalrusConversationStore
store = WalrusConversationStore(WalrusOS().workspace("app").stream("convos"))
```

---

## Performance

| Operation | Result |
|-----------|--------|
| Memory append (in-memory) | ~45,000 ops/sec |
| Memory append (Walrus testnet) | ~5 ops/sec (network-bound) |
| Semantic search (1K events) | < 8ms |
| Cold start | < 120ms |
| Crash recovery (1K events) | ~2s |

---

## License

MIT © 2024 WalrusOS Core Team — Built on [Sui](https://sui.io) and [Walrus](https://walrus.xyz)
