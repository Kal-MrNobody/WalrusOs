# Architecture

How WalrusOS works internally.

---

## Overview

WalrusOS is built in layers. Each layer has a single responsibility and can be swapped independently.

```
┌─────────────────────────────────────────────────────────────┐
│                      Your Application                        │
│          LangGraph  ·  CrewAI  ·  AutoGen  ·  Custom        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                       Framework Integrations                  │
│    AsyncWalrusSaver  ·  WalrusMemory  ·  WalrusConvoStore    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                        SDK Layer                             │
│          WalrusOS  ·  WorkspaceClient  ·  AgentClient        │
│                    StreamClient                               │
└────────┬──────────────────┬──────────────────────┬──────────┘
         │                  │                       │
┌────────▼────────┐ ┌───────▼────────┐ ┌──────────▼──────────┐
│  Memory Engine  │ │  Replay Engine │ │  Recovery Engine     │
│  (DAG writes)   │ │  (time travel) │ │  (disaster recovery) │
└────────┬────────┘ └───────┬────────┘ └──────────┬──────────┘
         │                  │                       │
┌────────▼──────────────────▼───────────────────────▼─────────┐
│                       Adapters                                │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  Walrus     │  │  Sui         │  │  Vector (TF-IDF)   │   │
│  │  Adapter    │  │  Ledger      │  │  Adapter           │   │
│  │  (storage)  │  │  Adapter     │  │  (semantic search) │   │
│  └──────┬──────┘  └──────┬───────┘  └───────────────────┘   │
│         │                │                                    │
│         │         ┌──────▼───────┐                           │
│         │         │  SQLite      │                           │
│         │         │  Ledger      │                           │
│         │         └──────────────┘                           │
└─────────┼──────────────────────────────────────────────────-─┘
          │                  │
    ┌─────▼─────┐      ┌─────▼─────┐
    │  Walrus   │      │  Sui      │
    │  Network  │      │  Blockchain│
    └───────────┘      └───────────┘
```

---

## Project structure

```
walrusos/
├── client.py              # WalrusOS — top-level entry point
├── config.py              # Config loading (env vars, JSON file, defaults)
│
├── core/
│   ├── models/
│   │   ├── events.py      # ProtocolEvent, EventType enum
│   │   ├── memory.py      # MemoryEvent (stream-level event)
│   │   ├── agent_identity.py  # AgentIdentity, AgentReputation, trust root
│   │   └── ...
│   ├── crypto.py          # Ed25519 signing, SHA-256 hashing, canonical JSON
│   └── projections/
│       └── engine.py      # Folds events into state (event sourcing pattern)
│
├── engine/
│   ├── memory.py          # MemoryEngine — DAG writes, timeline, fork, merge
│   ├── replay.py          # ReplayEngine — verified event replay, capability checks
│   ├── recovery.py        # DisasterRecoveryEngine — Sui + Walrus reconstruction
│   ├── event_store.py     # Protocol-level event store (workspace/agent events)
│   └── interfaces.py      # LedgerAdapter, StorageAdapter, VectorAdapter (ABCs)
│
├── adapters/
│   ├── walrus.py          # WalrusAdapter — encrypt/compress/upload/download
│   ├── key_store.py       # KeyStore — DEK management, PBKDF2 KEK derivation
│   ├── sui.py             # SuiIdentityAdapter, SuiLedgerAdapter
│   ├── sqlite_ledger.py   # SQLiteLedger — local SQLite write-through cache
│   └── in_memory.py       # InMemoryLedger, InMemoryStorage, InMemoryVector (mocks)
│
├── sdk/
│   ├── workspace.py       # WorkspaceClient — workspace.agent(), workspace.stream()
│   ├── agent.py           # AgentClient — publish(), subscribe(), search()
│   └── stream.py          # StreamClient — append(), timeline(), replay(), fork()
│
├── integrations/
│   ├── langgraph.py       # AsyncWalrusSaver (LangGraph BaseCheckpointSaver)
│   ├── crewai.py          # WalrusMemory (CrewAI embedder)
│   ├── openai.py          # WalrusConversationStore
│   ├── autogen.py         # WalrusGroupChatManager
│   ├── llamaindex.py      # WalrusChatMemoryBuffer
│   └── pydanticai.py      # WalrusMemoryTool, WalrusResultProcessor
│
└── cli/
    └── main.py            # Typer CLI — init, login, replay, search, recover, ...
```

---

## Event sourcing

WalrusOS is built on the **event sourcing** pattern. There is no mutable state — only an append-only log of events.

**Every state change is an event.** When you call `stream.append(payload)`, WalrusOS creates a `MemoryEvent` with:

- A unique `event_id` (SHA-256 of content + random nonce)
- The `blob_id` of the encrypted payload in Walrus
- A `blob_hash` (SHA-256 of the payload, for integrity)
- An Ed25519 `signature` from the writing agent
- A `parent_id` pointing to the previous event

This forms an **append-only DAG** (directed acyclic graph). The head of the DAG is always the most recent event.

### Event lifecycle

```
payload dict
    │
    ▼
serialize → compress → encrypt → upload to Walrus
                                       │
                              ◄────────┘  blob_id
                              │
                         MemoryEvent {
                           event_id: SHA256(parent + blob_id + ts + nonce)
                           blob_id: "Qm..."
                           blob_hash: SHA256(payload)
                           signature: Ed25519(agent_private_key, blob_hash)
                           parent_id: previous_event_id
                         }
                              │
                              ▼
                    write to SQLite (synchronous)
                              │
                              ▼
                    anchor to Sui (async, background)
```

