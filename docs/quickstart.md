# Quick Start

Get your first agent writing persistent memory in under 5 minutes.

---

## Install

```bash
pip install walrusos
```

WalrusOS requires Python 3.11 or later.

---

## Your first agent

This example runs entirely in memory — no Walrus account, no Sui wallet, no network.

```python
import asyncio
from walrusos import WalrusOS

async def main():
    # Start the runtime in mock mode (local, no network)
    runtime = WalrusOS(use_mocks=True)

    # Create a workspace and an agent
    agent  = runtime.workspace("research").agent("Researcher")
    stream = agent.stream("findings")

    # Write memory
    await stream.append({
        "insight": "Chain-of-thought prompting improves reasoning on math tasks.",
        "source":  "Wei et al. 2022",
        "confidence": 0.95,
    })

    # Read it back
    timeline = await stream.timeline()
    for event, payload in timeline:
        print(f"[{event.timestamp}] {payload['insight']}")

asyncio.run(main())
```

Run it:

```bash
python hello_agent.py
# [2026-06-17T...] Chain-of-thought prompting improves reasoning on math tasks.
```

Every event gets a permanent ID, a timestamp, a content hash, and a cryptographic signature — automatically.

---

## Connect to production storage

Switch from in-memory mocks to real persistent storage by removing `use_mocks=True`.

```python
runtime = WalrusOS()   # reads config from env vars or ~/.walrusos/config.json
```

Set your environment:

```bash
export WALRUSOS_KEY_PASSWORD="your-secret-passphrase"   # encrypts your data
```

That's it. Your data is now encrypted and stored on the [Walrus](https://walrus.xyz) decentralized network.

> **No Walrus account needed.** The testnet is public. Your data is encrypted before it leaves your machine.

---

## Connect a framework

### LangGraph

Replace LangGraph's default checkpointer with WalrusOS in two lines:

```python
from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver

runtime = WalrusOS()
memory  = AsyncWalrusSaver(runtime.workspace("my-app").stream("checkpoints"))
graph   = builder.compile(checkpointer=memory)
```

Your graph state now survives restarts, process crashes, and machine changes. [→ LangGraph integration](integrations.md#langgraph)

### CrewAI

```python
from walrusos import WalrusOS
from walrusos.integrations.crewai import WalrusMemory

memory = WalrusMemory(WalrusOS().workspace("crew").stream("episodes"))
crew   = Crew(agents=[...], tasks=[...], memory=True, embedder=memory)
```

[→ CrewAI integration](integrations.md#crewai)

---

## Multi-agent shared memory

Multiple agents reading and writing the same stream:

```python
async def main():
    runtime    = WalrusOS(use_mocks=True)
    workspace  = runtime.workspace("research-team")
    stream     = workspace.stream("shared-notes")

    researcher = workspace.agent("Researcher")
    writer     = workspace.agent("Writer")

    # Researcher writes
    await researcher.publish(stream, {
        "action":  "discovered",
        "title":   "Attention Is All You Need",
        "year":    2017,
    })

    # Writer reacts in real-time
    async def on_new_memory(payload):
        print(f"Writer sees: {payload['title']}")

    task = await writer.subscribe(stream, on_new_memory)

    # Both agents see the same timeline
    timeline = await stream.timeline()
    print(f"{len(timeline)} events in shared stream")

    task.cancel()
```

---

## CLI

```bash
# Initialize a workspace
walrusos init --workspace research --network testnet

# Publish a memory from the terminal
walrusos agent publish Researcher findings \
  --payload '{"insight": "LLMs compress world knowledge."}'

# Replay everything an agent did
walrusos replay findings

# Search memory semantically
walrusos search findings "transformer attention"

# Watch live events
walrusos events
```

---

## Next steps

- [**Concepts**](concepts.md) — understand Memory, Agents, Streams, and Trust
- [**Framework Integrations**](integrations.md) — LangGraph, CrewAI, AutoGen, and more
- [**Recovery & Replay**](recovery.md) — time travel, branching, crash recovery
- [**API Reference**](api-reference.md) — full SDK documentation
