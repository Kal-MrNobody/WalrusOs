# API Reference

Complete reference for the WalrusOS Python SDK.

---

## WalrusOS

The top-level runtime. Start here.

```python
from walrusos import WalrusOS

runtime = WalrusOS(
    use_mocks=False,         # True for local testing (no network)
    publisher_url=None,      # Walrus publisher URL (default: testnet)
    aggregator_url=None,     # Walrus aggregator URL (default: testnet)
    walrus_epochs=5,         # How long to store blobs (1 epoch ≈ 1 day on testnet)
    sui_rpc_url=None,        # Sui RPC URL (default: testnet)
    package_id=None,         # Deployed WalrusOS Move package ID
    db_path=None,            # SQLite database path (default: ~/.walrusos/walrusos.db)
)
```

**Configuration priority** (highest to lowest):

1. Constructor arguments
2. Environment variables (`WALRUSOS_*`)
3. Config file (`~/.walrusos/config.json`)
4. Built-in defaults (testnet)

### Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WALRUSOS_KEY_PASSWORD` | Password for key encryption. **Set this in production.** | Machine-derived |
| `WALRUSOS_MACHINE_SECRET` | Secondary key derivation input | Auto-generated |
| `WALRUSOS_USE_MOCKS` | `1` to enable mock mode | `0` |
| `WALRUSOS_PUBLISHER_URL` | Walrus publisher endpoint | Testnet |
| `WALRUSOS_AGGREGATOR_URL` | Walrus aggregator endpoint | Testnet |
| `WALRUSOS_PACKAGE_ID` | Deployed Move package ID | None |
| `WALRUSOS_DB_PATH` | SQLite database path | `~/.walrusos/walrusos.db` |

### `WalrusOS.workspace(name)`

Open a workspace. Creates it if it doesn't exist.

```python
workspace = runtime.workspace("research")
```

