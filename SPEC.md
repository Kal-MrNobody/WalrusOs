# WalrusOS Protocol Specification

```
Document:   SPEC.md
Series:     WalrusOS Core
Version:    0.1.0 (Draft)
Status:     DRAFT — NOT FOR PRODUCTION
Date:       2026-06-16
Authors:    WalrusOS Protocol Working Group
```

---

## Abstract

WalrusOS is a persistent operating layer for autonomous AI agents. It defines a set of protocol primitives that together provide durable, verifiable, sovereign, and economically governed memory for agents running on any compute substrate. WalrusOS is built on two underlying protocols: **Walrus** (decentralized blob storage) and **Sui** (programmable object blockchain). Neither is optional. Together they constitute the WalrusOS substrate.

This document specifies the eight core primitives of WalrusOS. It does not specify implementation. It does specify semantics, invariants, identity schemes, state machines, and relationships between primitives. Conformant implementations MUST satisfy all MUST and SHALL constraints. SHOULD constraints represent strongly recommended behavior. MAY constraints are optional.

---

## Conformance Language

The key words **MUST**, **MUST NOT**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119].

The key word **IMMUTABLE** means: once written, a value MUST NOT change under any circumstance, including operator action.

The key word **MONOTONIC** means: a value MUST only increase. Decreasing a MONOTONIC value constitutes a protocol violation.

The key word **CANONICAL** means: there is exactly one valid encoding of a value; implementations MUST NOT produce or accept alternative encodings.

---

## Notation

```
TYPE            A named type definition
TYPE?           An optional field of TYPE; may be absent or null
[TYPE]          An ordered list of TYPE
{K: V}          A map from key type K to value type V
|               Union type (one of)
::              Namespace separator
<N>             A placeholder for a user-supplied name N
#               Comment
```

Identifiers use the format `<domain>/<kind>/<name>[@<version>]`.  
Content addresses use the format `sha3-256:<hex>` (64 hex characters).  
Sui object IDs use the format `sui:<hex>` (64 hex characters).  
Walrus blob IDs use the format `walrus:<hex>` (64 hex characters).  
Ed25519 public keys use the format `ed25519:<base58>`.  
Signatures use the format `<scheme>:<base64>` where scheme is `ed25519` or `multisig`.

---

## Table of Contents

```
1.  Primitive: Agent
2.  Primitive: User
3.  Primitive: Memory Stream
4.  Primitive: Artifact
5.  Primitive: Memory Event
6.  Primitive: Capability
7.  Primitive: Subscription
8.  Primitive: Workspace
9.  Identifier Grammar
10. Epoch Model
11. Cryptographic Primitives
12. Primitive Relationships
13. Error Taxonomy
```

---

## 1. Primitive: Agent

### 1.1 Definition

An **Agent** is a named, addressable, autonomous computational principal registered in the WalrusOS Agent Registry. An Agent has a stable identity, a lifecycle, a Sui address that owns all of its on-chain objects, a Memory Stream, and a WAL treasury. An Agent is not a process. An Agent is not a model. An Agent is a persistent identity that MAY be executed by different runtimes, models, or compute environments across its lifetime.

An Agent is analogous to a UNIX process account: it persists independently of what program runs under it.

### 1.2 Identity

Every Agent is identified by a globally unique **Agent ID**:

```
agent-id ::= "agent/" <name> "/" <instance>

name       ::= [a-z0-9][a-z0-9-]{0,62}
instance   ::= [a-z0-9]{8,16}

Examples:
  agent/researcher/a3f92b01
  agent/orchestrator/cc8812de
```

An Agent ID MUST be unique within a WalrusOS network. An Agent ID MUST NOT be reused after an Agent is deprecated. The `instance` component is derived from the lower 8 bytes of the Agent's Sui address. It is IMMUTABLE.

### 1.3 Schema

```
Agent {
  # Identity
  id:              AgentID                   # IMMUTABLE. Globally unique agent identifier.
  version:         u64                       # MONOTONIC. Increments on every mutation.
  sui_address:     SuiAddress                # IMMUTABLE. The Sui address that owns all agent objects.
  sui_object_id:   SuiObjectID               # IMMUTABLE. The on-chain AgentIdentityObject ID.

  # Metadata
  display_name:    string                    # Human-readable label. 63 characters max. Mutable.
  description:     string?                   # Optional description. 1024 characters max. Mutable.
  created_epoch:   u64                       # IMMUTABLE. Walrus epoch at creation.
  created_unix_ms: u64                       # IMMUTABLE. Unix timestamp (ms) at creation.
  tags:            [string]                  # Freeform labels. 16 tags max. Each tag 63 chars max.

  # Lifecycle
  status:          AgentStatus              # Current lifecycle phase. See §1.4.
  paused_reason:   string?                  # Set when status is PAUSED. Cleared on RESUME.
  deprecated_by:   AgentID?                 # Set when status is DEPRECATED. Points to successor.

  # Ownership and custody
  owner:           UserID | AgentID         # The principal that owns this agent.
  workspace:       WorkspaceID?             # The workspace this agent belongs to, if any.
  operator_caps:   [CapabilityID]           # Active OperatorCap IDs held over this agent.

  # Memory
  memory_stream:   MemoryStreamID           # IMMUTABLE. The agent's primary Memory Stream.
  memory_classes:  [MemoryClass]            # Declared memory classes this agent uses.

  # Economics
  wal_treasury:    Balance<WAL>             # Current WAL balance for storage fees.
  storage_budget:  StorageBudget?           # Optional spending limits per epoch.

  # Runtime hints (advisory, not enforced by protocol)
  runtime_hints:   {string: string}         # e.g. {"framework": "langgraph", "model": "claude-4"}
}
```

### 1.4 Lifecycle

An Agent's lifecycle is a deterministic state machine. Transitions MUST be authorized by a Capability of sufficient scope (see §6).

```
State Machine:

  PENDING ──[register]──► ACTIVE
                              │
                    ┌─────────┼─────────┐
                    │         │         │
               [pause]   [transfer]  [deprecate]
                    │         │         │
                  PAUSED   ACTIVE    DEPRECATED
                    │     (new owner)     │
               [resume]              [succession]
                    │                    │
                  ACTIVE           DEPRECATED
                                   (successor set)

States:
  PENDING      Agent record created but not yet activated.
               MAY NOT write to Memory Stream.
               MAY NOT consume WAL.

  ACTIVE       Agent is operational.
               MUST have a funded WAL treasury (≥1 epoch of minimum storage).
               MAY read and write its Memory Stream.
               MAY hold and exercise Capabilities.

  PAUSED       Agent is suspended by operator action.
               MUST NOT execute autonomous actions.
               MUST NOT write to Memory Stream during pause.
               MAY read its Memory Stream (read-only).
               paused_reason MUST be set.
               WAL treasury continues to be charged for existing storage.

  DEPRECATED   Agent has permanently ceased operation.
               MUST NOT transition to any other state.
               MUST have deprecated_by set if succeeded by another Agent.
               Existing Artifacts remain accessible per their epoch lease.
               Memory Stream is sealed (no new events appendable).
               Remaining WAL treasury is returned to owner upon cleanup.
```

### 1.5 Invariants

- An Agent's `id`, `sui_address`, `sui_object_id`, `created_epoch`, `created_unix_ms`, and `memory_stream` are IMMUTABLE after the `register` transition.
- An Agent's `version` MUST be incremented atomically with every state-changing operation.
- An Agent MUST NOT be ACTIVE with a `wal_treasury` balance of zero for more than one epoch. Implementations SHOULD alert at two epochs of remaining balance.
- An Agent's `sui_address` MUST be the sole owner of its `sui_object_id` on the Sui blockchain. Transfer of ownership changes the `owner` field but does NOT change the `sui_address` (the signing key).
- An Agent MUST belong to at most one Workspace at any time.
- Two Agents MUST NOT share a `memory_stream`.