### Protocol events vs memory events

WalrusOS has two event types:

| Type | Class | Purpose |
|------|-------|---------|
| **Protocol event** | `ProtocolEvent` | System-level: workspace created, agent registered, capability granted |
| **Memory event** | `MemoryEvent` | Content-level: what your agent is thinking/doing |

Protocol events are stored in the `EventStoreEngine`. Memory events are stored in the `MemoryEngine`. Both use the same underlying adapters.

---

## The write path (detail)

When you call `await stream.append(payload)`:

1. **Memory Engine** receives the call
2. Payload is serialized to JSON bytes
3. **Walrus Adapter** compresses (zstd) and encrypts (AES-256-GCM)
4. **Walrus Adapter** uploads to Walrus HTTP API, receives `blob_id`
5. **Memory Engine** computes `event_id = SHA256(parent_id + blob_id + timestamp + nonce)`
6. **Memory Engine** creates `MemoryEvent(event_id, blob_id, blob_hash, parent_id, ...)`
7. **SQLite Ledger** writes the event record (atomic)
8. **SQLite Ledger** updates the stream head pointer
9. **Vector Adapter** upserts the payload text into the TF-IDF index
10. **Sui Ledger Adapter** (async) submits anchor transaction to Sui blockchain
11. Control returns to caller with the `MemoryEvent` — total time: ~5ms (local) or ~200ms (with Walrus)

---

## The read path (detail)

When you call `await stream.timeline()`:

1. **SQLite Ledger** returns all `MemoryEvent` records for the stream (ordered by epoch counter)
2. For each event, **Walrus Adapter** downloads the blob by `blob_id`
3. **Walrus Adapter** decrypts (AES-256-GCM) and decompresses (zstd)
4. Payload is deserialized from JSON
5. Returns `List[(MemoryEvent, dict)]`

---

## The replay path (detail)

When you call `await stream.replay(verify_crypto=True)`:

1. **SQLite Ledger** returns events in order
2. **Replay Engine** iterates events, maintaining:
   - `agent_keys` dict: agent_id → public_key (built from AgentRegistered events)
   - `active_capabilities` dict: agent_id → List[capability]
3. For each event, verifies:
   - `blob_hash` matches the downloaded payload
   - Ed25519 `signature` is valid for the public key
   - Agent held required capability at this point in the stream
4. Tampered or invalid events are dropped and logged
5. Returns only verified events

---

## Adapter interface

Any component can be swapped by implementing the adapter interface:

```python
from walrusos.engine.interfaces import StorageAdapter, LedgerAdapter, VectorAdapter

class MyStorageAdapter(StorageAdapter):
    async def store_blob(self, data: bytes) -> str: ...       # returns blob_id
    async def retrieve_blob(self, blob_id: str) -> bytes: ... # raises if not found

class MyLedgerAdapter(LedgerAdapter):
    async def create_stream(self, agent_id: uuid.UUID) -> uuid.UUID: ...
    async def append_event(self, stream_id: uuid.UUID, event: MemoryEvent) -> None: ...
    async def get_head(self, stream_id: uuid.UUID) -> Optional[str]: ...
    async def list_events(self, stream_id: uuid.UUID) -> List[MemoryEvent]: ...

class MyVectorAdapter(VectorAdapter):
    async def upsert(self, doc_id: str, text: str, metadata: dict) -> None: ...
    async def search(self, query: str, limit: int) -> List[Tuple[str, float]]: ...
```

Inject your adapters:

```python
from walrusos.engine.memory import MemoryEngine

engine = MemoryEngine(
    ledger=MyLedgerAdapter(),
    storage=MyStorageAdapter(),
    vector=MyVectorAdapter(),
)
```

This is how the mock adapters work — `InMemoryLedger`, `InMemoryStorage`, `InMemoryVector` all implement these interfaces.

---

## Cryptography

All cryptographic operations are in `walrusos/core/crypto.py`.

| Operation | Algorithm | Used for |
|-----------|-----------|----------|
| Event signing | Ed25519 | Proves an agent wrote an event |
| Payload hashing | SHA-256 | Integrity verification |
| Canonical serialization | RFC 8785 JSON Canonicalization | Deterministic hash input |
| Blob encryption | AES-256-GCM | Data confidentiality |
| KEK derivation | PBKDF2-HMAC-SHA256 | Wrapping DEKs |
| Trust root | SHA-256 chaining | Deterministic agent history fingerprint |

The library uses Python's `cryptography` package (backed by OpenSSL/BoringSSL). No custom crypto.

---

## Design decisions

### Why append-only?

Immutability enables replay. You can reconstruct any past state deterministically because you have the complete, unmodified history. It also enables concurrent writes without coordination — two agents can write simultaneously without locking.

### Why SQLite as the primary read store?

Reads need to be fast. Querying Sui or Walrus on every read would be too slow. SQLite is a local write-through cache that makes reads zero-latency while still being rebuilt from the network if lost.

### Why Ed25519 and not secp256k1?

Sui uses secp256k1 for wallet addresses but also supports Ed25519 for object signing. Ed25519 is faster, produces smaller signatures, and has better constant-time implementation properties. Agent keys use Ed25519; wallet-level operations use whatever Sui supports.

### Why event sourcing?

Event sourcing makes replay, branching, and recovery natural — they're just operations on the event log. It also makes debugging straightforward: you can always answer "what happened and when" because you have the full history.
