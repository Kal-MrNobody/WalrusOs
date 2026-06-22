# FAQ

---

## General

### What is WalrusOS?

WalrusOS is a Python library that gives AI agents durable, append-only memory. Your agents can write memory events that survive crashes, are cryptographically verifiable, can be replayed in time, and can be shared between multiple agents — without any central server.

Think of it as Git for AI memory: every write is a commit, every stream is a branch, and you can always recover the full history.

### Who is it for?

AI engineers building systems with LangGraph, CrewAI, AutoGen, OpenAI Agents, LlamaIndex, PydanticAI, or custom agent frameworks who need their agents to have persistent, auditable memory.

You don't need to know anything about blockchains to use WalrusOS.

### Do I need a blockchain wallet?

No. WalrusOS works without a Sui wallet. In that mode:

- Your data is stored on the Walrus network (encrypted)
- Events are indexed locally in SQLite
- There's no on-chain anchoring

A Sui wallet adds on-chain tamper evidence and capability tokens. It's optional.

### Do I need a Walrus account?

No. The Walrus testnet is public and free. You can upload blobs to it with no account.

For mainnet, Walrus has its own staking and storage economics — check [walrus.xyz](https://walrus.xyz) for details.

### Is my data private?

Yes. All data is encrypted with AES-256-GCM before it leaves your machine. The Walrus network stores ciphertext only. Your `WALRUSOS_KEY_PASSWORD` is the only way to decrypt it.

---

## Getting started

### How do I run it without a network connection?

```python
runtime = WalrusOS(use_mocks=True)
```

This runs entirely in-process with no network calls. It's also how you should run tests.

### Where does my data go?

| Mode | Data location |
|------|--------------|
| `use_mocks=True` | In-process memory — gone when the process exits |
| Production (no Sui) | SQLite (local) + Walrus (encrypted, network) |
| Production (with Sui) | SQLite + Walrus + Sui event log |

### How do I set up production storage?

```bash
export WALRUSOS_KEY_PASSWORD="a-strong-passphrase"
```

Then use `WalrusOS()` without `use_mocks=True`. Data is automatically written to the Walrus testnet.

For mainnet:

```python
runtime = WalrusOS(
    publisher_url="https://publisher.walrus.space",
    aggregator_url="https://aggregator.walrus.space",
)
```

### How do I use it in tests?

```python
import pytest
from walrusos import WalrusOS

@pytest.fixture
def runtime():
    return WalrusOS(use_mocks=True)   # fresh in-memory state per test

@pytest.mark.asyncio
async def test_agent_memory(runtime):
    agent  = runtime.workspace("test").agent("Agent")
    stream = agent.stream("memory")
    event  = await stream.append({"msg": "hello"})
    assert event.event_id is not None
```

---

## Memory and streams

### What's the difference between a workspace stream and an agent stream?

```python
# Workspace stream — any agent in the workspace can write
stream = workspace.stream("shared-notes")

# Agent stream — conceptually private to one agent
stream = agent.stream("scratchpad")
```

Technically both are the same `StreamClient`. The distinction is organizational. All agents in a workspace can read and write any stream in that workspace (subject to capability checks if Sui is connected).

### How large can a payload be?

There's no hard limit. Large payloads are chunked automatically by the Walrus adapter. In practice, keep payloads under 10MB for reasonable performance. For larger files, store them in Walrus directly and put the blob ID in the payload.

### Can I delete a memory event?

No. Streams are append-only. You can "logically delete" by appending a deletion marker:

```python
await stream.append({
    "type": "delete",
    "deletes_event": original_event_id,
    "reason": "outdated",
})
```

Your application is responsible for checking for deletion markers during replay.

For actual data destruction, use `shred_key()` to cryptographically erase the DEK — all blobs encrypted with that key become unreadable.

### How do I get the 10 most recent events?

```python
timeline = await stream.timeline()
recent = timeline[-10:]   # last 10
```

Or use semantic search if you're looking for specific content:

```python
results = await stream.search("query text", limit=10)
```

### Can multiple agents write to the same stream simultaneously?

Yes. Concurrent writes are safe. Each write is atomic (SQLite transaction). The ordering is determined by wall-clock time — the SQLite `epoch_counter` is incremented atomically.

### What are memory types for?

Memory types (`semantic`, `episodic`, `procedural`, `working`, `system`) are metadata — they help you organize and filter events during replay. WalrusOS doesn't treat them differently at the storage layer.

Use them however makes sense for your application.

---

## Framework integrations

### Does WalrusOS work with LangGraph's async graph?

Yes. `AsyncWalrusSaver` is fully async and implements `BaseCheckpointSaver`.

### My LangGraph graph was using `MemorySaver`. Will my existing checkpoints be lost?

Yes — if you switch from `MemorySaver` (in-process) to `AsyncWalrusSaver`, existing in-memory checkpoints are not migrated. Start fresh, or export your `MemorySaver` state and import it into WalrusOS.

### Does WalrusOS work with synchronous frameworks?

The SDK is async (`async/await`). For synchronous contexts:

```python
import asyncio

async def _append(payload):
    return await stream.append(payload)

# In sync code
event = asyncio.run(_append({"message": "hello"}))
```

---

## Performance

### How fast is it?

| Mode | Append throughput | Read latency |
|------|-------------------|--------------|
| `use_mocks=True` | ~45,000/sec | < 1ms |
| SQLite-only (no Walrus) | ~5,000/sec | < 2ms |
| With Walrus (testnet) | ~5/sec (network-bound) | ~200ms p50 |

The bottleneck in production is the Walrus HTTP round-trip (upload per event). This is being addressed in future versions with batching.

### How do I make reads faster?

Reads fetch blobs from Walrus on each `timeline()` call. To speed up reads:

- Cache results in your application
- Use `stream.search()` instead — it queries the local vector index, not Walrus
- Store only references (IDs, pointers) in WalrusOS and the actual data elsewhere

---

## Security

### What happens if I lose my `WALRUSOS_KEY_PASSWORD`?

Your data is permanently unrecoverable. There's no backdoor. Back up this password securely.

### What happens if I lose my local `walrusos.db`?

If you have a Sui wallet connected, run `walrusos recover` to rebuild from the blockchain + Walrus. If you don't, you lose your event index (but not your data — blobs remain in Walrus, just unindexed).

### Can WalrusOS be used without encryption?

Not with the default Walrus adapter. All blobs are encrypted before upload. You can bypass this by implementing a custom `StorageAdapter` that doesn't encrypt, but this is not recommended.

### Is the Sui wallet required for security?

No. Encryption is independent of Sui. Your data is always encrypted before leaving your machine. Sui adds:

- On-chain tamper evidence (anyone can verify your event log is unmodified)
- Capability-based access control enforced by smart contracts
- Recovery from blockchain event log

---

## Troubleshooting

### `WalrusConnectionError: Cannot reach publisher`

The Walrus testnet is temporarily unavailable. Try:

```bash
curl https://publisher.walrus-testnet.walrus.space/v1/status
```

If it's down, use `use_mocks=True` temporarily.

### `WalrusKeyDestroyedError`

`shred_key()` was called. The DEK is gone. Blobs encrypted with that key are permanently unreadable.

### `CryptographicVerificationError` during replay

An event's signature or hash doesn't match. This means the event was tampered with (or written with a different key). The event is dropped during replay.

### Events appear out of order

Events are ordered by `epoch_counter` (SQLite autoincrement). If two events have the same timestamp, their order depends on which arrived at SQLite first. This is correct behavior for concurrent writers.

### My LangGraph agent doesn't resume state after restart

Check that `thread_id` in your config matches across runs:

```python
config = {"configurable": {"thread_id": "my-session-1"}}   # must be consistent
result = await app.ainvoke(inputs, config=config)
```

Also verify `use_mocks=True` is not set — mock mode doesn't persist across process restarts.
