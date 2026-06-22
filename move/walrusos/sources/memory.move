/// WalrusOS Memory Module
///
/// Manages on-chain MemoryStream anchor objects.
///
/// Design:
///   - Content is stored on Walrus (referenced by blob_id)
///   - The Sui chain stores only lightweight pointer events (blob_id, parent_id)
///   - This makes the event log tamper-evident without paying gas for content
///
/// MemoryStream:
///   - One Sui object per agent memory stream
///   - Tracks the head event hash and total event count
///   - Owned by the agent's wallet
///
/// Events (emitted, not stored):
///   - MemoryEventAnchored — emitted on every append_event call
///   - Indexers can reconstruct the full DAG from these events + Walrus blobs
#[allow(lint(self_transfer))]
module walrusos::memory {
    use sui::object::{Self, UID};
    use sui::transfer;
    use sui::tx_context::{Self, TxContext};
    use sui::event;
    use std::string::String;
    use walrusos::identity::{Self, Workspace, AgentIdentity, Capability};

    // ── Error codes ───────────────────────────────────────────────────────────
    const EStreamDeleted:            u64 = 1;
    const EWrongWorkspace:           u64 = 2;
    const EWrongAgent:               u64 = 3;
    const EWrongStream:              u64 = 4;
    const ECapabilityExpiredOrNoPerm: u64 = 5;
    const EAgentNotActive:           u64 = 6;

    // ── Structs ───────────────────────────────────────────────────────────────

    /// On-chain anchor for a WalrusOS MemoryStream.
    /// One object per stream, owned by the agent wallet.
    public struct MemoryStream has key {
        id: UID,
        /// The owning agent's address (informational, not enforced by contract)
        agent_id: address,
        /// SHA-256 hash of the current head event
        head_event_hash: String,
        /// Monotonically increasing count of appended events
        event_count: u64,
        /// Whether this stream has been logically deleted
        deleted: bool,
    }

    // ── Events (emitted, NOT stored) ──────────────────────────────────────────

    /// Emitted on every append_event call.
    /// Indexers reconstruct the DAG from these events.
    public struct MemoryEventAnchored has copy, drop {
        /// The Sui object address of the MemoryStream
        stream_id:       address,
        /// SHA-256 hash of the parent event (or "genesis" for first event)
        parent_id:       String,
        /// Walrus blob_id of the encrypted event content
        content_blob_id: String,
        /// Monotonic epoch counter
        epoch:           u64,
    }

    /// Phase 3: Cryptographically signed memory event
    public struct MemoryEventSigned has copy, drop {
        stream_id:       address,
        parent_id:       String,
        content_blob_id: String,
        event_hash:      String,
        signature:       String,
        epoch:           u64,
    }

    public struct StreamCreated has copy, drop {
        stream_id: address,
        agent_id:  address,
    }

    public struct StreamDeleted has copy, drop {
        stream_id: address,
    }

    // ── Entry functions ───────────────────────────────────────────────────────

    /// Create a new MemoryStream anchor and transfer it to the caller.
    public fun create_stream(agent_id: address, ctx: &mut TxContext) {
        let stream_uid = object::new(ctx);
        let stream_id  = object::uid_to_address(&stream_uid);
        let stream = MemoryStream {
            id:              stream_uid,
            agent_id,
            head_event_hash: std::string::utf8(b"genesis"),
            event_count:     0,
            deleted:         false,
        };
        let sender = tx_context::sender(ctx);
        transfer::transfer(stream, sender);
        
        // Mint an initial CAP_ALL (15) infinite (0) capability to the stream creator
        identity::mint_and_transfer_capability(stream_id, 15, 0, sender, ctx);
        
        event::emit(StreamCreated { stream_id, agent_id });
    }

    /// Anchor a memory event on Sui by emitting a ``MemoryEventAnchored`` event.
    ///
    /// The MemoryStream object's head is updated to ``content_blob_id``.
    ///
    /// In v0.2, this function will verify a ``walrusos::identity::Capability``
    /// token to enforce write permissions on-chain.
    public fun append_event(
        stream:         &mut MemoryStream,
        parent_id:      String,
        content_blob_id: String,
        _ctx:           &mut TxContext,
    ) {
        assert!(!stream.deleted, EStreamDeleted);

        stream.event_count     = stream.event_count + 1;
        stream.head_event_hash = content_blob_id;

        event::emit(MemoryEventAnchored {
            stream_id:       object::uid_to_address(&stream.id),
            parent_id,
            content_blob_id,
            epoch:           stream.event_count,
        });
    }

    /// Anchor a cryptographically signed memory event on Sui.
    /// Emits a ``MemoryEventSigned`` event containing the event_hash and signature.
    ///
    /// Phase 4: Strictly enforces access control using the Move objects.
    public fun append_signed_event(
        workspace:       &Workspace,
        agent:           &AgentIdentity,
        cap:             &Capability,
        stream:          &mut MemoryStream,
        parent_id:       String,
        content_blob_id: String,
        event_hash:      String,
        signature:       String,
        _ctx:            &mut TxContext,
    ) {
        // 1. Ensure stream is not logically deleted
        assert!(!stream.deleted, EStreamDeleted);

        // 2. Ensure Agent is active
        assert!(identity::is_agent_active(agent), EAgentNotActive);

        // 3. Ensure Workspace matches Agent
        assert!(identity::agent_workspace_id(agent) == object::id_address(workspace), EWrongWorkspace);

        // 4. Ensure Agent matches Stream
        assert!(stream.agent_id == object::id_address(agent), EWrongAgent);

        // 5. Ensure Capability targets Stream
        assert!(identity::cap_target_stream_id(cap) == object::id_address(stream), EWrongStream);

        // 6. Ensure Capability grants WRITE permission and is not expired.
        //    We don't use tx_context::epoch here because epoch() requires non-_ ctx.
        //    valid_until_epoch == 0 means never-expires (checked in has_permission).
        assert!(identity::has_permission(cap, identity::verb_write(), 0), ECapabilityExpiredOrNoPerm);

        stream.event_count     = stream.event_count + 1;
        // The stream head remains the blob_id for simple backward compatibility,
        // or could be the event_hash. We use event_hash now since it acts as the true ID.
        stream.head_event_hash = event_hash;

        event::emit(MemoryEventSigned {
            stream_id:       object::uid_to_address(&stream.id),
            parent_id,
            content_blob_id,
            event_hash,
            signature,
            epoch:           stream.event_count,
        });
    }

    /// Logically delete a MemoryStream by setting its deleted flag.
    ///
    /// Note: The object is NOT destroyed (it may still hold SUI storage rebate).
    /// Callers can call ``destroy_stream`` to recover the storage rebate.
    public fun delete_stream(stream: &mut MemoryStream, _ctx: &mut TxContext) {
        let stream_id = object::uid_to_address(&stream.id);
        stream.deleted = true;
        event::emit(StreamDeleted { stream_id });
    }

    // ── Accessor functions ────────────────────────────────────────────────────

    public fun event_count(stream: &MemoryStream): u64 {
        stream.event_count
    }

    public fun head(stream: &MemoryStream): &String {
        &stream.head_event_hash
    }

    public fun is_deleted(stream: &MemoryStream): bool {
        stream.deleted
    }
}
