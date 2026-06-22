#!/usr/bin/env bash
# =============================================================================
# WalrusOS — Move Contract Deployment Script
# =============================================================================
#
# Usage:
#   chmod +x scripts/deploy_contracts.sh
#   ./scripts/deploy_contracts.sh
#   ./scripts/deploy_contracts.sh --network mainnet   # after testing
#
# Prerequisites:
#   - Sui CLI installed:        sui --version
#   - Active wallet:            sui client active-address
#   - Testnet SUI tokens:       https://faucet.sui.io  (or: sui client faucet)
#   - Correct network active:   sui client envs
#
# After deployment:
#   - PACKAGE_ID is written to .env in the project root
#   - PACKAGE_ID is written to ~/.walrusos/config.json
#   - Run: python scripts/verify_deployment.py
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOVE_PACKAGE="${REPO_ROOT}/move/walrusos"
ENV_FILE="${REPO_ROOT}/.env"
CONFIG_DIR="${HOME}/.walrusos"
CONFIG_FILE="${CONFIG_DIR}/config.json"
NETWORK="${1:-testnet}"
GAS_BUDGET=200000000   # 0.2 SUI

# Colours
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ── Step 0: Check prerequisites ───────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  WalrusOS — Move Package Deployment${RESET}"
echo -e "${BOLD}  Network: ${YELLOW}${NETWORK}${RESET}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo ""

info "Checking prerequisites…"

if ! command -v sui &>/dev/null; then
    error "Sui CLI not found. Install it:
  → https://docs.sui.io/guides/developer/getting-started/sui-install
  → Or: curl -fsSL https://raw.githubusercontent.com/MystenLabs/suiup/main/install.sh | sh
         suiup install sui@testnet"
fi
SUI_VERSION=$(sui --version 2>&1 | head -1)
success "Sui CLI: ${SUI_VERSION}"

ACTIVE_ADDRESS=$(sui client active-address 2>/dev/null | tr -d '\r\n')
if [[ -z "${ACTIVE_ADDRESS}" ]]; then
    error "No active Sui wallet configured.
  Run: sui client new-address ed25519
  Then: sui client faucet   (to get testnet tokens)"
fi
success "Active wallet: ${ACTIVE_ADDRESS}"