---

## 2. Primitive: User

### 2.1 Definition

A **User** is a human principal registered in WalrusOS. A User has a cryptographic identity, owns one or more Agents, and holds Capabilities that authorize actions over agents, workspaces, and memory. A User is distinct from an Agent. A User represents a human decision-maker; an Agent represents an autonomous computational actor. A User MAY be the same Sui address as an Agent's custody key but MUST be a separate registered identity.

### 2.2 Identity

```
user-id ::= "user/" <name>

name    ::= [a-z0-9][a-z0-9-]{0,62}

Examples:
  user/alice
  user/engineering-lead
```

A User ID MUST be unique within a WalrusOS network. User IDs are NOT IMMUTABLE — a User MAY be renamed if the renaming is authorized by the User's own signing key.

### 2.3 Schema

```
User {
  # Identity
  id:              UserID                    # Globally unique user identifier.
  version:         u64                       # MONOTONIC. Increments on every mutation.

  # Cryptographic identity (one or more; at least one MUST be present)
  primary_key:     PublicKey                 # Primary signing key. Ed25519 or Passkey (WebAuthn).
  recovery_keys:   [PublicKey]              # Recovery key set. 0–5 keys.
  zklogin_subs:    [ZkLoginSubject]         # OAuth subjects (Google, Apple, etc.) bound to this User.
  multisig_policy: MultiSigPolicy?          # M-of-N policy combining keys above.

  # Sui binding
  sui_address:     SuiAddress               # The Sui address derived from primary_key or multisig_policy.

  # Metadata
  display_name:    string?                  # Human-readable label.
  created_epoch:   u64                      # IMMUTABLE.
  created_unix_ms: u64                      # IMMUTABLE.

  # Ownership
  owned_agents:    [AgentID]               # Agents this User currently owns.
  owned_workspaces:[WorkspaceID]           # Workspaces this User administers.
  held_caps:       [CapabilityID]          # Active Capabilities held by this User.

  # Preferences
  default_workspace: WorkspaceID?          # Default workspace for new agents.
  notification_config: NotificationConfig? # Where to deliver Subscription events.
}
```

### 2.4 Authentication Schemes

A User MUST authenticate to WalrusOS by signing a challenge with a key that corresponds to a registered `primary_key`, `recovery_keys[i]`, or a zkLogin credential bound via `zklogin_subs`. WalrusOS MUST reject any request where the authenticated key does not resolve to a registered User or does not satisfy the User's `multisig_policy`.

```
PublicKey ::=
  | { scheme: "ed25519",  key: base58 }
  | { scheme: "secp256r1", key: base58 }   # Passkey / WebAuthn
  | { scheme: "secp256k1", key: base58 }   # Legacy

ZkLoginSubject ::= {
  provider:    "google" | "apple" | "github" | "twitch"
  subject_id:  string        # Stable OAuth sub claim
  audience:    string        # OAuth aud claim
  salt:        hex           # User-chosen salt (determines Sui address)
}

MultiSigPolicy ::= {
  keys:      [{key: PublicKey, weight: u8}]  # 2-10 keys
  threshold: u16                              # Sum of weights required
}
```

### 2.5 Invariants

- A User MUST have at least one active signing key at all times (primary_key or recovery_keys). A User with zero valid keys is permanently locked and MUST be considered inaccessible.
- A User's `sui_address` MUST be derived deterministically from `primary_key` (or `multisig_policy`). It MUST NOT be set manually.
- A User MUST NOT own more than 1024 Agents simultaneously. (This limit MAY be raised by WalrusOS network governance.)
- A User's `owned_agents` MUST reflect the current on-chain ownership state of AgentIdentityObjects on Sui. Discrepancies are protocol violations.
- A ZkLoginSubject `(provider, subject_id, audience, salt)` tuple MUST be unique per User. The same OAuth identity MUST NOT be bound to two different Users.

---

## 3. Primitive: Memory Stream

### 3.1 Definition

A **Memory Stream** is the ordered, append-only sequence of Memory Events produced by or for a specific Agent. A Memory Stream is the agent's canonical history. It is to an Agent what a git repository's `refs/heads/main` commit chain is to a project: a verifiable, content-addressed, causally-ordered log.

A Memory Stream is anchored on the Sui blockchain as a shared or owned object. The anchor holds the **head pointer** — the Event ID of the most recent Memory Event in the stream. All prior events are reachable by following the `parent_id` chain of each Memory Event (see §5).

### 3.2 Identity

```
stream-id ::= "stream/" <agent-instance>

Examples:
  stream/a3f92b01
```

A Memory Stream's ID is derived from its owning Agent's `instance` component. A Memory Stream MUST be created in the same transaction that creates its owning Agent.

### 3.3 Schema

```
MemoryStream {
  # Identity
  id:                StreamID               # IMMUTABLE.
  agent_id:          AgentID               # IMMUTABLE. The owning agent.
  sui_object_id:     SuiObjectID           # IMMUTABLE. On-chain MemoryCursor object.

  # State
  head:              EventID?              # The most recent Memory Event. NULL on empty stream.
  event_count:       u64                   # MONOTONIC. Total events appended to this stream.
  sealed:            bool                  # True when the stream is permanently closed (agent DEPRECATED).

  # Content summary
  classes_present:   [MemoryClass]         # Distinct memory classes that have been written.
  total_bytes_net:   u64                   # Sum of raw blob sizes of all live (non-deleted) events.
  epoch_span:        [u64, u64]            # [first_event_epoch, last_event_epoch]

  # Epoch window (storage lease coverage)
  min_covered_epoch: u64                   # Earliest epoch covered by any live Artifact in this stream.
  max_covered_epoch: u64                   # Latest epoch covered by any live Artifact in this stream.

  # Retention policy
  retention_policy:  RetentionPolicy?      # Governs automatic expiry and renewal.
}

MemoryClass ::=
  | "working"       # Short-lived task state and scratchpad
  | "episodic"      # Timestamped event records; agent's autobiography
  | "semantic"      # Distilled facts and knowledge; queryable by content
  | "procedural"    # Skills, rules, and learned behaviors
  | "checkpoint"    # Framework-specific execution snapshots (framework adapters)

RetentionPolicy ::= {
  default_epochs:       u64                # Default lease duration for new Artifacts (per class)
  importance_threshold: float              # [0.0, 1.0]. Events below threshold are not auto-renewed.
  max_total_bytes:      u64?              # If set, oldest low-importance events are pruned when exceeded.
  consolidation_window: u64?              # Epoch count; triggers consolidation when exceeded without renewal.
}
```

### 3.4 Append Protocol

A new Memory Event MUST be appended to a Memory Stream following this protocol:

```
Append Protocol:

1. VALIDATE
   - The caller MUST present a valid MemoryWriteCap (see §6) for this stream's agent_id.
   - The stream MUST NOT be sealed.
   - The new event's parent_id MUST equal the stream's current head.
     (This enforces causal ordering and prevents concurrent appends from forking the stream.)

2. WRITE ARTIFACT(S)
   - All Artifacts referenced by the new event MUST be written to Walrus first.
   - Each Artifact MUST be certified (availability certificate confirmed on Sui) before the event is appended.
   - Artifact writes MAY be performed asynchronously, but the event MUST NOT be appended
     until all referenced Artifacts are certified.

3. SIGN EVENT
   - The Memory Event MUST be signed by the Agent's signing key.
   - The signature MUST cover the CANONICAL serialization of the event (see §11).

4. COMMIT
   - The event is appended by updating the on-chain MemoryCursor:
       new_head     = event_id
       event_count += 1
   - This update MUST be atomic. Partial updates (head updated without event_count, or vice versa)
     are protocol violations.

5. EMIT
   - A MemoryEvent notification MUST be emitted to the Sui event system (see §7).
   - Subscriptions matching this event MUST be notified within one Sui epoch of commit.
```

