# Concepts

This page explains the core ideas behind WalrusOS. Read this once, and the rest of the library will make sense.

---

## The mental model

WalrusOS is **Git for AI memory**.

- A **Workspace** is a repository.
- An **Agent** is a contributor.
- A **Stream** is a branch.
- Every `append()` is a commit.
- `replay()` is `git log`.
- `fork()` is `git branch`.
- `merge()` is `git merge`.

If you understand Git, you understand WalrusOS.

---

## Memory

Memory in WalrusOS is **append-only**. You can never delete or overwrite an event. You can only add new ones.

This isn't a limitation — it's the feature. An append-only log means:

- Every decision an agent made is permanently auditable
- You can replay any point in history exactly
- Multiple agents can write concurrently without conflicts
- Crashes don't corrupt state — you just replay from the last good point

Every memory event is:

| Field | Description |
|-------|-------------|
| `event_id` | Unique SHA-256 hash. Content-addressed — the ID changes if the data changes. |
| `timestamp` | ISO 8601 UTC. Set at append time. |
| `blob_hash` | SHA-256 of the payload. Tamper detection. |
| `signature` | Ed25519 signature from the agent's key. Proves authorship. |
| `parent_id` | Links to the previous event. Forms the DAG. |

### Memory types

WalrusOS classifies memory by how it's used:

| Type | Use |
|------|-----|
| `semantic` | Facts, knowledge, long-term beliefs |
| `episodic` | Specific past experiences, conversation turns |
| `procedural` | How to do things — learned skills |
| `working` | Short-term scratchpad for current task |
| `system` | Infrastructure events (checkpoints, recovery) |

```python
await stream.append(
    {"fact": "Paris is the capital of France."},
    memory_type="semantic",
)

await stream.append(
    {"turn": 3, "user": "What's the weather?", "reply": "Sunny, 22°C."},
    memory_type="episodic",
)
```

---

## Agents

An **Agent** in WalrusOS is a named identity within a workspace. It has:

- A persistent **Ed25519 key pair** — every event it writes is signed
- A **trust root** — a SHA-256 fingerprint that rolls forward with every event
- A **reputation** — counters for successful writes, failed verifications, and capability grants
- **Capabilities** — what it's allowed to do (read, write, fork, merge)

```python
agent = runtime.workspace("research").agent("Researcher")

print(agent.agent_id)     # deterministic UUID — same name = same ID across restarts
print(agent.trust_root)   # rolls forward with every event the agent produces
```

Agents are **lazy** — they're created on first use, not on declaration. Calling `workspace.agent("Researcher")` twice returns the same agent.

### Agent identity vs agent behavior

WalrusOS manages **identity** — who wrote what, when, and with what authority.

It does not manage **behavior** — that's your LLM, your prompts, your graph. WalrusOS is the memory layer; your framework is the execution layer.

---

## Streams

A **Stream** is an ordered, append-only sequence of memory events. Think of it as a named log.

```python
stream = workspace.stream("findings")    # workspace-level — any agent can write
stream = agent.stream("scratchpad")      # agent-level — private to one agent
```

### Writing

```python
event = await stream.append({
    "thought": "The model is overfitting on the validation set.",
    "step":    42,
})

print(event.event_id)    # SHA-256 hash
print(event.blob_hash)   # hash of the payload
print(event.signature)   # Ed25519 signature
```

### Reading

```python
# Full timeline — oldest to newest
timeline = await stream.timeline()
for event, payload in timeline:
    print(f"[{event.timestamp}] {payload}")

# Search by meaning
results = await stream.search("overfitting")
```

### Subscribing

```python
async def on_event(payload):
    print(f"New memory: {payload}")

task = await agent.subscribe(stream, on_event)   # non-blocking
# ...
task.cancel()   # unsubscribe
```

### Forking and merging

```python
# Create an experimental branch
fork_id = await stream.fork()
fork    = workspace.stream_by_id(fork_id)

# Write to the fork
await fork.append({"experiment": "trying new approach"})

# Merge back when done
merge_event = await stream.merge(fork_id)
```

---

## Permissions

WalrusOS has two layers of access control:

**Layer 1 — Sui on-chain capabilities (production)**

When a Sui wallet is connected, capabilities are minted as Move objects on the Sui blockchain. An agent that doesn't hold the capability object simply cannot produce valid transactions. The blockchain enforces this — there's no way to bypass it.

**Layer 2 — Local replay verification (always active)**

During replay, WalrusOS checks that each event was produced by an agent that held the correct capability at the time. Events that violate this are dropped.

