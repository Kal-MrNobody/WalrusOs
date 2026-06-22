/// WalrusOS Protocol Module
///
/// Anchors generalized ProtocolEvents to the Sui blockchain.
/// In the Event Sourcing architecture, this replaces `memory.move`'s MemoryEvent.
module walrusos::protocol {
    use sui::object::{Self, UID};
    use sui::transfer;
    use sui::tx_context::{Self, TxContext};
    use sui::event;
    use std::string::String;

    // ── Structs ───────────────────────────────────────────────────────────────

    /// Emitted on every ProtocolEvent.
    public struct ProtocolEventAnchored has copy, drop {
        event_id:      String,
        event_type:    String,
        workspace_id:  String,
        agent_id:      String,
        blob_id:       String,
        blob_hash:     String,
        parent_event:  String,
        previous_hash: String,
        signature:     String,
    }

    /// On-chain Global Ledger Anchor for the Event Stream.
    /// Tracks the latest event hash to form a global DAG.
    public struct LedgerAnchor has key {
        id: UID,
        latest_event_hash: String,
        event_count: u64,
    }

    // ── Entry functions ───────────────────────────────────────────────────────

    fun init(ctx: &mut TxContext) {
        let ledger = LedgerAnchor {
            id: object::new(ctx),
            latest_event_hash: std::string::utf8(b"genesis"),
            event_count: 0,
        };
        // Shared object for global anchoring
        transfer::share_object(ledger);
    }

    public fun anchor_event(
        ledger:        &mut LedgerAnchor,
        event_id:      String,
        event_type:    String,
        workspace_id:  String,
        agent_id:      String,
        blob_id:       String,
        blob_hash:     String,
        parent_event:  String,
        previous_hash: String,
        signature:     String,
        _ctx:          &mut TxContext,
    ) {
        ledger.event_count = ledger.event_count + 1;
        ledger.latest_event_hash = event_id;

        event::emit(ProtocolEventAnchored {
            event_id,
            event_type,
            workspace_id,
            agent_id,
            blob_id,
            blob_hash,
            parent_event,
            previous_hash,
            signature,
        });
    }

    public fun latest_event_hash(ledger: &LedgerAnchor): &String {
        &ledger.latest_event_hash
    }
}
