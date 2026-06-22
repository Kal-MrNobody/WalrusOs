#!/usr/bin/env python3
"""
WalrusOS — Post-Deployment Verification Script

Loads the package ID from config (or .env), verifies the package
exists on-chain, and prints every object that was created.

Usage:
    python scripts/verify_deployment.py
    python scripts/verify_deployment.py --package-id 0xABC123...
    python scripts/verify_deployment.py --network mainnet
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
CONFIG_FILE = Path.home() / ".walrusos" / "config.json"
ENV_FILE    = REPO_ROOT / ".env"

EXPLORER_URLS = {
    "testnet": "https://suiscan.xyz/testnet/object",
    "mainnet": "https://suiscan.xyz/mainnet/object",
    "devnet":  "https://suiscan.xyz/devnet/object",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def load_config() -> tuple[str, str]:
    """
    Load package_id and network from, in priority order:
      1. CLI args (--package-id / --network)
      2. Environment variables (WALRUSOS_PACKAGE_ID, WALRUSOS_NETWORK)
      3. .env file in project root
      4. ~/.walrusos/config.json
    Returns (package_id, network).
    """
    import argparse
    parser = argparse.ArgumentParser(description="Verify WalrusOS Move deployment")
    parser.add_argument("--package-id", default=None, help="Override package ID")
    parser.add_argument("--network", default=None, choices=["testnet", "mainnet", "devnet"])
    args = parser.parse_args()

    # Priority 1: CLI
    package_id = args.package_id
    network    = args.network

    # Priority 2: Env vars
    if not package_id:
        package_id = os.environ.get("WALRUSOS_PACKAGE_ID")
    if not network:
        network = os.environ.get("WALRUSOS_NETWORK")

    # Priority 3: .env file
    env_file = _load_env_file(ENV_FILE)
    if not package_id:
        package_id = env_file.get("WALRUSOS_PACKAGE_ID")
    if not network:
        network = env_file.get("WALRUSOS_NETWORK")

    # Priority 4: ~/.walrusos/config.json
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if not package_id:
                package_id = cfg.get("package_id")
            if not network:
                network = cfg.get("network")
        except (json.JSONDecodeError, OSError):
            pass

    if not package_id or package_id == "0x0":
        print("❌ No package ID found.")
        print()
        print("   Deploy first:")
        print("     ./scripts/deploy_contracts.sh")
        print("   Or specify directly:")
        print("     python scripts/verify_deployment.py --package-id 0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8")
        sys.exit(1)

    return package_id, (network or "testnet")


def run(cmd: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def sui_object(object_id: str) -> dict | None:
    """Fetch a Sui object by ID using `sui client object --json`."""
    code, stdout, stderr = run(["sui", "client", "object", object_id, "--json"])
    if code != 0:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def get_objects_by_package(package_id: str, network: str) -> list[dict]:
    """
    Use `sui client events` to find objects created during package publish.
    Falls back to querying the package object itself.
    """
    code, stdout, stderr = run([
        "sui", "client", "object", package_id, "--json"
    ])
    if code != 0:
        return []
    try:
        return [json.loads(stdout)]
    except json.JSONDecodeError:
        return []


def print_object_info(obj: dict, label: str = "") -> None:
    """Pretty-print a Sui object."""
    if not obj:
        return

    content  = obj.get("content", obj.get("data", {}).get("content", {}))
    obj_type = content.get("dataType", "unknown")
    fields   = content.get("fields", {})
    type_str = content.get("type", "")

    if label:
        print(f"\n  📦 {label}")

    obj_id = (
        obj.get("objectId")
        or obj.get("data", {}).get("objectId")
        or "?"
    )
    print(f"     Object ID  : {obj_id}")
    print(f"     Type       : {type_str or obj_type}")

    if fields:
        print(f"     Fields:")
        for k, v in fields.items():
            val_str = str(v)
            if len(val_str) > 60:
                val_str = val_str[:57] + "..."
            print(f"       {k:20s} = {val_str}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("════════════════════════════════════════════════════════════")
    print("  WalrusOS — Deployment Verification")
    print("════════════════════════════════════════════════════════════")
    print()

    # Step 1: Load config
    package_id, network = load_config()
    explorer_base = EXPLORER_URLS.get(network, EXPLORER_URLS["testnet"])

    print(f"  Package ID : {package_id}")
    print(f"  Network    : {network}")
    print()

    # Step 2: Check Sui CLI
    code, version, _ = run(["sui", "--version"])
    if code != 0:
        print("❌ Sui CLI not found.")
        print("   Install: https://docs.sui.io/guides/developer/getting-started/sui-install")
        sys.exit(1)
    print(f"  Sui CLI    : {version.strip()}")

    # Check active address
    code, address, _ = run(["sui", "client", "active-address"])
    if code == 0 and address.strip():
        print(f"  Wallet     : {address.strip()}")
    print()

    # Step 3: Verify package exists on-chain
    print("  Verifying package on-chain…")
    pkg_obj = sui_object(package_id)

    if pkg_obj is None:
        print(f"\n  ❌ Package {package_id} NOT found on {network}.")
        print()
        print("  Possible reasons:")
        print("   - Wrong network active (run: sui client envs)")
        print("   - Package not yet finalised (wait a few seconds and retry)")
        print("   - Wrong package ID in config")
        sys.exit(1)

    print(f"\n  ✅ Package exists on {network}!")
    print_object_info(pkg_obj, "Package Object")

    # Step 4: Discover all created objects from deploy_output.json
    deploy_output_file = REPO_ROOT / "deploy_output.json"
    created_objects: list[dict] = []

    if deploy_output_file.exists():
        print("\n  Scanning deploy_output.json for created objects…")
        try:
            deploy_data = json.loads(deploy_output_file.read_text(encoding="utf-8"))
            object_changes = deploy_data.get("objectChanges", [])

            for change in object_changes:
                change_type = change.get("type", "")
                obj_type    = change.get("objectType", "")
                obj_id      = change.get("objectId", "")

                if change_type == "published":
                    print(f"\n  📦 Published Package")
                    print(f"     ID      : {change.get('packageId', obj_id)}")
                    modules = change.get("modules", [])
                    if modules:
                        print(f"     Modules : {', '.join(modules)}")

                elif change_type == "created":
                    label = obj_type.split("::")[-1] if "::" in obj_type else obj_type
                    print(f"\n  🆕 Created: {label}")
                    print(f"     Object ID : {obj_id}")
                    print(f"     Type      : {obj_type}")
                    owner = change.get("owner", {})
                    if isinstance(owner, dict):
                        if "Shared" in owner:
                            print(f"     Ownership : Shared (accessible by anyone)")
                        elif "AddressOwner" in owner:
                            print(f"     Ownership : Owned by {owner['AddressOwner']}")
                    created_objects.append({"id": obj_id, "type": obj_type})

        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Could not read deploy_output.json: {e}")
    else:
        print("\n  ℹ No deploy_output.json found — skipping object discovery.")
        print("    Re-deploy with deploy_contracts.sh to generate it.")

    # Step 5: Print expected module structure
    print()
    print("  Expected modules in package:")
    MODULES = {
        "identity": [
            "create_workspace(name: String)",
            "register_agent(workspace_id: address, name: String, public_key: vector<u8>, trust_root: vector<u8>)",
            "update_agent_status(agent: &mut AgentIdentity, new_status: u8)",
            "increment_counters(agent: &mut AgentIdentity, execution: u64, memory: u64, artifact: u64)",
            "delegate_capability(target_stream: address, bitmask: u64, recipient: address, valid_until_epoch: u64)",
            "revoke_capability(cap: Capability)",
        ],
        "memory": [
            "create_stream(agent_id: address)",
            "append_event(stream: &mut MemoryStream, parent_id: String, content_blob_id: String)",
            "append_signed_event(workspace, agent, cap, stream, parent_id, content_blob_id, event_hash, signature)",
            "delete_stream(stream: &mut MemoryStream)",
        ],
        "protocol": [
            "anchor_event(ledger: &mut LedgerAnchor, event_id, event_type, workspace_id, agent_id, blob_id, blob_hash, parent_event, previous_hash, signature)",
        ],
    }

    for module_name, entry_fns in MODULES.items():
        print(f"\n  ┌─ {package_id}::{module_name}")
        for fn in entry_fns:
            print(f"  │  entry {fn}")
        print(f"  └─")

    # Step 6: Explorer URLs
    print()
    print("  ─────────────────────────────────────────────────────────")
    print("  🔗 Sui Explorer URLs")
    print("  ─────────────────────────────────────────────────────────")
    print(f"  Package  : {explorer_base}/{package_id}")
    for obj_info in created_objects:
        obj_id    = obj_info.get("id", "")
        obj_label = obj_info.get("type", "").split("::")[-1]
        if obj_id:
            print(f"  {obj_label:8s} : {explorer_base}/{obj_id}")

    # Step 7: SDK configuration
    print()
    print("  ─────────────────────────────────────────────────────────")
    print("  🐍 SDK Configuration")
    print("  ─────────────────────────────────────────────────────────")
    print()
    print(f"  # Option 1: environment variable")
    print(f"  export WALRUSOS_PACKAGE_ID={package_id}")
    print()
    print(f"  # Option 2: Python")
    print(f"  from walrusos import WalrusOS")
    print(f"  os = WalrusOS(package_id=\"{package_id}\")")
    print()
    print(f"  # Option 3: .env file  (already written by deploy_contracts.sh)")
    print(f"  WALRUSOS_PACKAGE_ID={package_id}")
    print()
    print("════════════════════════════════════════════════════════════")
    print("  ✅ Verification complete.")
    print("════════════════════════════════════════════════════════════")
    print()


if __name__ == "__main__":
    main()
