#!/usr/bin/env python3
"""
WalrusOS Move Package Deployment Script.

Deploys the WalrusOS Move package to Sui testnet (or mainnet) and
saves the resulting package_id to ~/.walrusos/config.json so all
subsequent CLI and SDK calls use it automatically.

Requirements:
  - Sui CLI installed:    sui --version
  - Wallet configured:   sui client active-address
  - Wallet funded:       sui client gas  (if empty, go to testnet.sui.io/faucet)

Usage:
  python scripts/deploy_walrusos.py
  python scripts/deploy_walrusos.py --network mainnet   # (after thorough testing)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
MOVE_PACKAGE = REPO_ROOT / "move" / "walrusos"
CONFIG_DIR   = Path.home() / ".walrusos"
CONFIG_FILE  = CONFIG_DIR / "config.json"

NETWORKS = {
    "testnet": {
        "sui_rpc_url":    "https://fullnode.testnet.sui.io:443",
        "publisher_url":  "https://publisher.walrus-testnet.walrus.space",
        "aggregator_url": "https://aggregator.walrus-testnet.walrus.space",
    },
    "mainnet": {
        "sui_rpc_url":    "https://fullnode.mainnet.sui.io:443",
        "publisher_url":  "https://publisher.walrus.space",
        "aggregator_url": "https://aggregator.walrus.space",
    },
}


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        print(f"\n❌ Command failed: {' '.join(cmd)}")
        if result.stdout:
            print("stdout:", result.stdout[-2000:])
        if result.stderr:
            print("stderr:", result.stderr[-2000:])
        sys.exit(result.returncode)
    return result


def check_prerequisites() -> str:
    """Check that the Sui CLI is installed and a wallet is configured."""
    print("🔍 Checking prerequisites…")

    # Check sui CLI
    result = run(["sui", "--version"], check=False)
    if result.returncode != 0:
        print("❌ Sui CLI not found. Install it from https://docs.sui.io/guides/developer/getting-started/sui-install")
        sys.exit(1)
    print(f"  ✓ Sui CLI: {result.stdout.strip()}")

    # Check active wallet
    result = run(["sui", "client", "active-address"], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        print("❌ No active Sui wallet. Run: sui client new-address ed25519")
        sys.exit(1)
    address = result.stdout.strip()
    print(f"  ✓ Active wallet: {address}")

    return address


def check_balance(address: str) -> None:
    """Check wallet balance and warn if low."""
    result = run(["sui", "client", "gas", "--json"], check=False)
    if result.returncode != 0:
        print("  ⚠ Could not check gas balance. Proceeding anyway.")
        return

    try:
        coins = json.loads(result.stdout)
        total_mist = sum(c.get("mistBalance", 0) for c in coins)
        total_sui  = total_mist / 1_000_000_000
        print(f"  ✓ Balance: {total_sui:.4f} SUI")
        if total_sui < 0.1:
            print(f"\n⚠ Balance is low ({total_sui:.4f} SUI).")
            print("  Get testnet tokens at: https://testnet.sui.io/faucet")
            print("  Or run: sui client faucet")
            input("\nPress Enter to continue anyway, or Ctrl+C to abort…")
    except (json.JSONDecodeError, KeyError):
        print("  ⚠ Could not parse gas balance. Proceeding anyway.")


def deploy(network: str) -> dict:
    """
    Run `sui client publish --json` and return the parsed result.
    """
    print(f"\n📦 Publishing Move package to Sui {network}…")
    print(f"   Package: {MOVE_PACKAGE}")

    if not MOVE_PACKAGE.exists():
        print(f"❌ Move package not found at {MOVE_PACKAGE}")
        sys.exit(1)

    result = run([
        "sui", "client", "publish",
        "--json",
        "--gas-budget", "200000000",   # 0.2 SUI
        str(MOVE_PACKAGE),
    ])

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("❌ Could not parse publish output as JSON:")
        print(result.stdout[-2000:])
        sys.exit(1)

    return output


def extract_package_id(publish_output: dict) -> str:
    """
    Extract the package_id from the `sui client publish --json` output.

    The published package appears in ``objectChanges`` with type ``"published"``.
    """
    object_changes = publish_output.get("objectChanges", [])
    for change in object_changes:
        if change.get("type") == "published":
            pkg_id = change.get("packageId")
            if pkg_id:
                return pkg_id

    # Fallback: look in effects
    effects = publish_output.get("effects", {})
    for dep in effects.get("dependencies", []):
        if isinstance(dep, str) and dep.startswith("0x"):
            return dep

    print("❌ Could not extract packageId from publish output.")
    print("   Raw output:")
    print(json.dumps(publish_output, indent=2)[:3000])
    sys.exit(1)


def save_config(network: str, package_id: str, address: str) -> None:
    """Write package_id and network config to ~/.walrusos/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    current: dict = {}
    if CONFIG_FILE.exists():
        try:
            current = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    net_config = NETWORKS[network]
    current.update({
        "package_id":     package_id,
        "network":        network,
        "sui_address":    address,
        "sui_rpc_url":    net_config["sui_rpc_url"],
        "publisher_url":  net_config["publisher_url"],
        "aggregator_url": net_config["aggregator_url"],
    })

    CONFIG_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    print(f"\n✅ Config saved to {CONFIG_FILE}")


def print_summary(package_id: str, address: str, network: str) -> None:
    net = NETWORKS[network]
    print("\n" + "═" * 60)
    print("🎉  WalrusOS Move Package Deployed!")
    print("═" * 60)
    print(f"  Package ID : {package_id}")
    print(f"  Wallet     : {address}")
    print(f"  Network    : {network}")
    print(f"  Sui RPC    : {net['sui_rpc_url']}")
    print(f"  Publisher  : {net['publisher_url']}")
    print("═" * 60)
    print("\nNext steps:")
    print("  walrusos login")
    print("  walrusos workspace create my-research")
    print("  walrusos agent publish Researcher papers --payload '{\"title\": \"Paper 1\"}'")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Deploy WalrusOS Move package to Sui")
    parser.add_argument(
        "--network",
        choices=["testnet", "mainnet"],
        default="testnet",
        help="Target Sui network (default: testnet)",
    )
    parser.add_argument(
        "--skip-balance-check",
        action="store_true",
        help="Skip wallet balance check",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  WalrusOS — Move Package Deployment")
    print("=" * 60)

    address = check_prerequisites()

    if not args.skip_balance_check:
        check_balance(address)

    output     = deploy(args.network)
    package_id = extract_package_id(output)
    save_config(args.network, package_id, address)
    print_summary(package_id, address, args.network)


if __name__ == "__main__":
    main()
