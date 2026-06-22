# WalrusOS — Move Contract Deployment Guide

This guide covers deploying the WalrusOS Move package to **Sui Testnet** (and eventually Mainnet).

---

## Prerequisites

### 1. Install the Sui CLI

```bash
# Recommended: suiup (manages versions across networks)
curl -fsSL https://raw.githubusercontent.com/MystenLabs/suiup/main/install.sh | sh
suiup install sui@testnet

# Verify
sui --version
# sui 1.x.x-testnet-...
```

**Alternative — direct binary (Windows):**
1. Download from https://github.com/MystenLabs/sui/releases
2. Pick `sui-testnet-vX.XX.X-windows-x86_64.tgz`
3. Extract `sui.exe` and add to `PATH`

**Alternative — Chocolatey (Windows):**
```powershell
choco install sui
```

### 2. Create and fund a wallet

```bash
# Create a new Ed25519 keypair
sui client new-address ed25519

# Switch to testnet
sui client new-env --alias testnet --rpc https://fullnode.testnet.sui.io:443
sui client switch --env testnet

# Verify active address
sui client active-address

# Get testnet tokens (pick one):
sui client faucet                        # built-in CLI faucet
# Or visit: https://faucet.sui.io
```

You need at least **0.2 SUI** (200,000,000 MIST) for deployment gas.

### 3. Verify network

```bash
sui client envs       # list configured networks
sui client active-env # confirm testnet is active
```

---

## Package Structure

```
move/walrusos/
├── Move.toml          ← package manifest
└── sources/
    ├── identity.move  ← Workspace, AgentIdentity, Capability
    ├── memory.move    ← MemoryStream, event anchoring
    └── protocol.move  ← LedgerAnchor, ProtocolEvent anchoring
```

---

## Step 1 — Build

```bash
# From the WalrusOS project root:
sui move build --path ./move/walrusos
```

### Expected output

```
UPDATING GIT DEPENDENCY https://github.com/MystenLabs/sui.git
INCLUDING DEPENDENCY Sui
INCLUDING DEPENDENCY MoveStdlib
BUILDING walrusos
```