### 3.5 Invariants

- A Memory Stream MUST be owned by exactly one Agent.
- A Memory Stream MUST be append-only. Events MUST NOT be removed from the causal chain. (Artifacts referenced by events MAY be deleted from Walrus when their epoch lease expires, but the event record itself persists in the chain.)
- The `head` of a sealed stream MUST NOT change after sealing.
- The `event_count` MUST equal the length of the causal chain from `head` back to the genesis event.
- A Memory Stream MUST have at most one concurrent active writer. Concurrent appends MUST be rejected with `CONCURRENT_WRITE_CONFLICT`.
- A Memory Stream MAY be empty (`head = NULL`, `event_count = 0`).

---

## 4. Primitive: Artifact

### 4.1 Definition

An **Artifact** is a discrete, content-addressed, immutable binary object stored on the Walrus decentralized storage network. An Artifact is the atomic unit of stored information in WalrusOS. All persistent data — memory records, execution checkpoints, knowledge bases, model outputs, embeddings, logs — is stored as Artifacts.

An Artifact is to WalrusOS what a blob object is to git: the content is addressed by its hash, is immutable once written, and carries no inherent meaning beyond its bytes. Meaning is conferred by the Memory Events that reference and annotate the Artifact.

### 4.2 Identity

An Artifact's identity is its **Artifact ID**, which is the Walrus Blob ID — a content-derived hash assigned by the Walrus protocol upon certification:

```
artifact-id ::= "artifact/" walrus-blob-id

walrus-blob-id ::= "walrus:" hex64

Example:
  artifact/walrus:3f8a2c9b01d4e7f6a5b8c3d2e1f09a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1
```

Two Artifacts with identical content MUST have identical IDs. Writing the same content twice MUST NOT create two distinct Artifacts — the Walrus protocol enforces this via content addressing.

### 4.3 Schema

```
Artifact {
  # Identity
  id:              ArtifactID              # IMMUTABLE. Derived from blob content.
  walrus_blob_id:  WalrusBlobID           # IMMUTABLE. The Walrus-layer identifier.
  sui_object_id:   SuiObjectID            # IMMUTABLE. The on-chain Walrus Blob object.

  # Content description
  content_type:    MediaType              # IANA media type. e.g. "application/json", "application/octet-stream"
  encoding:        Encoding?             # Content encoding applied before storage. e.g. "zstd", "lz4"
  byte_size:       u64                   # IMMUTABLE. Uncompressed byte size of content.
  stored_size:     u64                   # IMMUTABLE. Compressed byte size as stored on Walrus.
  content_hash:    ContentHash           # IMMUTABLE. sha3-256 hash of the UNCOMPRESSED content.

  # Authorship
  author_id:       AgentID | UserID      # Who created this artifact.
  author_signature: Signature            # ed25519 or multisig signature over content_hash.
  created_epoch:   u64                   # IMMUTABLE.
  created_unix_ms: u64                   # IMMUTABLE.

  # Storage lifecycle
  storage_mode:    StorageMode           # See §4.4.
  start_epoch:     u64                   # IMMUTABLE. Epoch from which Walrus stores this blob.
  end_epoch:       u64?                  # Epoch after which the blob MAY be garbage-collected.
                                          # NULL for permanent artifacts.

  # Encryption
  encrypted:       bool                  # Whether the stored bytes are encrypted.
  encryption_scheme: EncryptionScheme?  # Required if encrypted = true.

  # Availability
  certified:       bool                  # True once Walrus availability certificate is on-chain.
  availability_cert: AvailabilityCert?  # The on-chain certificate. NULL until certified.
}

StorageMode ::=
  | "ephemeral"    # 1-epoch lease; used for working memory
  | "durable"      # Multi-epoch lease; the default for episodic and semantic memory
  | "permanent"    # Permanent storage funded via Walrus storage fund; no end_epoch

EncryptionScheme ::=
  | { type: "seal-ibe",    policy_id: SuiObjectID }  # Seal threshold IBE with on-chain policy
  | { type: "aes-256-gcm", key_ref:   string }        # Symmetric key, referenced externally

ContentHash ::= "sha3-256:" hex64

AvailabilityCert ::= {
  certificate_digest: hex64      # Walrus-layer availability certificate
  certified_epoch:    u64
  certified_unix_ms:  u64
}
```

### 4.4 Storage Modes

```
Mode         | end_epoch      | Use Case                         | WAL Cost Model
─────────────┼────────────────┼──────────────────────────────────┼────────────────────
ephemeral    | created + 1    | Working memory, scratch state    | Minimal (1 epoch)
durable      | created + N    | Episodic logs, checkpoints       | N × byte_size × rate
permanent    | NULL           | Knowledge bases, published specs | Lump sum (storage fund)
```

The `permanent` mode MUST be authorized by the agent's operator. An agent MUST NOT set `permanent` on its own without `MemoryAdminCap` or higher.

### 4.5 Invariants

- An Artifact's `content_hash` MUST equal `sha3-256(uncompressed_content)`. Implementations MUST verify this on read.
- An Artifact's `author_signature` MUST be a valid signature over `content_hash` by the stated `author_id`'s current signing key. Implementations MUST verify this before accepting an Artifact into a Memory Stream.
- An Artifact MUST NOT be mutated. Updating an Artifact's content creates a new Artifact with a different ID. The original MUST remain unchanged.
- An Artifact's `certified` flag MUST be set to `true` only after the Walrus availability certificate is confirmed on-chain. An Artifact with `certified = false` MUST NOT be referenced by any Memory Event.
- An Artifact's `content_type` MUST be a valid IANA media type string.
- An Artifact's `byte_size` MUST be greater than zero. Zero-byte Artifacts are not permitted.

---

## 5. Primitive: Memory Event

### 5.1 Definition

A **Memory Event** is a signed, content-addressed record that describes a discrete occurrence in an Agent's history. A Memory Event is the unit of the Memory Stream. It references one or more Artifacts (the payload), carries metadata about the occurrence, and links to its predecessor event, forming a cryptographically-verifiable causal chain.

A Memory Event is to WalrusOS what a commit object is to git: it records what changed (artifacts), when (epoch), who changed it (author_signature), and why (event_type + annotations). It is immutable and content-addressed once appended to a stream.

### 5.2 Identity

An Event ID is the content hash of the CANONICAL serialization of the Memory Event record:

```
event-id ::= "event/" sha3-256-hex

Example:
  event/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2
```

The Event ID MUST be computed after all fields are set, including `author_signature`. The Event ID MUST NOT be computed from content that includes the Event ID itself (no circular reference).

### 5.3 Schema

