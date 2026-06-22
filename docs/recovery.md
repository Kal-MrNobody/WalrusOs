# Recovery & Replay

WalrusOS is designed so that no failure is permanent. This page covers time travel, branching, and crash recovery.

---

## The core guarantee

> Every piece of memory WalrusOS has ever written can be recovered from the Walrus network and the Sui blockchain, even if your local machine is completely wiped.

This works because:

1. Every memory event is uploaded to **Walrus** (decentralized blob storage)
2. Every event's ID is anchored to the **Sui blockchain** as an immutable transaction
3. The blockchain acts as a tamper-evident index of all your data

Recovery means: download the event index from Sui, fetch the blobs from Walrus, and rebuild.

---

## Replay

Replay lets you reconstruct state at any point in history.

### Replay the full stream

```python
timeline = await stream.timeline()
for event, payload in timeline:
    print(f"[{event.timestamp}] {payload}")
```

### Replay to a specific event

```python
timeline = await stream.replay(until_event="a3f8b2...")
# Returns all events up to and including that event ID
```

### Replay to a timestamp

```python
timeline = await stream.replay(until_timestamp="2026-06-01T12:00:00Z")
# Returns all events that existed at that point in time
```

### Replay to a checkpoint

```python
# First, find a checkpoint
checkpoints = await stream.list_checkpoints()
# [{"checkpoint_id": "cp_001", "event_id": "abc...", "timestamp": "..."}]

# Then replay to it
timeline = await stream.replay(until_event=checkpoints[0]["event_id"])
```

### What happens during replay

WalrusOS verifies every event during replay:

1. **Hash check** — the event's `blob_hash` must match the payload
2. **Signature check** — the Ed25519 signature must be valid
3. **Capability check** — the agent must have held the required capability at that point
4. **Ordering check** — parent IDs must form a valid chain

Tampered or corrupted events are silently dropped and logged. Replay only returns verified, valid events.

---

## Branching

Branching lets you create an experimental copy of a stream without affecting the original.

### Fork

```python
# Create a branch of the "main" stream
fork_stream_id = await stream.fork()
fork = workspace.stream_by_id(fork_stream_id)

# Write experimental events to the fork
await fork.append({"experiment": "What if we tried approach B?"})
await fork.append({"result": "Approach B reduces latency by 30%."})

# The original stream is untouched
main_timeline = await stream.timeline()   # doesn't include fork events
```

### Merge

```python
# Merge the fork back into main when ready
merge_event = await stream.merge(fork_stream_id)

# Now the main stream includes all fork events
merged_timeline = await stream.timeline()
```

### Compare branches

```python
# See what's different between a fork and the main stream
diff = await stream.diff(fork_stream_id)
for event_id, status in diff.items():
    print(f"{event_id}: {status}")   # "only_in_fork" | "only_in_main" | "in_both"
```

### Use case: A/B testing agent behavior

```python
# Production stream
prod = workspace.stream("agent-v1")

# Create an experimental branch for v2
experimental_id = await prod.fork()
experimental    = workspace.stream_by_id(experimental_id)

# Run v2 agent against the experimental branch
await experimental.append({"version": "v2", "decision": "..."})

# Compare results before promoting to production
diff = await prod.diff(experimental_id)
if diff_looks_good(diff):
    await prod.merge(experimental_id)
```

---

## Crash recovery

### Automatic recovery

If your process crashes mid-write, WalrusOS recovers automatically on restart. The SQLite ledger uses atomic writes, so there are no partial events.

```python
runtime = WalrusOS()   # on restart, resumes from where it left off
stream  = runtime.workspace("app").stream("agent-memory")
await stream.append(...)   # continues from the last committed event
```

### Full disaster recovery

If you lose your local database entirely, recover from the network:

```bash
# From the CLI
walrusos recover --workspace research

# Reconstructs:
# 1. Queries Sui blockchain for all anchored events
# 2. Fetches payloads from Walrus
# 3. Verifies cryptographic integrity
# 4. Rebuilds local SQLite + vector index
```

Or from Python:

```python
from walrusos.engine.recovery import DisasterRecoveryEngine
from walrusos import WalrusOS

runtime = WalrusOS()

async def recover():
    engine = DisasterRecoveryEngine(
        ledger=runtime._ledger,
        storage=runtime._storage,
        vector=runtime._vector,
    )

    def on_progress(current, total):
        print(f"Recovered {current}/{total} events")

    count = await engine.recover(progress_callback=on_progress)
    print(f"Recovery complete. {count} events restored.")
```

### What gets recovered

| Component | Recovery source |
|-----------|----------------|
| Event history | Sui blockchain event log |
| Payload data | Walrus blob storage |
| Vector index | Rebuilt from payload text |
| Agent identities | Reconstructed from AgentRegistered events |
| Capabilities | Reconstructed from CapabilityGranted/Revoked events |

### What's NOT recovered

| Component | Why |
|-----------|-----|
| Encryption keys | The KEK is on your machine — back up `~/.walrusos/.machine_secret` |
| Local file outputs | WalrusOS doesn't track files outside the stream |

---

## Snapshots

Snapshots capture the full state of a stream at a point in time and store it as a single blob.

```python
# Create a snapshot
snapshot_id = await stream.snapshot()
print(f"Snapshot blob ID: {snapshot_id}")

# Restore into a new stream (e.g., for a new agent instance)
new_stream_id = await runtime.workspace("app").restore_snapshot(
    snapshot_blob_id=snapshot_id,
    new_agent_id=uuid.uuid4(),
)
```

Snapshots are useful for:

- Cloning an agent's memory for a new instance
- Creating a known-good checkpoint before a risky operation
- Archiving the state of a completed project

> **Note:** Restored events are marked with `_restored_from_snapshot` in their payload. They do not carry the original event's signature — use full disaster recovery if you need cryptographic continuity.

---

## Time travel in the dashboard

The dashboard's **Replay** page lets you scrub through your stream's history visually:

1. Open the dashboard: `http://localhost:3000`
2. Navigate to **Replay**
3. Select a workspace and stream
4. Use the timeline slider to travel to any point
5. See the reconstructed agent state at that moment

---

## Recovery guarantees

| Scenario | WalrusOS behavior |
|----------|------------------|
| Process crash mid-write | Event is either fully committed or not at all |
| Local SQLite deleted | Full recovery from Sui + Walrus |
| Walrus blob unavailable | Event listed with `_status: PayloadLost`, skipped |
| Sui RPC unavailable | Reads from local SQLite cache (zero latency) |
| Network partition | Writes succeed locally; Sui anchoring retried on reconnect |
| Tampered blob | Decryption fails (AES-GCM authentication tag mismatch) |
| Tampered event | Signature check fails; event dropped during replay |