### Capability types

| Capability | Allows |
|------------|--------|
| `read` | Read events from a stream |
| `write` | Append events to a stream |
| `fork` | Create a branch of a stream |
| `merge` | Merge a branch back |

### Granting permissions

```python
workspace = runtime.workspace("research")
researcher = workspace.agent("Researcher")
reviewer   = workspace.agent("Reviewer")

# Give Reviewer read access to Researcher's stream
await workspace.grant(
    from_agent=researcher,
    to_agent=reviewer,
    capability="read",
    stream=researcher.stream("findings"),
)
```

---

## Walrus

[Walrus](https://walrus.xyz) is the decentralized storage network where WalrusOS persists memory.

**You don't need to know how Walrus works to use WalrusOS.** The `WalrusAdapter` handles:

- Compressing payloads (zstd)
- Encrypting them (AES-256-GCM)
- Uploading to the Walrus testnet/mainnet
- Downloading and decrypting on read

Your data never touches Walrus in plaintext. The encryption key lives on your machine (wrapped in your `WALRUSOS_KEY_PASSWORD`).

### What Walrus gives you

- **Permanent storage** — blobs are stored for a configurable number of epochs (default: 5). One epoch ≈ 1 day on testnet.
- **Content addressing** — every blob has a unique ID derived from its content.
- **Decentralization** — no single company controls your data.

### Walrus blob IDs

Every memory event produces a `blob_id`. This is a globally unique, content-addressed identifier on the Walrus network. You can share it with anyone who has decryption access.

```python
event = await stream.append({"message": "hello"})
print(event.blob_id)    # e.g. "Qm...abc123"
```

---

## Sui

[Sui](https://sui.io) is the blockchain WalrusOS uses for:

1. **Agent identity** — each agent's public key is registered on-chain
2. **Event anchoring** — every memory event gets a Sui transaction digest, making tampering detectable
3. **Capability tokens** — permissions are Move objects owned by wallets
4. **Recovery** — you can reconstruct your entire memory from the Sui event log + Walrus blobs

**You don't need to understand Sui to use WalrusOS.** In development mode (`use_mocks=True`), Sui is replaced entirely by an in-memory mock. In production with no wallet configured, WalrusOS runs in SQLite-only mode — data still goes to Walrus, but without on-chain anchoring.

### What Sui adds

| Without Sui | With Sui |
|-------------|----------|
| Data in Walrus, indexed locally | Data in Walrus, indexed on-chain |
| Trust based on local SQLite | Trust anchored to blockchain |
| Recovery from local DB only | Recovery from blockchain + Walrus |
| Capabilities enforced locally | Capabilities enforced by Move contracts |

### Connecting a wallet

```bash
# Install Sui CLI
brew install sui      # macOS
# or: https://docs.sui.io/build/install

# Create or import a wallet
sui client active-address

# Tell WalrusOS to use it
walrusos login
```

---

## Recovery

WalrusOS is designed to survive any failure — process crash, disk wipe, machine loss.

**The full state can always be reconstructed** from the Sui blockchain event log and the Walrus blob storage. Both are decentralized and exist independently of your machine.

See [Recovery & Replay](recovery.md) for the full guide.

---

## Replay

Every stream can be replayed from any point:

```python
# Replay everything
timeline = await stream.timeline()

# Replay up to a specific event
timeline = await stream.replay(until_event="abc123...")

# Replay up to a timestamp
timeline = await stream.replay(until_timestamp="2026-01-01T12:00:00Z")
```

During replay, WalrusOS cryptographically verifies every event — checking signatures, hashes, and capability constraints. Tampered events are dropped.

---

## Trust

Every agent has a **trust root** — a SHA-256 hash that starts from the agent's identity and rolls forward deterministically with every event it produces.

```
TrustRoot₀ = SHA256(wallet : workspace_id : agent_name)
TrustRoot₁ = SHA256(TrustRoot₀ : event_id_1)
TrustRoot₂ = SHA256(TrustRoot₁ : event_id_2)
...
```

This means:
- The trust root uniquely identifies where an agent is in its history
- Two agents that produced the same events in the same order have the same trust root
- Any divergence (a skipped event, a tampered event) produces a different trust root
- You can verify an agent's history by recomputing its trust root from scratch

### The trust graph

WalrusOS maintains a trust graph — a record of how agents have interacted, what capabilities they've granted to each other, and how many successful/failed verifications they've accumulated.

The dashboard visualizes this graph in real-time. Think of it as a reputation system for AI agents.