```
MemoryEvent {
  # Identity
  id:              EventID               # IMMUTABLE. Content hash of this record.
  stream_id:       StreamID             # IMMUTABLE. The Memory Stream this event belongs to.
  sequence:        u64                  # MONOTONIC. Position in the stream (1-based).

  # Causality
  parent_id:       EventID?            # IMMUTABLE. The preceding event in the stream. NULL for genesis.

  # Timing
  epoch:           u64                  # IMMUTABLE. Walrus epoch at time of append.
  unix_ms:         u64                  # IMMUTABLE. Unix timestamp at time of append.

  # Classification
  event_type:      EventType            # See §5.4.
  memory_class:    MemoryClass          # The memory tier this event contributes to.

  # Payload
  artifacts:       [ArtifactRef]        # Ordered list of Artifacts this event references.
                                         # MUST be non-empty. MUST NOT exceed 64 entries.

  # Authorship
  author_id:       AgentID | UserID    # Who produced this event.
  author_signature: Signature          # Signs the CANONICAL serialization of all fields
                                         # except author_signature itself.

  # Annotations
  importance:      float               # [0.0, 1.0]. Relative salience. 0.5 if unset.
  topic_tags:      [string]           # Semantic labels. 16 max. 63 chars each.
  annotations:     {string: string}   # Freeform key-value metadata. 32 pairs max.

  # Cross-event relations
  supersedes:      EventID?           # If set, this event replaces/corrects a prior event.
  derived_from:    [EventID]         # Source events that this event was derived from (e.g. consolidation).

  # Embedding reference (for semantic indexing)
  embedding_ref:   ArtifactRef?       # Reference to an Artifact containing the vector embedding
                                        # of this event's primary content.
}

ArtifactRef ::= {
  artifact_id:   ArtifactID
  role:          ArtifactRole          # How this artifact relates to the event
  byte_range:    [u64, u64]?          # Optional byte range within the artifact (for large blobs)
}

ArtifactRole ::=
  | "primary"     # The main content of this event
  | "embedding"   # Vector embedding of the primary content
  | "diff"        # A delta relative to a previous artifact
  | "attachment"  # Supplementary data referenced by the primary
  | "proof"       # A cryptographic proof (e.g. ZK proof, availability certificate)
```

### 5.4 Event Types

```
EventType                | Description
─────────────────────────┼──────────────────────────────────────────────────────────────────
OBSERVATION              | Agent recorded an external fact or perception.
REASONING                | Agent recorded an internal reasoning trace or plan.
TOOL_CALL                | Agent invoked a tool; artifacts contain request and response.
TOOL_RESULT              | Agent received a tool result (paired with a TOOL_CALL event).
DECISION                 | Agent made a choice among alternatives; artifacts contain rationale.
LEARNING                 | Agent updated a belief or stored a new fact into semantic memory.
CHECKPOINT               | Agent persisted an execution checkpoint for crash recovery.
CONSOLIDATION            | A set of prior events was summarized into a single artifact.
                         | derived_from MUST list all source events.
HANDOFF                  | Agent transferred a task to another agent.
                         | annotations MUST include: {"target_agent_id": AgentID}
RECEIPT                  | Agent received a task or artifact from another agent.
                         | annotations MUST include: {"source_agent_id": AgentID}
CORRECTION               | Agent acknowledged and corrected a prior error.
                         | supersedes MUST be set to the corrected event's ID.
ARCHIVE                  | Agent marked a set of events as archived (still accessible, lower priority).
USER_ANNOTATION          | A User manually annotated this point in the stream.
SYSTEM                   | Protocol-level event (e.g. stream genesis, sealing).
                         | author_id MUST be a WalrusOS protocol identifier.
```

### 5.5 Genesis Event

Every Memory Stream MUST begin with a SYSTEM event of type SYSTEM with the following properties:

```
GenesisEvent {
  id:           <computed>
  stream_id:    <stream id>
  sequence:     1
  parent_id:    NULL
  event_type:   SYSTEM
  memory_class: "episodic"
  artifacts:    [<agent-manifest-artifact>]    # An artifact containing the agent's initial spec
  author_id:    <walrus-os-protocol>
  annotations:  {"event_subtype": "genesis", "agent_id": <agent-id>}
}
```

The genesis event MUST be the first event ever appended to the stream. No event with `sequence = 1` and `parent_id != NULL` is valid. No event with `parent_id = NULL` and `sequence != 1` is valid.

### 5.6 Invariants

- A Memory Event's `id` MUST equal `sha3-256(canonical_serialize(event))` where `canonical_serialize` produces a deterministic byte representation (see §11).
- A Memory Event's `author_signature` MUST be a valid signature over `sha3-256(canonical_serialize(event excluding author_signature field))`.
- A Memory Event's `parent_id` MUST reference an event with `sequence = this.sequence - 1` in the same stream.
- A Memory Event's `artifacts` list MUST contain at least one entry. All referenced Artifacts MUST be certified before the event is committed.
- A Memory Event's `importance` MUST be in the range [0.0, 1.0] inclusive.
- A Memory Event MUST NOT be deleted. Its Artifacts MAY be deleted (when their epoch lease expires), but the event record itself persists. An event whose Artifacts have been deleted is called a **tombstoned event** and MUST be visibly marked as such when enumerated.
- A CONSOLIDATION event MUST reference at least two events in `derived_from`. A CORRECTION event MUST reference exactly one event in `supersedes`. These are type-specific structural constraints.

---

## 6. Primitive: Capability

### 6.1 Definition

A **Capability** is a first-class protocol object that confers specific, scoped, time-bounded authority on a **grantee** principal. A Capability is a Sui Move object. Possessing a Capability object at the Sui address level is, by itself, sufficient proof of authorization for the actions the Capability covers. WalrusOS does not use access control lists, role registries, or mapping-based permission tables. All authorization flows through Capability objects.

A Capability is to WalrusOS what a capability token is to capability-based security theory: authority is materialized as an object, not inferred from identity. "You are allowed because you hold this object" — not "you are allowed because your address is in this list."

### 6.2 Identity

```
capability-id ::= "cap/" <type> "/" <nonce>

type   ::= capability type name (see §6.4)
nonce  ::= hex16 — randomly generated at creation time

Examples:
  cap/MemoryWriteCap/a3f92b01cc881200
  cap/OperatorCap/7de4a1b23c994501
```

### 6.3 Schema

```
Capability {
  # Identity
  id:              CapabilityID          # IMMUTABLE.
  cap_type:        CapabilityType        # IMMUTABLE. The type of authority this cap confers.
  sui_object_id:   SuiObjectID          # IMMUTABLE. The on-chain Sui object representing this cap.

  # Scope
  subject_id:      AgentID | WorkspaceID | StreamID
                                          # IMMUTABLE. What this cap grants authority over.
  scope_mask:      [Permission]          # IMMUTABLE. The specific permissions conferred.

  # Principals
  grantor_id:      AgentID | UserID     # IMMUTABLE. Who issued this capability.
  grantee_id:      AgentID | UserID     # IMMUTABLE. Who holds this capability.

  # Transferability
  transferable:    bool                  # IMMUTABLE. Whether this cap can be passed to another principal.
  delegatable:     bool                  # IMMUTABLE. Whether this cap can be used to issue sub-caps.

  # Validity window
  valid_from_epoch: u64                 # IMMUTABLE. First epoch in which this cap is exercisable.
  valid_until_epoch: u64?               # Epoch after which this cap is no longer valid. NULL = perpetual.

  # Revocability
  revocable:       bool                 # IMMUTABLE. If true, grantor can revoke before expiry.
  revoked:         bool                 # Set to true when revoked. MUST NOT be set back to false.
  revoked_epoch:   u64?                 # Epoch at which revocation occurred.
  revoked_reason:  string?              # Human-readable revocation reason.

  # Audit
  created_epoch:   u64                  # IMMUTABLE.
  created_unix_ms: u64                  # IMMUTABLE.
  last_exercised_epoch: u64?            # Updated when the cap is exercised. NULL if never used.
  exercise_count:  u64                  # MONOTONIC. Number of times this cap has been exercised.
}
```

### 6.4 Capability Types

