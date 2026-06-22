# WalrusOS SDK API Reference

This document is auto-generated from the Python source code.

## class `WalrusOS`
Top-level WalrusOS runtime.

Wires storage, ledger, and vector adapters together into a single
MemoryEngine and exposes the workspace() API.

In production mode (use_mocks=False, the default):
  - Storage: WalrusAdapter (Walrus testnet/mainnet HTTP)
  - Ledger:  SuiLedgerAdapter (SQLite + Sui event anchoring)
  - Vector:  InMemoryVector (TF-IDF, zero deps — swap for embedding model if needed)

In mock mode (use_mocks=True):
  - Storage: InMemoryStorage
  - Ledger:  InMemoryLedger
  - Vector:  InMemoryVector
  Used for unit tests and offline development.

### `def __init__(self, use_mocks: 'Optional[bool]' = None, publisher_url: 'Optional[str]' = None, aggregator_url: 'Optional[str]' = None, walrus_epochs: 'Optional[int]' = None, sui_rpc_url: 'Optional[str]' = None, package_id: 'Optional[str]' = None, db_path: 'Optional[str]' = None) -> 'None'`
### `def workspace(self, name: 'str') -> 'WorkspaceClient'`
Open a workspace context.

Phase 2: owner_wallet is resolved from the connected Sui identity
and passed to WorkspaceClient so every agent created within this
workspace has a correctly anchored identity.

Example::

    ws     = runtime.workspace("research")
    agent  = ws.agent("Researcher")
    stream = ws.stream("papers")

---

## class `WorkspaceClient`
Public SDK facade mapping to a WalrusOS Workspace.

The WorkspaceClient provides access to agents and streams. It uses 
Lazy Initialization, meaning the workspace is only physically registered 
in the ledger when an actual event is appended.

### `def __init__(self, engine: 'EventStoreEngine', name: 'str', owner_wallet: 'str' = '') -> 'None'`
### `def agent(self, name: 'str') -> 'AgentClient'`
Return an AgentClient for the named agent. 
Initialization happens lazily when the agent performs an action.

Args:
    name: The human-readable name of the agent.
    
Returns:
    An instance of `AgentClient`.

### `def list_agents(self) -> 'list'`
Return all persistent AgentIdentity records for this workspace.

### `def stream(self, name: 'str') -> 'StreamClient'`
Return a StreamClient for the named stream.

Args:
    name: The human-readable name of the stream.
    
Returns:
    An instance of `StreamClient`.

---

## class `AgentClient`
Fluent handle for a named Agent within a workspace.

### `def __init__(self, engine: 'EventStoreEngine', workspace_name: 'str', agent_name: 'str', owner_wallet: 'str' = '') -> 'None'`
### `def export_identity(self) -> 'Dict[str, Any]'`
Return a JSON-serializable dict containing the full agent identity.

Useful for serialization, inter-process handoff, and debugging.

### `def get_identity(self) -> 'AgentIdentity'`
Return the AgentIdentity projection. 
Automatically initializes the agent if it hasn't been already.

Returns:
    AgentIdentity object containing the agent's reputation and capabilities.

### `def initialize(self)`
Manually trigger initialization. 
Deprecated: Initialization is now handled lazily on first use.

### `def pause(self) -> 'None'`
Pause this agent.

A paused agent cannot publish events.  Call ``resume()`` to reactivate.
The status is persisted to SQLite immediately.

### `def publish(self, stream: 'StreamClient', payload: 'Dict[str, Any]', class_type: 'str' = 'working') -> 'ProtocolEvent'`
Append a memory event to ``stream`` on behalf of this agent.

### `def resume(self) -> 'None'`
Resume a paused agent (set status back to active).

### `def stream(self, name: 'str') -> 'StreamClient'`
Return a StreamClient bound to this Agent, automatically 
providing the agent's identity and signing capabilities for appending events.

Args:
    name: Human-readable name for the stream.
    