# Check balance
GAS_JSON=$(sui client gas --json 2>/dev/null || echo "[]")
TOTAL_MIST=$(echo "${GAS_JSON}" | python3 -c "
import json, sys
coins = json.load(sys.stdin)
print(sum(c.get('mistBalance', c.get('balance', 0)) for c in coins))
" 2>/dev/null || echo "0")
TOTAL_SUI=$(echo "scale=4; ${TOTAL_MIST} / 1000000000" | bc 2>/dev/null || echo "?")
if [[ "${TOTAL_MIST}" -lt 100000000 ]]; then
    warn "Low balance: ${TOTAL_SUI} SUI (need ~0.2 SUI for deployment)"
    warn "Get tokens at: https://faucet.sui.io"
    warn "Or run: sui client faucet"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
else
    success "Balance: ${TOTAL_SUI} SUI"
fi

# ── Step 1: Build ─────────────────────────────────────────────────────────────

echo ""
info "Building Move package…"
echo "  Package: ${MOVE_PACKAGE}"
echo ""

BUILD_OUTPUT=$(sui move build --path "${MOVE_PACKAGE}" 2>&1)
BUILD_EXIT=$?

echo "${BUILD_OUTPUT}"
echo ""

if [[ ${BUILD_EXIT} -ne 0 ]]; then
    error "sui move build failed (exit ${BUILD_EXIT}).
  Fix all compilation errors above before deploying."
fi

success "Build succeeded."

# ── Step 2: Publish ───────────────────────────────────────────────────────────

echo ""
info "Publishing to Sui ${NETWORK}…"
echo "  Gas budget: ${GAS_BUDGET} MIST ($(echo "scale=3; ${GAS_BUDGET}/1000000000" | bc) SUI max)"
echo ""

PUBLISH_OUTPUT=$(sui client publish \
    --json \
    --gas-budget "${GAS_BUDGET}" \
    "${MOVE_PACKAGE}" 2>&1)
PUBLISH_EXIT=$?

if [[ ${PUBLISH_EXIT} -ne 0 ]]; then
    echo "${PUBLISH_OUTPUT}"
    error "sui client publish failed (exit ${PUBLISH_EXIT})."
fi

# ── Step 3: Extract Package ID ────────────────────────────────────────────────

PACKAGE_ID=$(echo "${PUBLISH_OUTPUT}" | python3 -c "
import json, sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    # Non-JSON output: try regex fallback
    import re
    m = re.search(r'\"packageId\"\s*:\s*\"(0x[0-9a-fA-F]+)\"', raw)
    if m:
        print(m.group(1))
    else:
        sys.exit(1)
    sys.exit(0)

# Preferred: objectChanges[type=published].packageId
for change in data.get('objectChanges', []):
    if change.get('type') == 'published':
        pkg_id = change.get('packageId')
        if pkg_id:
            print(pkg_id)
            sys.exit(0)

# Fallback: effects.created[objectType contains '::package']
for obj in data.get('effects', {}).get('created', []):
    ref = obj.get('reference', obj.get('objectId', ''))
    if ref.get('objectId', '').startswith('0x') if isinstance(ref, dict) else False:
        print(ref['objectId'])
        sys.exit(0)

sys.exit(1)
" 2>/dev/null)

if [[ -z "${PACKAGE_ID}" ]]; then
    echo ""
    echo "Raw publish output:"
    echo "${PUBLISH_OUTPUT}" | head -100
    error "Could not extract packageId from publish output.
  Run: python scripts/deploy_walrusos.py --network ${NETWORK}
  for a more robust extraction."
fi

success "Package ID: ${PACKAGE_ID}"

# Also extract the LedgerAnchor shared object ID (created by init())
LEDGER_ANCHOR_ID=$(echo "${PUBLISH_OUTPUT}" | python3 -c "
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except:
    sys.exit(0)
for change in data.get('objectChanges', []):
    obj_type = change.get('objectType', '')
    if 'LedgerAnchor' in obj_type and change.get('type') == 'created':
        ref = change.get('objectId', change.get('reference', {}).get('objectId', ''))
        if ref:
            print(ref)
            sys.exit(0)
" 2>/dev/null || echo "")

if [[ -n "${LEDGER_ANCHOR_ID}" ]]; then
    success "LedgerAnchor (shared): ${LEDGER_ANCHOR_ID}"
fi

# ── Step 4: Write .env ────────────────────────────────────────────────────────

echo ""
info "Writing ${ENV_FILE}…"

# Preserve existing .env content, replace PACKAGE_ID line
if [[ -f "${ENV_FILE}" ]]; then
    # Remove old PACKAGE_ID / LEDGER_ANCHOR_ID lines
    grep -v "^WALRUSOS_PACKAGE_ID=" "${ENV_FILE}" | \
    grep -v "^WALRUSOS_LEDGER_ANCHOR_ID=" | \
    grep -v "^WALRUSOS_NETWORK=" > "${ENV_FILE}.tmp" && mv "${ENV_FILE}.tmp" "${ENV_FILE}"
fi

{
    echo "WALRUSOS_PACKAGE_ID=${PACKAGE_ID}"
    echo "WALRUSOS_NETWORK=${NETWORK}"
    [[ -n "${LEDGER_ANCHOR_ID}" ]] && echo "WALRUSOS_LEDGER_ANCHOR_ID=${LEDGER_ANCHOR_ID}"
} >> "${ENV_FILE}"

success ".env updated"

# ── Step 5: Write ~/.walrusos/config.json ─────────────────────────────────────

info "Writing ${CONFIG_FILE}…"
mkdir -p "${CONFIG_DIR}"

python3 -c "
import json, sys
from pathlib import Path

cfg_path = Path('${CONFIG_FILE}')
cfg = {}
if cfg_path.exists():
    try:
        cfg = json.loads(cfg_path.read_text())
    except:
        pass

cfg.update({
    'package_id':        '${PACKAGE_ID}',
    'network':           '${NETWORK}',
    'sui_address':       '${ACTIVE_ADDRESS}',
    'sui_rpc_url':       'https://fullnode.${NETWORK}.sui.io:443',
    'publisher_url':     'https://publisher.walrus-${NETWORK}.walrus.space',
    'aggregator_url':    'https://aggregator.walrus-${NETWORK}.walrus.space',
})
if '${LEDGER_ANCHOR_ID}':
    cfg['ledger_anchor_id'] = '${LEDGER_ANCHOR_ID}'

cfg_path.write_text(json.dumps(cfg, indent=2))
print('  Written:', str(cfg_path))
"
success "~/.walrusos/config.json updated"

# ── Step 6: Print full publish JSON for inspection ───────────────────────────

echo ""
info "Full publish output (saved to deploy_output.json):"
echo "${PUBLISH_OUTPUT}" > "${REPO_ROOT}/deploy_output.json"
echo "  ${REPO_ROOT}/deploy_output.json"

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  WalrusOS Move Package Deployed Successfully!${RESET}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo ""
echo -e "  Package ID         : ${BOLD}${PACKAGE_ID}${RESET}"
[[ -n "${LEDGER_ANCHOR_ID}" ]] && \
echo -e "  LedgerAnchor ID    : ${BOLD}${LEDGER_ANCHOR_ID}${RESET}"
echo -e "  Deployer wallet    : ${ACTIVE_ADDRESS}"
echo -e "  Network            : ${NETWORK}"
echo -e "  Sui Explorer       : https://suiscan.xyz/${NETWORK}/object/${PACKAGE_ID}"
echo ""
echo -e "  .env               : ${ENV_FILE}"
echo -e "  Config             : ${CONFIG_FILE}"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo -e "  1. python scripts/verify_deployment.py"
echo -e "  2. export WALRUSOS_PACKAGE_ID=${PACKAGE_ID}"
echo -e "  3. walrusos workspace create my-project"
echo ""