```
CapabilityType         | Subject        | Confers Authority To
───────────────────────┼────────────────┼────────────────────────────────────────────────────────────
MemoryWriteCap         | AgentID        | Append Memory Events to the subject agent's Memory Stream.
                       |                | scope_mask specifies which MemoryClass values are writable.

MemoryReadCap          | AgentID        | Read Memory Events and retrieve Artifacts from the subject
                       |                | agent's Memory Stream.
                       |                | scope_mask specifies which MemoryClass values are readable.

MemoryAdminCap         | AgentID        | Extend Artifact epoch leases, trigger consolidation,
                       |                | mark events for archival, initiate succession protocol.

OperatorCap            | AgentID        | Execute lifecycle transitions on the subject agent.
                       |                | scope_mask specifies which AgentTransitions are permitted.

WorkspaceAdminCap      | WorkspaceID    | Modify workspace policy, add/remove members,
                       |                | approve workspace-level governance actions.

WorkspaceMemberCap     | WorkspaceID    | Participate in the workspace: read shared streams,
                       |                | contribute to shared Artifacts, subscribe to workspace events.

SubscriptionCap        | StreamID |     | Create, modify, and cancel Subscriptions targeting
                       | WorkspaceID    | the subject stream or workspace.

UpgradeCap             | PackageID      | Authorize WalrusOS Move package upgrades.
                       |                | Held by the WalrusOS governance multisig.
```

### 6.5 Permission Flags

```
Permission ::=
  # Memory permissions (used in MemoryWriteCap, MemoryReadCap scope_mask)
  | WRITE_WORKING
  | WRITE_EPISODIC
  | WRITE_SEMANTIC
  | WRITE_PROCEDURAL
  | WRITE_CHECKPOINT
  | READ_WORKING
  | READ_EPISODIC
  | READ_SEMANTIC
  | READ_PROCEDURAL
  | READ_CHECKPOINT

  # Operator permissions (used in OperatorCap scope_mask)
  | PAUSE_AGENT
  | RESUME_AGENT
  | DEPRECATE_AGENT
  | INITIATE_TRANSFER
  | FUND_TREASURY
  | MODIFY_RETENTION_POLICY
  | INITIATE_SUCCESSION

  # Workspace permissions (used in WorkspaceAdminCap scope_mask)
  | ADD_MEMBER
  | REMOVE_MEMBER
  | MODIFY_POLICY
  | DISSOLVE_WORKSPACE
```

### 6.6 Cap Issuance and Revocation Protocol

```
Issuance:

  1. Grantor MUST hold a Capability of equal or greater scope over the same subject.
     (You cannot grant what you do not have.)

  2. If delegatable = false on the grantor's cap, the grantor MUST NOT issue sub-caps
     from that cap. (Non-delegatable caps are terminal.)

  3. A sub-cap's scope_mask MUST be a strict subset of the parent cap's scope_mask.
     (Privilege cannot be escalated through delegation.)

  4. A sub-cap's valid_until_epoch MUST NOT exceed the parent cap's valid_until_epoch.
     (Delegation cannot extend the time window beyond the parent's window.)

  5. The issuance transaction MUST emit a CapabilityGranted event (see §7).

Revocation:

  1. Only the grantor or a principal holding a CapabilityAdminCap over the same subject
     MAY revoke a revocable Capability.

  2. Non-revocable Capabilities MUST NOT be revoked before their valid_until_epoch.
     The only way to invalidate a non-revocable, non-expired Cap is for the grantee
     to voluntarily destroy the object.

  3. Revocation MUST set revoked = true and revoked_epoch = current_epoch.

  4. Revocation MUST emit a CapabilityRevoked event (see §7) within the same transaction.

  5. A revoked Capability MUST be rejected immediately by all protocol operations.
     Off-chain caches MUST treat a CapabilityRevoked event as a hard invalidation signal
     and MUST NOT accept the Cap for any operation with a timestamp after revoked_epoch.
```

### 6.7 Invariants

- A Capability's `scope_mask` MUST NOT be empty. A zero-permission capability is meaningless and MUST NOT be created.
- A Capability with `transferable = false` MUST NOT be moved to a different Sui address. It is soulbound — its grantee is fixed at creation.
- A Capability with `delegatable = false` MUST NOT be used to issue sub-capabilities of any kind.
- A Capability MUST NOT be exercised after `valid_until_epoch` (when set). Implementations MUST check the current epoch against `valid_until_epoch` at exercise time.
- A Capability MUST NOT be exercised after `revoked = true` is set.
- A Capability with `delegatable = true` MUST also have `transferable = true`. (You cannot delegate a cap you cannot move.)

---

## 7. Primitive: Subscription

### 7.1 Definition

A **Subscription** is a registered, filter-bound, delivery-configured contract that causes a principal to be notified when Memory Events matching specified criteria are appended to a Memory Stream or set of streams. A Subscription is reactive: it MUST NOT require the subscriber to poll. WalrusOS MUST deliver matching events to the subscriber's configured endpoint.

A Subscription is analogous to a `kubectl watch` command or a git post-receive hook: it specifies what to watch, and the system delivers notifications when changes occur.

### 7.2 Identity

```
subscription-id ::= "sub/" <subscriber-id> "/" <nonce>

nonce ::= hex8

Example:
  sub/user/alice/44a3f201
  sub/agent/researcher/a3f92b01/9c2d4e01
```

### 7.3 Schema

```
Subscription {
  # Identity
  id:              SubscriptionID        # IMMUTABLE.
  version:         u64                   # MONOTONIC.
  sui_object_id:   SuiObjectID          # On-chain Subscription object.

  # Subscriber
  subscriber_id:   AgentID | UserID     # IMMUTABLE. Who receives notifications.

  # Filter — defines which events trigger delivery
  filter:          SubscriptionFilter    # See §7.4.

  # Delivery
  delivery:        DeliveryConfig        # See §7.5.

  # Lifecycle
  status:          SubscriptionStatus    # ACTIVE | PAUSED | CANCELLED | EXPIRED
  created_epoch:   u64                   # IMMUTABLE.
  expires_epoch:   u64?                  # If set, subscription auto-cancels at this epoch.

  # Authorization
  cap_id:          CapabilityID         # The SubscriptionCap authorizing this subscription.

  # Stats
  events_delivered: u64                 # MONOTONIC. Total events delivered since creation.
  last_delivery_epoch: u64?             # Epoch of most recent delivery.
  last_delivery_event_id: EventID?      # EventID of most recent delivered event.
}
```

### 7.4 Filter Schema

```
SubscriptionFilter {
  # Stream selection (at least one MUST be set)
  stream_ids:        [StreamID]?          # Specific streams to watch.
  agent_ids:         [AgentID]?           # Watch all streams for these agents.
  workspace_id:      WorkspaceID?         # Watch all streams in this workspace.

  # Event content filters (all specified filters MUST match — logical AND)
  event_types:       [EventType]?         # If set, only deliver events of these types.
  memory_classes:    [MemoryClass]?       # If set, only deliver events of these classes.
  importance_min:    float?               # If set, only deliver events with importance ≥ this value.
  topic_tags_any:    [string]?           # If set, deliver events matching ANY of these tags.
  topic_tags_all:    [string]?           # If set, deliver events matching ALL of these tags.
  author_ids:        [AgentID | UserID]? # If set, only deliver events from these authors.

  # Lookback (for initial delivery of recent history on subscription creation)
  lookback_epochs:   u64?                 # If set, deliver events from the last N epochs on subscribe.
}
```

### 7.5 Delivery Configuration

