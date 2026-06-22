/// WalrusOS Identity Module
///
/// Manages Workspaces, Agents, and Capability tokens on Sui.
///
/// Objects:
///   Workspace     — top-level namespace owned by a wallet
///   AgentIdentity — first-class persistent AI agent with cryptographic identity
///   Capability    — transferable permission token with bitmask + expiry
///
/// Phase 2 additions to Agent:
///   public_key        — Ed25519 public key bytes (32 bytes)
///   trust_root        — SHA-256(owner:workspace:name) as 32-byte vector
///   status            — 0=active, 1=paused, 2=terminated
///   execution_counter — number of publish() calls
///   memory_counter    — number of MemoryEvents appended
///   artifact_counter  — number of Walrus blobs stored
///
/// Bitmask values:
///   0b0001 (1)  = READ
///   0b0010 (2)  = WRITE
///   0b0100 (4)  = FORK
///   0b1000 (8)  = MERGE
///   0b1111 (15) = ALL
#[allow(unused_const, lint(self_transfer))]
module walrusos::identity {
    use sui::object::{Self, UID};
    use sui::transfer;
    use sui::tx_context::{Self, TxContext};
    use sui::event;
    use std::string::String;

    // ── Capability bitmask constants ──────────────────────────────────────────
    const CAP_READ:  u64 = 1;
    const CAP_WRITE: u64 = 2;
    const CAP_FORK:  u64 = 4;
    const CAP_MERGE: u64 = 8;
    const CAP_ALL:   u64 = 15;

    // ── Agent status constants ────────────────────────────────────────────────
    const AGENT_ACTIVE:     u8 = 0;
    const AGENT_PAUSED:     u8 = 1;
    const AGENT_TERMINATED: u8 = 2;

    // ── Error codes ───────────────────────────────────────────────────────────
    const ECapabilityExpired:        u64 = 1;
    const EInsufficientPermissions:  u64 = 2;
    const EAgentNotActive:           u64 = 3;
    const EAgentAlreadyTerminated:   u64 = 4;
    const EInvalidStatus:            u64 = 5;
    const ENotOwner:                 u64 = 6;

    // ── Structs ───────────────────────────────────────────────────────────────

    /// Top-level namespace. Owned by the creating wallet.
    public struct Workspace has key, store {
        id: UID,
        name: String,
        /// How many Sui epochs blobs in this workspace should be retained.
        retention_epochs: u64,
    }

    /// First-class persistent AI agent with cryptographic identity.
    ///
    /// Phase 2: Extends the minimal Agent with:
    ///   - Ed25519 public key (enables off-chain signature verification)
    ///   - Trust root (deterministic SHA-256 fingerprint)
    ///   - Status lifecycle
    ///   - Independent usage counters
    public struct AgentIdentity has key, store {
        id: UID,
        workspace_id:      address,
        name:              String,
        /// Ed25519 public key bytes (32 bytes, raw scalar).
        public_key:        vector<u8>,
        /// SHA-256(owner_wallet:workspace_id:agent_name) — 32 bytes.
        trust_root:        vector<u8>,
        /// Agent status: 0=active, 1=paused, 2=terminated.
        status:            u8,
        /// Number of publish() calls made by this agent.
        execution_counter: u64,
        /// Number of MemoryEvents appended by this agent.
        memory_counter:    u64,
        /// Number of Walrus blobs stored by this agent.
        artifact_counter:  u64,
    }

    /// Transferable permission token.
    /// ``valid_until_epoch == 0`` means the capability never expires.
    public struct Capability has key {
        id: UID,
        target_stream_id:  address,
        verb_bitmask:      u64,
        valid_until_epoch: u64,
    }

    // ── Events ────────────────────────────────────────────────────────────────

    public struct WorkspaceCreated has copy, drop {
        workspace_id: address,
        name:         String,
        owner:        address,
    }

