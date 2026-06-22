# Migration Guide

This guide covers breaking changes between WalrusOS versions and how to update your code.

---

## Migrating to v0.1 from pre-release

v0.1 is the first stable release. If you were using a pre-release version, this guide covers everything that changed.

### Summary of breaking changes

| Area | Change |
|------|--------|
| Entry point | `from walrusos.client import WalrusOS` → `from walrusos import WalrusOS` |
| Stream append | `engine.append(stream_id, class_type, dict)` → `stream.append(dict)` |
| Agent creation | Manual UUID management → `workspace.agent("Name")` |
| Framework adapters | Split imports → unified `walrusos.integrations.*` |
| CLI | Removed experimental flags |

---

## Entry point

**Before:**

```python
from walrusos.client import WalrusOS
```

**After:**

```python
from walrusos import WalrusOS
```

Both still work — the old import path is kept for backward compatibility — but the new path is preferred.

---

## Stream API

The engine-level API still works but is now considered low-level. The SDK API is the recommended interface.

**Before (low-level engine):**

```python
import uuid
from walrusos.engine.memory import MemoryEngine
from walrusos.adapters.in_memory import InMemoryLedger, InMemoryStorage, InMemoryVector

engine    = MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())
agent_id  = uuid.uuid4()
stream_id = await engine.create_stream(agent_id)
event     = await engine.append(stream_id, "episodic", {"message": "hello"})
timeline  = await engine.timeline(stream_id)
```

**After (SDK):**

```python
from walrusos import WalrusOS

runtime = WalrusOS(use_mocks=True)
agent   = runtime.workspace("myapp").agent("MyAgent")
stream  = agent.stream("memory")
event   = await stream.append({"message": "hello"})
timeline = await stream.timeline()
```

The low-level engine API is unchanged and still works. You can mix both.

---

## Memory type enum

**Before:**

```python
event = await engine.append(stream_id, "working", payload)   # string literal
```

**After:**

```python
event = await stream.append(payload, memory_type="working")  # keyword arg
```

Valid values: `"semantic"`, `"episodic"`, `"procedural"`, `"working"`, `"system"`

---

## Framework integrations

### LangGraph

**Before:**

```python
from walrusos.adapters.langgraph import WalrusSaver
saver = WalrusSaver(stream_id, engine)
```

**After:**

```python
from walrusos.integrations.langgraph import AsyncWalrusSaver
saver = AsyncWalrusSaver(stream)   # takes a StreamClient
```

### CrewAI

**Before:**

```python
from walrusos.crew import WalrusMemoryStore
memory = WalrusMemoryStore(engine, stream_id)
```

**After:**

```python
from walrusos.integrations.crewai import WalrusMemory
memory = WalrusMemory(stream)   # takes a StreamClient
```

---

## Configuration

**Before (constructor keyword arguments only):**

```python
runtime = WalrusOS(walrus_publisher="...", walrus_aggregator="...")
```

**After (env vars, config file, or constructor — highest priority wins):**

```python
# Option 1: env vars
export WALRUSOS_KEY_PASSWORD=...
export WALRUSOS_PUBLISHER_URL=...

# Option 2: config file at ~/.walrusos/config.json
{
  "publisher_url": "...",
  "aggregator_url": "..."
}

# Option 3: constructor (same as before)
runtime = WalrusOS(publisher_url="...", aggregator_url="...")
```

---

## Event model

`ProtocolEvent.blob_id` used to be `ProtocolEvent.content_blob_id` in pre-release. If you have existing code accessing this field directly:

**Before:**

```python
event.content_blob_id
```

**After:**

```python
event.blob_id
```

`MemoryEvent.id` is now `MemoryEvent.event_id` in the protocol layer. The `id` attribute still exists for backward compatibility.

---

## Signature format

Pre-release versions used hex-encoded signatures. v0.1 uses base64-encoded signatures to save space.

If you have stored signatures in hex format, convert them:

```python
import base64

hex_sig = "deadbeef..."
b64_sig = base64.b64encode(bytes.fromhex(hex_sig)).decode()
```

Events with hex signatures are accepted during replay if they carry the `"v0_migration"` signature marker — this marker skips verification.

---

## CLI

The CLI was rewritten in v0.1. If you had scripts using the pre-release CLI, update them:

| Pre-release | v0.1 |
|-------------|------|
| `walrusos --append` | `walrusos agent publish` |
| `walrusos --read` | `walrusos replay` |
| `walrusos --list-streams` | `walrusos events` |

---

## Database migration

v0.1 adds several new columns to the SQLite schema. The database is migrated automatically on first use. No action required.

If you need to reset the database:

```bash
rm ~/.walrusos/walrusos.db
walrusos init --workspace your-workspace
```

> ⚠️ This deletes your local event index. If you have a Sui wallet connected, you can recover with `walrusos recover`.

---

## v0.2 preview

The following changes are planned for v0.2 and may require migration:

- **Encryption key rotation API** — new `stream.rekey()` method to re-encrypt existing blobs
- **TypeScript SDK** — compatible wire format, no Python changes required
- **Mainnet integration** — new `network="mainnet"` config option
- **Streaming reads** — `stream.stream_timeline()` async generator for large streams

No breaking changes are planned for the v0.1 → v0.2 upgrade path.
