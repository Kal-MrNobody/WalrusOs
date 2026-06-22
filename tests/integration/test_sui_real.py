"""
Integration tests for the real Sui transaction adapter.

These tests execute REAL transactions on Sui Testnet — they require:
  - A funded Sui wallet at ~/.sui/sui_config/client.yaml
  - The WalrusOS Move package deployed (PACKAGE_ID in config.py)
  - SUI_INTEGRATION=1 environment variable set

Run with:
    SUI_INTEGRATION=1 pytest tests/integration/test_sui_real.py -v -s -x

Tests run sequentially (-x stops on first failure) because each test
depends on objects created by previous tests.

Every test prints the full Sui Explorer URL so transactions can be
verified manually.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

import pytest

# Gate: only run when SUI_INTEGRATION=1 is set
pytestmark = pytest.mark.skipif(
    os.environ.get("SUI_INTEGRATION", "").lower() not in ("1", "true", "yes"),
    reason="Set SUI_INTEGRATION=1 to run real Sui integration tests",
)

from walrusos.adapters.sui_real import RealSuiClient, SuiTransactionError
from walrusos.config import DEPLOYER_ADDRESS

# Temp file to pass state between sequential tests
_STATE_FILE = os.path.join(tempfile.gettempdir(), "walrusos_sui_test_state.json")


def _save_state(data: dict) -> None:
    """Save test state to a temp file."""
    existing = _load_state()
    existing.update(data)
    with open(_STATE_FILE, "w") as f:
        json.dump(existing, f)


def _load_state() -> dict:
    """Load test state from temp file."""
    if os.path.exists(_STATE_FILE):
        with open(_STATE_FILE) as f:
            return json.load(f)
    return {}


@pytest.fixture(scope="module")
def sui() -> RealSuiClient:
    """Create a RealSuiClient connected to testnet."""
    client = RealSuiClient()
    assert client.active_address, "Sui wallet not connected"
    print(f"\n  Wallet: {client.active_address}")
    print(f"  Package: {client.package_id}")
    print(f"  LedgerAnchor: {client.ledger_anchor_id}")
    # Clean up state from previous runs
    if os.path.exists(_STATE_FILE):
        os.remove(_STATE_FILE)
    return client


# ── Test 1: create_workspace ─────────────────────────────────────────────────


def test_1_create_workspace(sui: RealSuiClient):
    """Create a Workspace object on Sui testnet."""
    result = sui.create_workspace("test-workspace-walrusos")

    assert result["tx_digest"], "tx_digest is empty"
    assert result["workspace_id"].startswith("0x"), (
        f"workspace_id should start with 0x, got: {result['workspace_id']}"
    )

    print(f"\n{'='*70}")
    print(f"  [OK] Workspace Created")
    print(f"  Workspace ID:  {result['workspace_id']}")
    print(f"  Tx Digest:     {result['tx_digest']}")
    print(f"  Explorer:      {result['explorer_url']}")
    print(f"{'='*70}")

    _save_state({"workspace_id": result["workspace_id"]})


# ── Test 2: register_agent ───────────────────────────────────────────────────


def test_2_register_agent(sui: RealSuiClient):
    """Register an AgentIdentity in the workspace created by test_1."""
    state = _load_state()
    workspace_id = state.get("workspace_id")
    assert workspace_id, "workspace_id not found — did test_1 pass?"

    # Generate a random 32-byte Ed25519-style public key
    public_key = os.urandom(32)

    result = sui.register_agent(
        workspace_id=workspace_id,
        name="ResearchAgent",
        public_key_bytes=public_key,
    )

    assert result["tx_digest"], "tx_digest is empty"
    assert result["agent_id"].startswith("0x"), (
        f"agent_id should start with 0x, got: {result['agent_id']}"
    )

    print(f"\n{'='*70}")
    print(f"  [OK] Agent Registered")
    print(f"  Agent ID:      {result['agent_id']}")
    print(f"  Workspace:     {workspace_id}")
    print(f"  Public Key:    {public_key.hex()[:32]}...")
    print(f"  Tx Digest:     {result['tx_digest']}")
    print(f"  Explorer:      {result['explorer_url']}")
    print(f"{'='*70}")

    _save_state({"agent_id": result["agent_id"]})


# ── Test 3: anchor_event ─────────────────────────────────────────────────────


def test_3_anchor_event(sui: RealSuiClient):
    """Anchor a protocol event to the shared LedgerAnchor."""
    blob_id_str = "test-blob-id-12345"
    event_hash = hashlib.sha256(b"test event payload").digest()

    result = sui.anchor_event(
        blob_id=blob_id_str,
        event_hash=event_hash,
    )

    assert result["tx_digest"], "tx_digest is empty"

    print(f"\n{'='*70}")
    print(f"  [OK] Event Anchored")
    print(f"  Blob ID:       {blob_id_str}")
    print(f"  Event Hash:    {event_hash.hex()[:32]}...")
    print(f"  Tx Digest:     {result['tx_digest']}")
    print(f"  Explorer:      {result['explorer_url']}")
    print(f"{'='*70}")


# ── Test 4: delegate_and_revoke ──────────────────────────────────────────────


def test_4_delegate_and_revoke(sui: RealSuiClient):
    """Delegate a Capability, then revoke it."""
    state = _load_state()
    workspace_id = state.get("workspace_id")
    agent_id = state.get("agent_id")
    assert workspace_id, "workspace_id not found — did test_1 pass?"
    assert agent_id, "agent_id not found — did test_2 pass?"

    # Use the agent_id as the target_stream (it's just an address for the cap)
    delegate_result = sui.delegate_capability(
        target_stream=agent_id,
        recipient=DEPLOYER_ADDRESS,
        bitmask=7,  # READ | WRITE | FORK
        until_epoch=0,  # Never expires
    )

    assert delegate_result["tx_digest"], "delegate tx_digest is empty"
    assert delegate_result["capability_id"].startswith("0x"), (
        f"capability_id should start with 0x, got: {delegate_result['capability_id']}"
    )

    print(f"\n{'='*70}")
    print(f"  [OK] Capability Delegated")
    print(f"  Capability ID: {delegate_result['capability_id']}")
    print(f"  Target Stream: {agent_id}")
    print(f"  Recipient:     {DEPLOYER_ADDRESS}")
    print(f"  Bitmask:       7 (READ|WRITE|FORK)")
    print(f"  Tx Digest:     {delegate_result['tx_digest']}")
    print(f"  Explorer:      {delegate_result['explorer_url']}")
    print(f"{'='*70}")

    # Now revoke it
    revoke_result = sui.revoke_capability(delegate_result["capability_id"])

    assert revoke_result["tx_digest"], "revoke tx_digest is empty"

    print(f"\n{'='*70}")
    print(f"  [OK] Capability Revoked")
    print(f"  Tx Digest:     {revoke_result['tx_digest']}")
    print(f"  Explorer:      {revoke_result['explorer_url']}")
    print(f"{'='*70}")


# ── Summary ──────────────────────────────────────────────────────────────────


def test_5_summary(sui: RealSuiClient):
    """Print a summary of all created objects."""
    state = _load_state()

    print(f"\n{'='*70}")
    print(f"  WalrusOS Sui Integration Test Summary")
    print(f"{'='*70}")
    print(f"  Network:        testnet")
    print(f"  Package ID:     {sui.package_id}")
    print(f"  LedgerAnchor:   {sui.ledger_anchor_id}")
    print(f"  Deployer:       {sui.active_address}")
    print(f"  Workspace ID:   {state.get('workspace_id', 'N/A')}")
    print(f"  Agent ID:       {state.get('agent_id', 'N/A')}")
    print(f"{'='*70}")
    print(f"\n  All objects live on Sui testnet. Verify at:")
    if state.get("workspace_id"):
        print(f"    Workspace: https://suiexplorer.com/object/{state['workspace_id']}?network=testnet")
    if state.get("agent_id"):
        print(f"    Agent:     https://suiexplorer.com/object/{state['agent_id']}?network=testnet")
    print(f"    Package:   https://suiexplorer.com/object/{sui.package_id}?network=testnet")
    print()