    public struct AgentRegistered has copy, drop {
        agent_id:     address,
        workspace_id: address,
        name:         String,
        /// Hex-encoded public key emitted for off-chain indexing.
        public_key:   vector<u8>,
        trust_root:   vector<u8>,
    }

    public struct AgentStatusChanged has copy, drop {
        agent_id:   address,
        old_status: u8,
        new_status: u8,
        owner:      address,
    }

    public struct AgentCountersUpdated has copy, drop {
        agent_id:          address,
        execution_counter: u64,
        memory_counter:    u64,
        artifact_counter:  u64,
    }

    public struct CapabilityDelegated has copy, drop {
        capability_id:    address,
        target_stream_id: address,
        verb_bitmask:     u64,
        recipient:        address,
    }

    public struct CapabilityRevoked has copy, drop {
        target_stream_id: address,
        verb_bitmask:     u64,
    }

    // ── Entry functions ───────────────────────────────────────────────────────

    /// Create a new Workspace and transfer it to the caller.
    public fun create_workspace(name: String, ctx: &mut TxContext) {
        let workspace_uid = object::new(ctx);
        let workspace_id  = object::uid_to_address(&workspace_uid);
        let workspace = Workspace {
            id: workspace_uid,
            name,
            retention_epochs: 365,
        };
        let owner = tx_context::sender(ctx);
        transfer::transfer(workspace, owner);
        event::emit(WorkspaceCreated { workspace_id, name, owner });
    }

    /// Register an AgentIdentity in a Workspace.
    ///
    /// Phase 2: Creates a full AgentIdentity object with:
    ///   - Ed25519 public_key embedded in the object
    ///   - trust_root for deterministic global identity anchoring
    ///   - All counters initialised to 0
    ///   - Status set to AGENT_ACTIVE
    ///
    /// The object is transferred to the caller (wallet = owner).
    public fun register_agent(
        workspace_id: address,
        name:         String,
        public_key:   vector<u8>,
        trust_root:   vector<u8>,
        ctx:          &mut TxContext,
    ) {
        let agent_uid = object::new(ctx);
        let agent_id  = object::uid_to_address(&agent_uid);

        let agent = AgentIdentity {
            id:                agent_uid,
            workspace_id,
            name,
            public_key,
            trust_root,
            status:            AGENT_ACTIVE,
            execution_counter: 0,
            memory_counter:    0,
            artifact_counter:  0,
        };

        let owner = tx_context::sender(ctx);
        transfer::transfer(agent, owner);

        event::emit(AgentRegistered {
            agent_id,
            workspace_id,
            name,
            public_key,
            trust_root,
        });
    }

    /// Update an AgentIdentity's status.
    ///
    /// Valid transitions:
    ///   active (0) → paused (1)
    ///   active (0) → terminated (2)
    ///   paused (1) → active (0)
    ///   paused (1) → terminated (2)
    ///   terminated (2) → (no further changes allowed)
    ///
    /// Only the agent owner can call this.
    public fun update_agent_status(
        agent:      &mut AgentIdentity,
        new_status: u8,
        ctx:        &mut TxContext,
    ) {
        assert!(agent.status != AGENT_TERMINATED, EAgentAlreadyTerminated);
        assert!(
            new_status == AGENT_ACTIVE ||
            new_status == AGENT_PAUSED ||
            new_status == AGENT_TERMINATED,
            EInvalidStatus
        );

        let old_status = agent.status;
        agent.status   = new_status;

        event::emit(AgentStatusChanged {
            agent_id:   object::uid_to_address(&agent.id),
            old_status,
            new_status,
            owner:      tx_context::sender(ctx),
        });
    }