```
DeliveryConfig {
  mode:            DeliveryMode           # See modes below.
  endpoint:        string?                # Required for WEBHOOK and GRPC modes. URL or address.
  format:          DeliveryFormat         # JSON | CBOR | PROTO

  # Reliability
  retry_policy:    RetryPolicy?           # If absent, default policy applies.
  dead_letter:     StreamID?              # If set, undeliverable events are written here.

  # Batching
  batch_max_size:  u64?                  # Max events per batch. Default 1 (unbatched).
  batch_window_ms: u64?                  # Time window to accumulate batch. Default 0.
}

DeliveryMode ::=
  | "webhook"      # HTTP POST to endpoint. Body: DeliveryPayload.
  | "grpc"         # gRPC stream to endpoint.
  | "event-queue"  # Write event to a WalrusOS-managed event queue (polled by subscriber).
  | "stream-write" # Write a RECEIPT event to a specified target Memory Stream.

RetryPolicy ::= {
  max_attempts:    u8       # Maximum delivery attempts. 1–10. Default 3.
  backoff_base_ms: u64      # Base retry delay in milliseconds. Default 1000.
  backoff_factor:  float    # Exponential backoff multiplier. Default 2.0.
}

DeliveryFormat ::= "json" | "cbor" | "proto"
```

### 7.6 Delivery Payload

When an event is delivered, the payload MUST contain the following structure:

```
DeliveryPayload {
  subscription_id:   SubscriptionID
  delivery_sequence: u64               # Monotonically increasing per subscription.
  delivered_unix_ms: u64
  event:             MemoryEvent       # The full event record.
  artifact_stubs:    [ArtifactStub]   # Metadata for each artifact (content NOT included).
                                        # Subscriber fetches full content via Artifact ID.
}

ArtifactStub {
  artifact_id:   ArtifactID
  content_type:  MediaType
  byte_size:     u64
  encrypted:     bool
  certified:     bool
}
```

Full Artifact content is NOT included in delivery payloads. Subscribers retrieve Artifact content separately using the `artifact_id` via the WalrusOS Artifact API. This keeps delivery payloads small regardless of blob size.

### 7.7 Invariants

- A Subscription MUST reference a valid `cap_id` of type `SubscriptionCap` that covers the streams or workspace in the filter. An expired or revoked `cap_id` MUST cause the subscription to be automatically CANCELLED.
- A Subscription MUST NOT be created with an empty filter (no stream_ids, no agent_ids, and no workspace_id). An unfiltered subscription is prohibited.
- Delivery MUST be at-least-once: if a delivery fails all retry attempts, the event MUST be written to the `dead_letter` stream if configured, or the subscription MUST be marked as PAUSED with a delivery failure reason.
- `delivery_sequence` MUST be monotonically increasing per subscription and MUST NOT have gaps. Gaps indicate missed events and MUST be treated as protocol errors.
- A Subscription in CANCELLED or EXPIRED status MUST NOT deliver further events. Any in-flight deliveries at the time of cancellation MAY complete.
- A Subscription's filter MUST be evaluated server-side. The subscriber MUST NOT be required to filter events that are delivered to it.

---

## 8. Primitive: Workspace

### 8.1 Definition

A **Workspace** is a named, policy-governed shared environment that groups one or more Agents and Users under a common access control boundary. A Workspace provides a shared coordination context: member agents share a Workspace-scoped event namespace, MAY share Artifacts via a workspace-level index, and operate under a common retention and governance policy. A Workspace does not own Memory Streams — Agents own their own Memory Streams. A Workspace provides the policy layer that governs cross-agent memory access and collaboration within its boundary.

A Workspace is analogous to a git organization: it contains repositories (agents), defines access policies, and provides a shared namespace — but each repository manages its own content independently.

### 8.2 Identity

```
workspace-id ::= "ws/" <name>

name ::= [a-z0-9][a-z0-9-]{0,62}

Example:
  ws/marketing-crew
  ws/research-lab
  ws/prod-autonomous-systems
```

Workspace IDs MUST be unique within a WalrusOS network. A Workspace ID MAY be renamed by a holder of a `WorkspaceAdminCap` over that workspace.

### 8.3 Schema

```
Workspace {
  # Identity
  id:              WorkspaceID           # Globally unique workspace identifier.
  version:         u64                   # MONOTONIC.
  sui_object_id:   SuiObjectID          # IMMUTABLE. On-chain WorkspaceObject.

  # Metadata
  display_name:    string               # Human-readable label. 128 chars max.
  description:     string?             # Purpose description. 2048 chars max.
  created_epoch:   u64                 # IMMUTABLE.
  created_unix_ms: u64                 # IMMUTABLE.

  # Membership
  admin_user_ids:  [UserID]            # Users with WorkspaceAdminCap. 1 MUST always be present.
  member_agents:   [AgentID]           # Agents belonging to this workspace.
  member_users:    [UserID]            # Users with WorkspaceMemberCap.

  # Lifecycle
  status:          WorkspaceStatus      # ACTIVE | LOCKED | DISSOLVING | DISSOLVED

  # Policy
  policy:          WorkspacePolicy      # Governing rules for this workspace.

  # Shared resources
  shared_index:    ArtifactIndexID?    # A workspace-scoped Artifact index for shared knowledge.
  event_log:       StreamID?           # A workspace-level event stream for coordination events.

  # Economics
  wal_pool:        Balance<WAL>?       # Optional shared WAL pool for member agents.
  billing_mode:    BillingMode         # How storage costs are covered within this workspace.
}
```

### 8.4 Workspace Policy

```
WorkspacePolicy {
  # Memory access defaults
  default_read_scope:  ReadScope       # Who can read member agents' memory by default.
  default_write_scope: WriteScope      # Who can append to a member agent's stream by default.

  # Cross-agent memory
  cross_agent_read:    bool            # If true, member agents can read each other's streams
                                        # (subject to individual MemoryReadCap grants).
  cross_agent_write:   bool            # If true, member agents can append to each other's streams
                                        # (subject to individual MemoryWriteCap grants).

  # Encryption requirements
  require_encryption:  [MemoryClass]  # Memory classes that MUST be encrypted within this workspace.

  # Retention defaults (applied to new agents joining this workspace)
  default_retention:   RetentionPolicy

  # Governance
  governance_mode:     GovernanceMode  # How policy changes and high-impact actions are authorized.
  required_approvals:  u8?            # For MULTISIG governance mode: minimum approvals needed.

  # Agent constraints
  max_agents:          u64?           # Maximum number of member agents. NULL = unlimited.
  allowed_frameworks:  [string]?      # If set, only agents with these runtime_hints.framework values
                                        # are permitted. NULL = any framework.
}

ReadScope ::=
  | "private"       # Only the agent itself can read
  | "workspace"     # All workspace members can read
  | "public"        # Anyone can read

WriteScope ::=
  | "self-only"     # Only the agent itself can write
  | "workspace"     # Any workspace member with appropriate cap can write
  | "operator"      # Only holders of OperatorCap can write on behalf of the agent

GovernanceMode ::=
  | "unilateral"    # Any WorkspaceAdmin can make changes immediately
  | "multisig"      # Changes require required_approvals count from admin_user_ids

BillingMode ::=
  | "per-agent"     # Each agent pays for its own storage from its own WAL treasury
  | "pooled"        # All storage costs are deducted from the workspace wal_pool
  | "split"         # Base costs pooled; overages per-agent
```

### 8.5 Lifecycle