> If you see `error[E*]` lines, see [Troubleshooting](#troubleshooting) below.

---

## Step 2 — Deploy

```bash
# Make script executable (macOS/Linux)
chmod +x scripts/deploy_contracts.sh

# Deploy to testnet
./scripts/deploy_contracts.sh

# Deploy to mainnet (only after thorough testing)
./scripts/deploy_contracts.sh mainnet
```

The script:
1. Runs `sui move build`
2. Runs `sui client publish --json --gas-budget 200000000`
3. Extracts the `packageId` from the JSON output
4. Writes `WALRUSOS_PACKAGE_ID` to `.env`
5. Updates `~/.walrusos/config.json`

### Expected output

```
════════════════════════════════════════════════════════════
  WalrusOS — Move Package Deployment
  Network: testnet
════════════════════════════════════════════════════════════

[INFO]  Checking prerequisites…
[OK]    Sui CLI: sui 1.x.x-testnet
[OK]    Active wallet: 0xYOUR_WALLET_ADDRESS
[OK]    Balance: 1.2345 SUI

[INFO]  Building Move package…

UPDATING GIT DEPENDENCY https://github.com/MystenLabs/sui.git
INCLUDING DEPENDENCY Sui
INCLUDING DEPENDENCY MoveStdlib
BUILDING walrusos

[OK]    Build succeeded.

[INFO]  Publishing to Sui testnet…
        Gas budget: 200000000 MIST (0.200 SUI max)

[OK]    Package ID: 0xABCDEF1234567890abcdef1234567890abcdef1234567890abcdef1234567890
[OK]    LedgerAnchor (shared): 0x1234...abcd
[OK]    .env updated
[OK]    ~/.walrusos/config.json updated

════════════════════════════════════════════════════════════
  WalrusOS Move Package Deployed Successfully!
════════════════════════════════════════════════════════════

  Package ID         : 0xABCDEF...
  LedgerAnchor ID    : 0x1234...abcd
  Deployer wallet    : 0xYOUR_WALLET_ADDRESS
  Network            : testnet
  Sui Explorer       : https://suiscan.xyz/testnet/object/0xABCDEF...

  .env               : /path/to/WalrusOS/.env
  Config             : /home/user/.walrusos/config.json

Next steps:
  1. python scripts/verify_deployment.py
  2. export WALRUSOS_PACKAGE_ID=0xABCDEF...
  3. walrusos workspace create my-project
```

---

## Step 3 — Verify

```bash
python scripts/verify_deployment.py
```

### Expected output

```
════════════════════════════════════════════════════════════
  WalrusOS — Deployment Verification
════════════════════════════════════════════════════════════

  Package ID : 0xABCDEF...
  Network    : testnet
  Sui CLI    : sui 1.x.x-testnet

  Verifying package on-chain…

  ✅ Package exists on testnet!

  📦 Package Object
     Object ID  : 0xABCDEF...
     Type       : package

  Scanning deploy_output.json for created objects…

  📦 Published Package
     ID      : 0xABCDEF...
     Modules : identity, memory, protocol

  🆕 Created: LedgerAnchor
     Object ID : 0x1234...abcd
     Type      : 0xABCDEF...::protocol::LedgerAnchor
     Ownership : Shared (accessible by anyone)

  Expected modules in package:

  ┌─ 0xABCDEF...::identity
  │  entry create_workspace(name: String)
  │  entry register_agent(workspace_id: address, name: String, ...)
  │  entry update_agent_status(agent: &mut AgentIdentity, new_status: u8)
  │  entry increment_counters(agent: &mut AgentIdentity, ...)
  │  entry delegate_capability(target_stream: address, ...)
  │  entry revoke_capability(cap: Capability)
  └─

  ┌─ 0xABCDEF...::memory
  │  entry create_stream(agent_id: address)
  │  entry append_event(stream: &mut MemoryStream, ...)
  │  entry append_signed_event(workspace, agent, cap, stream, ...)
  │  entry delete_stream(stream: &mut MemoryStream)
  └─

  ┌─ 0xABCDEF...::protocol
  │  entry anchor_event(ledger: &mut LedgerAnchor, ...)
  └─

  🔗 Sui Explorer URLs
  Package  : https://suiscan.xyz/testnet/object/0xABCDEF...
  LedgerAnchor : https://suiscan.xyz/testnet/object/0x1234...abcd

════════════════════════════════════════════════════════════
  ✅ Verification complete.
════════════════════════════════════════════════════════════
```

---

## Step 4 — Configure the SDK

The deploy script writes config automatically. You can also configure manually:

### Option A — Environment variable (recommended for CI/CD)

```bash
export WALRUSOS_PACKAGE_ID=0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8
export WALRUSOS_NETWORK=testnet
```

### Option B — `.env` file (local development)

```bash
# .env (in project root — already written by deploy_contracts.sh)
WALRUSOS_PACKAGE_ID=0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8
WALRUSOS_NETWORK=testnet
```

### Option C — Python constructor

```python
from walrusos import WalrusOS

os = WalrusOS(
    package_id="0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8",
    network="testnet",
)
```

### Option D — `~/.walrusos/config.json` (already written by deploy script)

```json
{
  "package_id":     "0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8",
  "network":        "testnet",
  "sui_address":    "0xYOUR_WALLET_ADDRESS",
  "sui_rpc_url":    "https://fullnode.testnet.sui.io:443",
  "publisher_url":  "https://publisher.walrus-testnet.walrus.space",
  "aggregator_url": "https://aggregator.walrus-testnet.walrus.space"
}
```

---

## Move Modules — Entry Functions Reference

### `walrusos::identity`

| Function | Description | Caller |
|----------|-------------|--------|
| `create_workspace(name)` | Create a Workspace object, transfer to sender | Wallet owner |
| `register_agent(workspace_id, name, public_key, trust_root)` | Create an AgentIdentity, transfer to sender | Wallet owner |
| `update_agent_status(agent, new_status)` | Pause / resume / terminate an agent | Agent owner |
| `increment_counters(agent, execution, memory, artifact)` | Update agent usage counters | Agent owner |
| `delegate_capability(target_stream, bitmask, recipient, valid_until_epoch)` | Mint and transfer a Capability token | Any wallet |
| `revoke_capability(cap)` | Destroy a Capability object | Capability owner |

### `walrusos::memory`

| Function | Description | Caller |
|----------|-------------|--------|
| `create_stream(agent_id)` | Create a MemoryStream + initial CAP_ALL capability | Agent wallet |
| `append_event(stream, parent_id, content_blob_id)` | Anchor a Walrus blob reference on-chain | Stream owner |
| `append_signed_event(workspace, agent, cap, stream, ...)` | Anchor with full permission checks + signature | Agent wallet (with cap) |
| `delete_stream(stream)` | Logically delete a stream | Stream owner |

### `walrusos::protocol`

| Function | Description | Caller |
|----------|-------------|--------|
| `anchor_event(ledger, event_id, ...)` | Emit a ProtocolEvent to the global ledger | SDK |

### Stored objects

| Struct | Module | Ability | Storage |
|--------|--------|---------|---------|
| `Workspace` | `identity` | `key, store` | Owned by creator wallet |
| `AgentIdentity` | `identity` | `key, store` | Owned by creator wallet |
| `Capability` | `identity` | `key` | Owned by recipient wallet |
| `MemoryStream` | `memory` | `key` | Owned by creator wallet |
| `LedgerAnchor` | `protocol` | `key` | **Shared** — created by `init()` |

---

## Troubleshooting

### `sui: command not found`

```bash
# suiup method (recommended):
curl -fsSL https://raw.githubusercontent.com/MystenLabs/suiup/main/install.sh | sh
suiup install sui@testnet
# Then add suiup's bin dir to PATH
```

### `error: no gas coins found`

Your wallet has no testnet SUI. Get tokens:
```bash
sui client faucet
# Or visit: https://faucet.sui.io
```

### `error: framework version mismatch`

Your local Sui CLI version doesn't match the `framework/testnet` revision.
```bash
suiup install sui@testnet   # installs latest testnet-compatible binary
```

### `error[E01]: unbound module 'sui::clock'`

The clock import was removed — this was a pre-fix version. Pull the latest source.

### `error: package size limit exceeded`

Rare. The package has 3 small modules and should be well within limits (~16KB total bytecode).

### `InsufficientGas`

Increase the gas budget:
```bash
sui client publish --gas-budget 500000000 ./move/walrusos
```

### Verify the correct network is active

```bash
sui client envs
# Should show testnet with *active* marker

sui client switch --env testnet
```

---

## Redeployment

Move packages are **immutable** once published. To upgrade:

1. Edit the source in `move/walrusos/sources/`
2. In `Move.toml`, add `published-at = "0xORIGINAL_PACKAGE_ID"` under `[package]`
3. Run: `sui client publish --gas-budget 200000000 ./move/walrusos`
4. Update `WALRUSOS_PACKAGE_ID` in `.env` and `~/.walrusos/config.json`

> **Note:** Sui uses package upgrades with explicit `upgrade_cap` objects. For testnet iteration, simply redeploy — the old package remains on-chain but the SDK will use the new ID.

---

## Security Notes

- **Never commit your keystore** (`~/.sui/sui_config/sui.keystore`) to git
- The `.env` file (containing `WALRUSOS_PACKAGE_ID`) is safe to commit — it contains no secrets
- On mainnet: use a hardware wallet or multisig for the deploying address
- Capabilities issued by `delegate_capability` are transferable on-chain — revoke promptly when no longer needed

---

## Quick Reference

```bash
# Full deployment flow
chmod +x scripts/deploy_contracts.sh
./scripts/deploy_contracts.sh

# Build only (no deploy)
sui move build --path ./move/walrusos

# Verify after deploy
python scripts/verify_deployment.py

# Check on-chain manually
sui client object 0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8

# Open in browser
open https://suiscan.xyz/testnet/object/0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8
```