    /// Increment usage counters for an AgentIdentity.
    ///
    /// Called after each publish() / event append / blob store operation.
    /// The caller must own the agent object.
    public fun increment_counters(
        agent:     &mut AgentIdentity,
        execution: u64,
        memory:    u64,
        artifact:  u64,
        _ctx:      &mut TxContext,
    ) {
        assert!(agent.status == AGENT_ACTIVE, EAgentNotActive);

        agent.execution_counter = agent.execution_counter + execution;
        agent.memory_counter    = agent.memory_counter    + memory;
        agent.artifact_counter  = agent.artifact_counter  + artifact;

        event::emit(AgentCountersUpdated {
            agent_id:          object::uid_to_address(&agent.id),
            execution_counter: agent.execution_counter,
            memory_counter:    agent.memory_counter,
            artifact_counter:  agent.artifact_counter,
        });
    }

    /// Delegate a Capability token to ``recipient`` for ``target_stream``.
    ///
    /// ``valid_until_epoch = 0`` means never expires.
    /// Set to a future Sui epoch to create an expiring capability.
    public fun delegate_capability(
        target_stream:     address,
        bitmask:           u64,
        recipient:         address,
        valid_until_epoch: u64,
        ctx:               &mut TxContext,
    ) {
        let cap_uid = object::new(ctx);
        let cap_id  = object::uid_to_address(&cap_uid);
        let cap = Capability {
            id: cap_uid,
            target_stream_id: target_stream,
            verb_bitmask:     bitmask,
            valid_until_epoch,
        };
        transfer::transfer(cap, recipient);
        event::emit(CapabilityDelegated {
            capability_id:    cap_id,
            target_stream_id: target_stream,
            verb_bitmask:     bitmask,
            recipient,
        });
    }

    /// Revoke a Capability by consuming and destroying the object.
    ///
    /// The capability must be owned by the transaction sender.
    /// After this call, the capability object no longer exists on-chain.
    public fun revoke_capability(cap: Capability, _ctx: &mut TxContext) {
        let Capability { id, target_stream_id, verb_bitmask, valid_until_epoch: _ } = cap;
        event::emit(CapabilityRevoked { target_stream_id, verb_bitmask });
        object::delete(id);
    }

    /// Public function allowing other modules (like memory) to mint and transfer a capability.
    /// Used by `memory::create_stream` to issue an initial capability to the creator.
    public fun mint_and_transfer_capability(
        target_stream:     address,
        bitmask:           u64,
        valid_until_epoch: u64,
        recipient:         address,
        ctx:               &mut TxContext,
    ) {
        let cap = Capability {
            id: object::new(ctx),
            target_stream_id: target_stream,
            verb_bitmask:     bitmask,
            valid_until_epoch,
        };
        transfer::transfer(cap, recipient);
    }

    // ── Accessor functions ────────────────────────────────────────────────────

    /// Check whether a capability is valid for a given verb at the current epoch.
    public fun has_permission(
        cap:           &Capability,
        verb:          u64,
        current_epoch: u64,
    ): bool {
        let not_expired = cap.valid_until_epoch == 0 || current_epoch <= cap.valid_until_epoch;
        let has_verb    = (cap.verb_bitmask & verb) != 0;
        not_expired && has_verb
    }

    /// Return the agent's status code.
    public fun agent_status(agent: &AgentIdentity): u8 {
        agent.status
    }

    /// Return whether the agent is currently active.
    public fun is_agent_active(agent: &AgentIdentity): bool {
        agent.status == AGENT_ACTIVE
    }

    /// Return the agent's public key bytes.
    public fun agent_public_key(agent: &AgentIdentity): &vector<u8> {
        &agent.public_key
    }

    /// Return the agent's trust root bytes.
    public fun agent_trust_root(agent: &AgentIdentity): &vector<u8> {
        &agent.trust_root
    }

    /// Return the agent's workspace id.
    public fun agent_workspace_id(agent: &AgentIdentity): address {
        agent.workspace_id
    }

    /// Return the capability's target stream id.
    public fun cap_target_stream_id(cap: &Capability): address {
        cap.target_stream_id
    }

    /// Expose the CAP_WRITE bitmask value.
    public fun verb_write(): u64 {
        CAP_WRITE
    }
}