Returns:
    StreamClient bound to this agent.

### `def subscribe(self, stream: 'StreamClient', callback: 'SubscriberCallback', poll_interval: 'float' = 0.5) -> "'asyncio.Task[None]'"`
Subscribe to new events on ``stream`` via async polling.

The callback receives the full payload dict of each new event.
Events published *before* ``subscribe()`` is called are NOT delivered
(use ``stream.timeline()`` to catch up first).

Returns an ``asyncio.Task`` — call ``.cancel()`` to stop listening.

### `def terminate(self) -> 'None'`
Permanently terminate this agent.

A terminated agent cannot publish events and cannot be resumed.
The status is persisted to SQLite.

### `def unsubscribe(self, stream: 'StreamClient') -> 'None'`
Cancel the active subscription for ``stream``, if any.

### `def unsubscribe_all(self) -> 'None'`
Cancel all active subscriptions for this agent.

### `@property agent_id`
The agent's persistent UUID (for stream registration).

### `@property identity`
Return the AgentIdentity projection. May raise AgentNotFoundError if not initialized.

---

## class `StreamClient`
Fluent handle for a named MemoryStream within a workspace.

Stream IDs are derived deterministically from
``<workspace>.<stream_name>`` so the same name always resolves to the
same UUID across process restarts.

### `def __init__(self, engine: 'EventStoreEngine', workspace_name: 'str', stream_name: 'str') -> 'None'`
### `def append(self, payload: 'Dict[str, Any]', class_type: 'str' = 'working') -> 'ProtocolEvent'`
Append a new event payload to this stream.

Note: This method is only available if the StreamClient was created 
by an AgentClient (e.g., `agent.stream('my-stream')`). If created from 
the WorkspaceClient directly, the stream is read-only.

Args:
    payload: A dictionary of arbitrary JSON-serializable data.
    class_type: Optional classification (e.g., "working", "final").
    
Returns:
    The signed and anchored ProtocolEvent.
    
Raises:
    WalrusOSError: If the stream is read-only (not bound to an agent).

### `def checkpoint(self) -> 'str'`
Save a lightweight checkpoint. Returns blob_id.

### `def fork(self, from_event_id: 'str', new_agent_id: 'uuid.UUID') -> "'StreamClient'"`
Create a new stream branching from ``from_event_id``.

### `def initialize(self, agent_id: 'uuid.UUID') -> 'None'`
Deprecated: Explicit initialization is no longer needed.

### `def merge(self, source_stream_id: 'uuid.UUID') -> 'ProtocolEvent'`
Merge another branch into this stream.

### `def read_event(self, event_id: 'str') -> 'Dict[str, Any]'`
Fetch a single event payload by its ID.

### `def replay(self, up_to_epoch: 'Optional[int]' = None, from_epoch: 'int' = 1) -> 'List[Dict[str, Any]]'`
Replay events, optionally bounded by epoch range.

### `def resume(self, checkpoint_blob_id: 'str') -> 'None'`
Restore in-engine epoch state from a checkpoint blob.

### `def search(self, query: 'str', limit: 'int' = 5) -> 'List[Dict[str, Any]]'`
Semantic search across events indexed in this engine.

### `def snapshot(self) -> 'str'`
Save a full snapshot. Returns blob_id.

### `def summarize(self, max_events: 'int' = 20) -> 'str'`
Human-readable digest of recent stream events.

### `def timeline(self) -> 'List[Tuple[ProtocolEvent, Dict[str, Any]]]'`
Fetch the chronological list of all (event, payload) pairs.

---

## class `WalrusOSError`
Base class for all WalrusOS SDK exceptions.

---

## class `AgentNotFoundError`
Raised when an agent identity cannot be resolved or is missing from the stream.

---

## class `CryptographicVerificationError`
Raised when an event signature, hash, or public key fails mathematical verification.

---

## class `CapabilityRevokedError`
Raised when an agent attempts an action using a revoked or expired capability.

---