```
State Machine:

  ACTIVE ──[lock]──────► LOCKED ──[unlock]──► ACTIVE
         │
         └──[dissolve]──► DISSOLVING ──[cleanup complete]──► DISSOLVED

States:
  ACTIVE       Normal operating state.
               Member agents MUST be functional.
               Policy MAY be modified per GovernanceMode.

  LOCKED       Administrative hold. No new members may join.
               Existing members continue operating.
               Policy MUST NOT be modified while LOCKED.
               Used for: audit, compliance review, incident response.

  DISSOLVING   Workspace is being shut down.
               No new agents MAY join.
               Existing agents MUST complete in-flight tasks.
               All shared resources MUST be transferred or archived
               before transitioning to DISSOLVED.

  DISSOLVED    Terminal state. Workspace no longer exists.
               All member agents MUST have been either transferred to
               another workspace or deprecated before dissolution.
               The Workspace ID MUST NOT be reused.
```

### 8.6 Workspace Event Log

If a Workspace has an `event_log` configured, the following SYSTEM-class Memory Events MUST be written to it automatically:

```
Workspace Event Log Events:

Event Type    | Trigger                                      | Required Annotations
──────────────┼──────────────────────────────────────────────┼─────────────────────────────────────
SYSTEM        | Agent joins workspace                        | agent_id, join_epoch
SYSTEM        | Agent leaves workspace                       | agent_id, leave_epoch, reason
SYSTEM        | Agent PAUSED within workspace                | agent_id, paused_by, reason
SYSTEM        | Agent DEPRECATED within workspace            | agent_id, deprecated_by, successor_id?
SYSTEM        | Policy modified                              | modified_by, changed_fields[...]
SYSTEM        | Workspace LOCKED                             | locked_by, reason
SYSTEM        | Workspace DISSOLVING initiated               | initiated_by
USER_ANNOTATION | Admin annotated workspace event            | annotator_id, target_event_id
```

### 8.7 Invariants

- A Workspace MUST have at least one `admin_user_id` at all times. A workspace with zero admins is permanently ungovernable and is a protocol violation.
- A Workspace in `DISSOLVED` status MUST NOT be reactivated. Dissolution is irreversible.
- A Workspace MUST NOT dissolve while any member agent is in ACTIVE or PAUSED status. All agents MUST be DEPRECATED or transferred before dissolution.
- A Workspace's `billing_mode = "pooled"` MUST NOT be active when `wal_pool` is empty. Implementations MUST alert at a two-epoch reserve threshold.
- Cross-agent memory access within a workspace MUST still require explicit Capability grants even when `cross_agent_read = true`. The `cross_agent_read` flag is a policy enabler (it allows the cap to be issued); it is NOT itself an authorization for access.
- A Workspace's `event_log` stream MUST be sealed when the workspace enters DISSOLVED status.

---

## 9. Identifier Grammar

All WalrusOS identifiers share a common grammar. Implementations MUST validate identifiers against this grammar before accepting them.

```
identifier  ::= kind "/" path ["@" version]
kind        ::= "agent" | "user" | "stream" | "artifact" | "event"
              | "cap" | "sub" | "ws"

path        ::= segment ("/" segment)*
segment     ::= [a-z0-9][a-z0-9-]{0,62}

version     ::= integer               # Used for artifact/event revisions where applicable

Content-addressed identifiers:
  artifact-id ::= "artifact/walrus:" hex64
  event-id    ::= "event/" hex64

Sui object references:
  sui-object  ::= "sui:" hex64        # 32-byte Sui object ID in hex

Walrus blob references:
  walrus-blob ::= "walrus:" hex64     # 32-byte Walrus blob ID in hex

hex64       ::= [0-9a-f]{64}         # 32 bytes in lowercase hex
hex16       ::= [0-9a-f]{16}         # 8 bytes in lowercase hex
hex8        ::= [0-9a-f]{8}          # 4 bytes in lowercase hex
```

Implementations MUST reject identifiers that:
- Contain uppercase letters.
- Contain characters outside the defined character sets.
- Have segments longer than 63 characters.
- Have a path depth greater than 8 segments.
- Are empty strings.

---

## 10. Epoch Model

WalrusOS adopts the Walrus epoch model directly. An epoch is the fundamental unit of time for storage lifecycle management.

```
Epoch Properties:
  Duration:     14 days (Mainnet). Subject to governance change.
  Numbering:    Monotonically increasing unsigned 64-bit integers beginning at 0.
  Source:       The current epoch is read from the Sui blockchain (TxContext.epoch),
                which in turn reflects the Walrus epoch clock.
  Immutability: Once an epoch has passed, its number MUST NOT be reassigned or modified.
```

Protocol operations that are epoch-sensitive:

```
Operation                   | Epoch semantics
────────────────────────────┼──────────────────────────────────────────────────────────
Capability validity check   | MUST reject if current_epoch > valid_until_epoch
Capability revocation check | MUST reject if current_epoch >= revoked_epoch
Artifact epoch lease        | MUST enforce that end_epoch >= current_epoch for read access
Subscription expiry         | MUST auto-cancel when current_epoch >= expires_epoch
Agent treasury check        | MUST alert when treasury covers < 2 epochs of projected cost
Agent status enforcement    | MUST transition agent to PENDING if treasury is empty and
                            | current_epoch > last_funded_epoch + 1
Memory Event timestamp      | MUST record the epoch from TxContext (on-chain verified time)
```

Implementations MUST NOT use wall-clock time as a substitute for epoch values in protocol-enforced operations. Wall-clock timestamps (unix_ms fields) are INFORMATIONAL only and MUST NOT be used for epoch-sensitive enforcement.

---

## 11. Cryptographic Primitives

### 11.1 Canonical Serialization

All content-addressed objects (Artifacts, Memory Events) MUST be canonically serialized before hashing. The CANONICAL serialization format is:

```
Format:       CBOR (RFC 8949), deterministic mode
Key ordering: Map keys MUST be sorted by byte string comparison of the encoded key.
Float format: All floats MUST be encoded in IEEE 754 double precision (64-bit).
Integer size: All integers MUST use the minimal CBOR encoding (no leading zero bytes).
Absent fields: Fields with value NULL or absent MUST be omitted from the CBOR map.
```

Implementations MUST use CBOR deterministic mode (RFC 8949 §4.2). Two CANONICAL serializations of the same logical object MUST produce identical byte sequences.

### 11.2 Hash Function

```
Content addressing:  sha3-256 (FIPS 202)
Output format:       Lowercase hex, 64 characters ("sha3-256:" prefix + hex)
```

### 11.3 Signature Schemes

```
Scheme         | Identifier      | Use case
───────────────┼─────────────────┼──────────────────────────────────────────────
ed25519        | "ed25519"       | Default agent and user signing key
secp256r1      | "secp256r1"     | Passkey / WebAuthn hardware binding
secp256k1      | "secp256k1"     | Legacy compatibility
multisig       | "multisig"      | M-of-N governance multisig
```

Signatures MUST be encoded as `<scheme>:<base64url-no-padding>`.

Message format for signing: All signatures MUST sign the sha3-256 hash of the CANONICAL serialization of the object being signed, prefixed with the ASCII string `"walrusos-v1:"` followed by the object type name:

```
message = sha3-256("walrusos-v1:" || object_type || ":" || canonical_cbor_bytes)
```

### 11.4 Encryption

```
Scheme         | Identifier      | Key type                        | Use case
───────────────┼─────────────────┼─────────────────────────────────┼────────────────────────
AES-256-GCM    | "aes-256-gcm"   | 256-bit symmetric key           | Client-side encryption
ChaCha20-Poly  | "chacha20-poly" | 256-bit symmetric key           | Alternative symmetric
Seal IBE       | "seal-ibe"      | Sui on-chain policy object ID   | Threshold IBE (Seal)
```

