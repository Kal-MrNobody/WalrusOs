# WalrusOS Documentation

WalrusOS gives your AI agents **persistent, verifiable, replayable memory**.

---

## Start here

| | |
|--|--|
| [**Quick Start**](quickstart.md) | Install and run your first agent in 5 minutes |
| [**Concepts**](concepts.md) | Memory, Agents, Streams, Trust — the mental model |
| [**Examples**](examples.md) | Six complete, runnable examples |

---

## Guides

| | |
|--|--|
| [**Framework Integrations**](integrations.md) | LangGraph, CrewAI, AutoGen, OpenAI, LlamaIndex, PydanticAI |
| [**Recovery & Replay**](recovery.md) | Time travel, branching, crash recovery |
| [**Infrastructure**](infrastructure.md) | Walrus storage and Sui identity explained |
| [**Architecture**](architecture.md) | How WalrusOS works internally |

---

## Reference

| | |
|--|--|
| [**API Reference**](api-reference.md) | Complete SDK documentation |
| [**FAQ**](faq.md) | Common questions and troubleshooting |
| [**Migration Guide**](migration.md) | Upgrading from older versions |
| [**Security Policy**](../SECURITY.md) | Vulnerability reporting and security model |

---

## Key concepts in 30 seconds

```python
from walrusos import WalrusOS

runtime   = WalrusOS(use_mocks=True)       # in-memory for development
workspace = runtime.workspace("myapp")     # like a project
agent     = workspace.agent("MyAgent")     # named identity with a key pair
stream    = agent.stream("memory")         # append-only event log

await stream.append({"thought": "..."})    # signed, hashed, encrypted, stored
timeline = await stream.timeline()         # read it back, always
results  = await stream.search("query")    # semantic search
fork_id  = await stream.fork()             # branch the timeline
```

That's 95% of the API.
