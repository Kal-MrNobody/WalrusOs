# WalrusOS CLI Reference

The `walrusos` CLI is automatically installed when you run `pip install walrusos`.

## Shell Completion

```bash
# Bash
walrusos --install-completion bash
# Zsh
walrusos --install-completion zsh
# Fish
walrusos --install-completion fish
# PowerShell
walrusos --install-completion powershell
```

---

## Commands

### `walrusos init`
Initialise WalrusOS in the current project directory.

```bash
walrusos init --workspace research --network testnet
```

| Option | Default | Description |
|---|---|---|
| `--workspace` | `default` | Default workspace name |
| `--network` | `testnet` | Sui network |

---

### `walrusos login`
Authenticate with a Sui wallet.

```bash
walrusos login --address 0x1234…
# Auto-detect from pysui config:
walrusos login
```

---

### `walrusos status`
Show current authentication and active workspace.

```bash
walrusos status
```

---

### `walrusos workspace`
Manage WalrusOS workspaces.

```bash
walrusos workspace list
walrusos workspace create "Research Lab"
walrusos workspace use "Research Lab"
```

---

### `walrusos agent`
Register agents and publish memory events.

```bash
walrusos agent list --workspace "Research Lab"
walrusos agent create Researcher --workspace "Research Lab"
walrusos agent publish Researcher papers --payload '{"thought": "Found new paper"}'
```

---

### `walrusos memory`
Inspect MemoryStream timelines.

```bash
walrusos memory list
walrusos memory show papers --limit 10
```

---

### `walrusos replay`
Replay a MemoryStream event-by-event in the terminal.

```bash
walrusos replay papers --speed 0.5
walrusos replay papers --from evt-003
```

---

### `walrusos search`
Semantic vector search across all streams.

```bash
walrusos search "swarm intelligence" --limit 5
walrusos search "neural networks" --stream papers
```

---

### `walrusos artifacts`
Browse Walrus blob artifacts.

```bash
walrusos artifacts list
walrusos artifacts list --stream papers
walrusos artifacts download blob-abc123 --output ./downloads/
```

---

### `walrusos permissions`
Manage Sui on-chain capability tokens.

```bash
walrusos permissions list
walrusos permissions delegate Researcher papers --verbs READ,WRITE
walrusos permissions revoke cap-001
```

---

### `walrusos events`
Stream live events from the dashboard bridge.

```bash
# Requires: uvicorn dashboard.walrusos_bridge:app --port 8787
walrusos events
walrusos events --filter memory
walrusos events --url ws://localhost:8787/ws/events
```

---

### `walrusos logs`
View the local CLI log file.

```bash
walrusos logs --lines 100
walrusos logs --follow
walrusos logs --clear
```