The nonce for AES-256-GCM MUST be 12 bytes, randomly generated per encryption operation. The nonce MUST be prepended to the ciphertext. The total stored format is: `nonce (12 bytes) || ciphertext || auth_tag (16 bytes)`.

---

## 12. Primitive Relationships

```
Relationship Map:

  User  ──[owns]──────────────────► Agent
  User  ──[holds]─────────────────► Capability (WorkspaceAdminCap, etc.)
  User  ──[administers]───────────► Workspace

  Agent ──[has exactly one]───────► MemoryStream
  Agent ──[is a member of]────────► Workspace (0 or 1)
  Agent ──[holds]─────────────────► Capability (MemoryWriteCap, MemoryReadCap)
  Agent ──[creates]───────────────► Artifact
  Agent ──[appends]───────────────► MemoryEvent → MemoryStream
  Agent ──[holds]─────────────────► Subscription

  MemoryStream ──[is a sequence of]─► MemoryEvent (ordered by sequence, linked by parent_id)

  MemoryEvent ──[references]──────► Artifact (1 or more, via ArtifactRef)
  MemoryEvent ──[MAY supersede]───► MemoryEvent (CORRECTION events)
  MemoryEvent ──[MAY derive from]─► [MemoryEvent] (CONSOLIDATION events)

  Artifact ──[stored on]──────────► Walrus (off-chain storage)
  Artifact ──[registered as]──────► Sui Blob Object (on-chain metadata)

  Capability ──[governs access to]► Agent | MemoryStream | Workspace | Artifact
  Capability ──[issued by]────────► User | Agent (as grantor)
  Capability ──[held by]──────────► User | Agent (as grantee)

  Subscription ──[watches]────────► MemoryStream | Workspace
  Subscription ──[authorized by]──► SubscriptionCap
  Subscription ──[delivers to]────► User | Agent (as subscriber)

  Workspace ──[contains]──────────► Agent (0 or more)
  Workspace ──[contains]──────────► User (as members or admins)
  Workspace ──[MAY have]──────────► MemoryStream (shared event log)
  Workspace ──[governed by]───────► WorkspacePolicy

  WalrusOS Protocol
    └── Substrate 1: Sui Blockchain
    │     ├── Agent Identity Objects (AgentIdentityObject)
    │     ├── Memory Cursor Objects (MemoryCursor)
    │     ├── Capability Objects (MemoryWriteCap, OperatorCap, etc.)
    │     ├── Blob Metadata Objects (Walrus Blob Objects)
    │     ├── Workspace Objects (WorkspaceObject)
    │     └── Event System (all protocol events)
    │
    └── Substrate 2: Walrus Storage Network
          ├── Artifact content (encrypted or plaintext blobs)
          ├── Checkpoint blobs
          ├── Embedding blobs
          └── Agent specification blobs
```

---

## 13. Error Taxonomy

All WalrusOS protocol errors are classified in a hierarchy. Implementations MUST use these error codes and MUST NOT substitute custom error codes for protocol-defined errors.

```
Category              | Code                           | Meaning
──────────────────────┼────────────────────────────────┼──────────────────────────────────────────
Identity              | AGENT_NOT_FOUND                | No agent with the given ID exists.
                      | USER_NOT_FOUND                 | No user with the given ID exists.
                      | WORKSPACE_NOT_FOUND            | No workspace with the given ID exists.
                      | IDENTIFIER_INVALID             | Identifier does not conform to §9 grammar.

Authorization         | CAPABILITY_MISSING             | Required capability not presented.
                      | CAPABILITY_EXPIRED             | Cap's valid_until_epoch has passed.
                      | CAPABILITY_REVOKED             | Cap has been revoked.
                      | CAPABILITY_SCOPE_INSUFFICIENT  | Cap does not cover the requested permission.
                      | CAPABILITY_NOT_TRANSFERABLE    | Attempted transfer of soulbound cap.
                      | CAPABILITY_NOT_DELEGATABLE     | Attempted delegation from non-delegatable cap.
                      | ESCALATION_ATTEMPT             | Sub-cap scope exceeds parent cap scope.

State Machine         | INVALID_TRANSITION             | Requested state transition is not permitted.
                      | AGENT_NOT_ACTIVE               | Operation requires ACTIVE agent status.
                      | AGENT_PAUSED                   | Agent is PAUSED; write operations rejected.
                      | AGENT_DEPRECATED               | Agent is DEPRECATED; all writes rejected.
                      | WORKSPACE_LOCKED               | Workspace is LOCKED; modifications rejected.
                      | STREAM_SEALED                  | Memory Stream is sealed; no new events.

Append Protocol       | CONCURRENT_WRITE_CONFLICT      | parent_id does not match current stream head.
                      | ARTIFACT_NOT_CERTIFIED         | Referenced artifact lacks availability cert.
                      | SIGNATURE_INVALID              | Author signature verification failed.
                      | GENESIS_CONSTRAINT_VIOLATION   | Genesis event constraints not satisfied.
                      | SEQUENCE_GAP                   | Sequence number is non-contiguous.

Artifact              | ARTIFACT_NOT_FOUND             | No artifact with the given ID on Walrus.
                      | CONTENT_HASH_MISMATCH          | Artifact content does not match stored hash.
                      | ARTIFACT_EXPIRED               | Artifact's epoch lease has expired.
                      | STORAGE_BUDGET_EXCEEDED        | Agent's WAL treasury insufficient.

Subscription          | SUBSCRIPTION_FILTER_EMPTY      | Filter matches no streams or workspaces.
                      | DELIVERY_FAILED_PERMANENTLY    | All retry attempts exhausted; event undeliverable.
                      | SUBSCRIPTION_CAP_INVALID       | SubscriptionCap does not cover the filter scope.

Economics             | TREASURY_INSUFFICIENT          | WAL balance cannot cover required storage cost.
                      | BUDGET_LIMIT_EXCEEDED          | Operation would exceed configured spending limit.

Protocol              | CANONICAL_SERIALIZATION_ERROR  | Object cannot be canonically serialized.
                      | EPOCH_VIOLATION                | Epoch-sensitive constraint violated.
                      | VERSION_CONFLICT               | Object version mismatch (optimistic concurrency).
                      | INVARIANT_VIOLATED             | A protocol invariant has been violated.
                                                        # This error MUST cause the operation to halt.
                                                        # Implementations SHOULD alert operators.
```

---

## Appendix A: Change Log

```
v0.1.0  2026-06-16  Initial draft. All eight primitives defined.
```

## Appendix B: Open Questions

The following questions are unresolved in this draft and MUST be resolved before v1.0:

```
B.1  Should MemoryStream support forking (like git branches)?
     Current spec: no forking; one canonical chain per agent.
     Alternative: allow named forks for agent experimentation.

B.2  Should Artifact deletion from Walrus be surfaced in the MemoryStream?
     Current spec: tombstoned events are marked but event record persists.
     Question: should a SYSTEM event of type ARCHIVE be emitted on expiry?

B.3  Maximum stream depth.
     Current spec: no defined maximum event_count.
     Risk: arbitrarily long chains may be impractical to traverse on-chain.
     Alternative: define a consolidation obligation at every N events.

B.4  Cross-workspace memory access.
     Current spec: Capabilities can be issued across workspace boundaries
     but the spec does not define a cross-workspace discovery protocol.
     This needs a dedicated section.

B.5  Network identity.
     Current spec assumes a single WalrusOS network.
     Multi-network / multi-chain deployments are not addressed.

B.6  Dispute resolution for INVARIANT_VIOLATED errors.
     Who arbitrates? The protocol does not define a dispute layer.
```

---

*End of Specification*