Returns: [`WorkspaceClient`](#workspaceclient)

---

## WorkspaceClient

A workspace groups agents and streams. Equivalent to a project or repository.

### `workspace.agent(name)`

Get or create an agent within the workspace.

```python
agent = workspace.agent("Researcher")
```

Returns: [`AgentClient`](#agentclient)

The agent is created on first use. Calling `workspace.agent("Researcher")` again returns the same agent — agents are identified by name, not by object reference.

### `workspace.stream(name)`

Get or create a workspace-level stream. Any agent in the workspace can write to it.

```python
stream = workspace.stream("shared-notes")
```

Returns: [`StreamClient`](#streamclient)

### `workspace.grant(from_agent, to_agent, capability, stream)`

Grant a capability from one agent to another.

```python
await workspace.grant(
    from_agent=researcher,
    to_agent=reviewer,
    capability="read",   # "read" | "write" | "fork" | "merge"
    stream=researcher.stream("findings"),
)
```

### `workspace.revoke(from_agent, to_agent, capability, stream)`

Revoke a previously granted capability.

```python
await workspace.revoke(
    from_agent=researcher,
    to_agent=reviewer,
    capability="read",
    stream=researcher.stream("findings"),
)
```

---

## AgentClient

An agent is a named identity that can read and write streams.

### `agent.stream(name)`

Get or create a stream owned by this agent.

```python
stream = agent.stream("scratchpad")
```

Returns: [`StreamClient`](#streamclient)

### `agent.publish(stream, payload, memory_type="episodic")`

Append an event to a stream, signing it with the agent's key.

```python
event = await agent.publish(stream, {
    "thought": "The model is converging.",
    "step": 42,
})
```

Returns: [`MemoryEvent`](#memoryevent)

### `agent.subscribe(stream, callback)`

Subscribe to new events on a stream. Calls `callback(payload)` for each new event.

```python
async def on_event(payload):
    print(f"New: {payload}")

task = await agent.subscribe(stream, on_event)
# Later:
task.cancel()
```

Returns: `asyncio.Task` — cancel to unsubscribe.

### `agent.search(stream, query, limit=10)`

Semantic search over a stream's events.

```python
results = await agent.search(stream, "attention mechanism", limit=5)
for payload, score in results:
    print(f"[{score:.2f}] {payload}")
```

Returns: `List[Tuple[dict, float]]` — (payload, similarity score)

### Agent properties

```python
agent.agent_id      # str — deterministic UUID5
agent.agent_name    # str — the name you passed to workspace.agent()
agent.workspace_id  # str — parent workspace UUID
agent.trust_root    # str — rolling SHA-256 fingerprint
agent.public_key    # str — Ed25519 public key (hex)
agent.capabilities  # List[str] — ["read", "write", "fork", "merge"]
agent.reputation    # AgentReputation — counters for trust graph metrics
```

---

## StreamClient

A stream is an ordered, append-only sequence of memory events.

### `stream.append(payload, memory_type="episodic")`

Append a new memory event to the stream.

```python
event = await stream.append({
    "thought": "The embedding space clusters topics naturally.",
    "confidence": 0.87,
})
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `payload` | `dict` | Any JSON-serializable dictionary |
| `memory_type` | `str` | `"semantic"` \| `"episodic"` \| `"procedural"` \| `"working"` \| `"system"` |

Returns: [`MemoryEvent`](#memoryevent)

### `stream.timeline()`

Read the full ordered history of events.

```python
timeline = await stream.timeline()
for event, payload in timeline:
    print(f"[{event.timestamp}] {payload}")
```

Returns: `List[Tuple[MemoryEvent, dict]]` — (event metadata, payload dict)

### `stream.replay(until_event=None, until_timestamp=None)`

Replay events up to a point in history. See [Recovery & Replay](recovery.md).

```python
# All events up to a specific event
past = await stream.replay(until_event="a3f8b2...")

# All events that existed at a timestamp
past = await stream.replay(until_timestamp="2026-06-01T12:00:00Z")
```

Returns: `List[Tuple[MemoryEvent, dict]]`

### `stream.search(query, limit=10)`

Semantic search over the stream's events.

```python
results = await stream.search("transformer architecture", limit=5)
for payload, score in results:
    print(f"Score {score:.2f}: {payload}")
```

Returns: `List[Tuple[dict, float]]`

### `stream.fork()`

Create a branch of this stream. See [Recovery & Replay — Branching](recovery.md#branching).

```python
fork_id = await stream.fork()
```

Returns: `str` — the new stream's ID

### `stream.merge(fork_stream_id)`

Merge a fork back into this stream.

```python
await stream.merge(fork_id)
```

### `stream.snapshot()`

Create a point-in-time snapshot of the stream.

```python
snapshot_blob_id = await stream.snapshot()
```

Returns: `str` — Walrus blob ID of the snapshot

### `stream.list_checkpoints()`

List all checkpoints in the stream.

```python
checkpoints = await stream.list_checkpoints()
# [{"checkpoint_id": "cp_001", "event_id": "abc...", "timestamp": "..."}]
```

Returns: `List[dict]`

### Stream properties

```python
stream.stream_id    # uuid.UUID
stream.stream_name  # str
```

---

## MemoryEvent

The return type of `stream.append()` and the first element of `stream.timeline()` tuples.

```python
event.event_id      # str  — SHA-256 content hash (unique, deterministic)
event.timestamp     # str  — ISO 8601 UTC timestamp
event.blob_id       # str  — Walrus blob ID
event.blob_hash     # str  — SHA-256 of the payload
event.signature     # str  — Ed25519 signature (base64)
event.parent_id     # str  — previous event's ID, or "genesis"
event.agent_id      # str  — UUID of the writing agent (if available)
event.workspace_id  # str  — UUID of the workspace
```

---

## Exceptions

| Exception | When it's raised |
|-----------|-----------------|
| `WalrusConnectionError` | Cannot reach the Walrus network |
| `WalrusKeyDestroyedError` | `shred_key()` was called; decryption impossible |
| `CryptographicVerificationError` | Event signature or hash check failed |
| `PermissionError` | Agent lacks the required capability |
| `StreamNotFoundError` | Stream ID doesn't exist in the ledger |

```python
from walrusos.adapters.walrus import WalrusConnectionError, WalrusKeyDestroyedError
from walrusos.engine.replay import CryptographicVerificationError

try:
    event = await stream.append(payload)
except WalrusConnectionError as e:
    print(f"Network error: {e}")
    # Data is queued locally and will be retried
```

---

## CLI Reference

```bash
walrusos --help
```

### Commands

| Command | Description |
|---------|-------------|
| `walrusos init` | Initialize a workspace config |
| `walrusos login` | Connect a Sui wallet |
| `walrusos agent publish` | Publish a memory event |
| `walrusos replay` | Replay a stream's history |
| `walrusos search` | Semantic search over a stream |
| `walrusos events` | Live event stream |
| `walrusos recover` | Disaster recovery from network |
| `walrusos snapshot` | Create a stream snapshot |
| `walrusos fork` | Fork a stream |
| `walrusos merge` | Merge a forked stream |

### `walrusos init`

```bash
walrusos init \
  --workspace research \
  --network testnet    # testnet | mainnet
```

### `walrusos agent publish`

```bash
walrusos agent publish \
  Researcher \
  findings \
  --payload '{"insight": "Transformers scale well."}'
```

### `walrusos replay`

```bash
walrusos replay findings
walrusos replay findings --until-event abc123...
walrusos replay findings --until-timestamp 2026-06-01T12:00:00Z
walrusos replay findings --speed 2.0   # playback speed multiplier
```

### `walrusos search`

```bash
walrusos search findings "attention mechanism"
walrusos search findings "attention mechanism" --limit 5
```

### `walrusos recover`

```bash
walrusos recover --workspace research
# Reconstructs from Sui + Walrus — can take minutes for large streams
```

---

## Advanced: Engine API

For low-level control, bypass the SDK and use the engine directly.

```python
from walrusos.engine.memory import MemoryEngine
from walrusos.adapters.in_memory import InMemoryLedger, InMemoryStorage, InMemoryVector
import uuid

engine    = MemoryEngine(InMemoryLedger(), InMemoryStorage(), InMemoryVector())
agent_id  = uuid.uuid4()
stream_id = await engine.create_stream(agent_id)

event = await engine.append(stream_id, "semantic", {
    "fact": "The attention mechanism was introduced in 2015.",
})

timeline = await engine.timeline(stream_id)
```

The engine API is stable but lower-level. Prefer `WalrusOS` → `workspace()` → `agent()` → `stream()` for most use cases.
