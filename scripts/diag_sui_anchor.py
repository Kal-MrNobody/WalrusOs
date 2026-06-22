"""
Sui anchor diagnostic — surfaces the real reason `protocol::anchor_event` is
failing. Runs every check the previous diagnosis pointed at:

  1. WALRUSOS_PACKAGE_ID — set in .env? loaded into the env at runtime?
  2. WALRUSOS_LEDGER_ANCHOR_ID — present?
  3. Active Sui env + active address
  4. Deployer wallet gas — `sui client gas`
  5. Manual `sui client call ... anchor_event` with synthetic args — captures
     full stdout + stderr + returncode

Run:
    python scripts/diag_sui_anchor.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH, override=True)


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError as exc:
        return -1, "", f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        return -2, "", f"timed out after {timeout}s"


# ── 1. Env vars ──────────────────────────────────────────────────────────────
section("1. Required env vars (loaded via python-dotenv)")

env_vars = [
    "WALRUSOS_PACKAGE_ID",
    "WALRUSOS_LEDGER_ANCHOR_ID",
    "WALRUSOS_DEPLOYER_ADDRESS",
    "WALRUSOS_NETWORK",
]
for k in env_vars:
    v = os.environ.get(k, "<UNSET>")
    if v == "<UNSET>":
        print(f"  ❌ {k:30} <UNSET>")
    else:
        print(f"  ✓  {k:30} {v[:60]}{'…' if len(v) > 60 else ''}")
print()
print(f"  .env path used: {ENV_PATH} (exists={ENV_PATH.exists()})")

PACKAGE_ID = os.environ.get("WALRUSOS_PACKAGE_ID", "")
LEDGER_ID  = os.environ.get("WALRUSOS_LEDGER_ANCHOR_ID", "")

if not PACKAGE_ID:
    print("\n❌ WALRUSOS_PACKAGE_ID is empty — cannot proceed.")
    sys.exit(1)
if not LEDGER_ID:
    print("\n❌ WALRUSOS_LEDGER_ANCHOR_ID is empty — cannot proceed.")
    sys.exit(1)


# ── 2. Sui CLI version + active env ──────────────────────────────────────────
section("2. Sui CLI status")

rc, out, err = run(["sui", "--version"])
print(f"  sui --version:        rc={rc}  out={out!r}  err={err!r}")

rc, out, err = run(["sui", "client", "active-env"])
print(f"  active-env:           rc={rc}  out={out!r}  err={err!r}")

rc, out, err = run(["sui", "client", "active-address"])
print(f"  active-address:       rc={rc}  out={out!r}  err={err!r}")
active_addr = out


# ── 3. Wallet gas ────────────────────────────────────────────────────────────
section("3. Deployer wallet gas (this wallet pays for anchor txns)")

rc, out, err = run(["sui", "client", "gas"], timeout=30)
print(f"  rc={rc}")
if out:
    # Just first ~12 lines is plenty
    for line in out.splitlines()[:12]:
        print(f"  | {line}")
elif err:
    for line in err.splitlines()[:12]:
        print(f"  | (stderr) {line}")
else:
    print("  (no output)")


# ── 4. LedgerAnchor object exists? ───────────────────────────────────────────
section("4. LedgerAnchor object on-chain")

rc, out, err = run(["sui", "client", "object", LEDGER_ID], timeout=30)
print(f"  rc={rc}")
if rc != 0:
    print(f"  ❌ stderr: {err[:500]}")
    print(f"  ❌ stdout: {out[:500]}")
else:
    for line in out.splitlines()[:14]:
        print(f"  | {line}")


# ── 5. Manual anchor_event call ──────────────────────────────────────────────
section("5. Manual sui client call PACKAGE::protocol::anchor_event (the demo's call)")

# Synthetic but valid args matching the order in sui_real.py
synthetic_event_id = "diag_event_" + hashlib.sha256(b"diag").hexdigest()[:8]
synthetic_blob_id  = "diag_blob_id"
synthetic_blob_hash = hashlib.sha256(b"diag_payload").hexdigest()

args = [
    LEDGER_ID,             # &mut LedgerAnchor (shared object)
    synthetic_event_id,    # event_id
    "MemoryAppended",      # event_type
    "diag-workspace",      # workspace_id
    "diag-agent",          # agent_id
    synthetic_blob_id,     # blob_id
    synthetic_blob_hash,   # blob_hash
    "genesis",             # parent_event
    "genesis",             # previous_hash
    "cli-unsigned",        # signature
]

cmd = [
    "sui", "client", "call",
    "--package", PACKAGE_ID,
    "--module", "protocol",
    "--function", "anchor_event",
    "--gas-budget", "50000000",
    "--json",
    "--args", *args,
]

print(f"  full cmd ({len(cmd)} tokens):")
print(f"    {' '.join(cmd)}")
print()
rc, out, err = run(cmd, timeout=120)
print(f"  rc:     {rc}")
print(f"  stdout: ({len(out)} chars)")
for line in out.splitlines()[:30]:
    print(f"    | {line}")
print(f"  stderr: ({len(err)} chars)")
for line in err.splitlines()[:30]:
    print(f"    | {line}")

print()
if rc == 0:
    print("  ✓ Manual anchor succeeded — adapter path should now work too.")
else:
    print("  ❌ Manual anchor failed — the rc/stderr/stdout above is the root cause.")
