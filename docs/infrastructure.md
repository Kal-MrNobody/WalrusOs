# Infrastructure

This page explains the Walrus storage layer and the Sui identity layer. You don't need to understand these to use WalrusOS — but if you're curious how it works under the hood, or you're running into an infrastructure issue, this is the right page.

---

## Walrus

[Walrus](https://walrus.xyz) is a decentralized blob storage network built on Sui. WalrusOS uses it to store memory event payloads.

### How blobs are stored

When you call `stream.append(payload)`, WalrusOS:

1. Serializes the payload to JSON
2. Compresses it with zstd
3. Encrypts with AES-256-GCM using your Data Encryption Key (DEK)
4. Uploads to the Walrus HTTP publisher endpoint
5. Gets back a `blob_id` — a globally unique, content-addressed identifier

When you read (via `stream.timeline()` or `stream.replay()`), the process reverses: download → decrypt → decompress → deserialize.

### The blob format

```
Offset  Size  Field
──────  ────  ─────────────────────────────────────────
0       4     Magic: 0x574B4559 ("WKEY")
4       1     Version: 0x01
5       16    Key ID (UUID, big-endian)
21      12    AES-GCM nonce (random per blob)
33      N     Ciphertext + 16-byte authentication tag
```

The key ID lets WalrusOS look up which DEK was used to encrypt this blob — even after key rotation.

### Encryption key hierarchy

```
WALRUSOS_KEY_PASSWORD (you supply this)
         ↓  PBKDF2-HMAC-SHA256 (600,000 iterations)
    Key Encryption Key (KEK)   ← never leaves your machine
         ↓  AES-256-GCM wrap
    Data Encryption Key (DEK)  ← stored wrapped in SQLite
         ↓  AES-256-GCM encryption
    Walrus blob ciphertext     ← stored on the Walrus network
```

This means:
- The data on Walrus is useless without your KEK
- The KEK is useless without your `WALRUSOS_KEY_PASSWORD`
- Losing `WALRUSOS_KEY_PASSWORD` makes your data permanently inaccessible — there's no recovery

### Key rotation

```python
# Rotate to a new DEK — old blobs remain readable, new blobs use the new key
runtime._storage.rotate_key()
```

### Cryptographic shredding

```python
# Permanently destroy the active DEK — all blobs encrypted with it become unreadable
runtime._storage.shred_key()
```

Use this to enforce data deletion without deleting blobs from Walrus (useful for GDPR compliance).

### Walrus endpoints

| Network | Publisher | Aggregator |
|---------|-----------|------------|
| Testnet | `https://publisher.walrus-testnet.walrus.space` | `https://aggregator.walrus-testnet.walrus.space` |
| Mainnet | `https://publisher.walrus.space` | `https://aggregator.walrus.space` |

```python
runtime = WalrusOS(
    publisher_url="https://publisher.walrus.space",    # mainnet
    aggregator_url="https://aggregator.walrus.space",
)
```

### Walrus epochs

Blobs are stored for a number of **epochs**. One epoch ≈ 1 day on testnet, 1 week on mainnet.

```python
runtime = WalrusOS(walrus_epochs=30)   # store for ~30 days on testnet
```

If a blob's epoch expires, it becomes unavailable. WalrusOS marks such events as `_status: PayloadLost` during recovery but continues processing other events.

### Blob retrieval caching

WalrusOS does not cache blobs locally (beyond SQLite metadata). Every `timeline()` call fetches from Walrus. For high-frequency reads, consider:

- Calling `timeline()` once and storing the result in memory
- Using `stream.search()` (which uses the local vector index, not Walrus)

---

## Sui

[Sui](https://sui.io) is the blockchain WalrusOS uses for identity and tamper-evident event anchoring.

### What Sui does for WalrusOS

| Sui object | Purpose |
|------------|---------|
| `Workspace` | Named container owned by a wallet address |
| `AgentIdentity` | Agent's public key, status, and counters, stored on-chain |
| `MemoryStream` | Anchor point for a stream's event history |
| `Capability` | Permission token; a Move object you can transfer or burn |
| `MemoryEvent` | On-chain record of every event's blob ID and signature |

### The write path

When `stream.append()` is called in production mode:

1. The event is written to local SQLite (synchronous — fast)
2. A Sui transaction is submitted asynchronously (fire-and-forget)
3. The Sui transaction anchors the event: `{ event_id, blob_id, blob_hash, signature }`
4. The transaction digest is stored in SQLite when it completes

If the Sui transaction fails, the event is still valid locally and in Walrus. Sui anchoring will be retried.

### The read path

Reads always come from local SQLite — zero Sui RPC latency. Sui is only queried during:

- Full disaster recovery (`walrusos recover`)
- Capability verification against on-chain objects
- Initial wallet connection

### Running without Sui

WalrusOS runs without a Sui wallet configured. In this mode:

- Data is still uploaded to Walrus and encrypted
- Events are indexed in local SQLite
- No on-chain anchoring occurs
- Recovery is limited to local SQLite + Walrus (not from blockchain)

This is fine for development and for applications that don't need on-chain tamper evidence.

### Connecting a wallet

```bash
# Install Sui CLI
curl -fsSL https://docs.sui.io/references/cli | sh

# Create a wallet
sui client new-address ed25519

# Set it as active
sui client active-address

# Connect to WalrusOS
walrusos login
```

Or configure programmatically:

```python
runtime = WalrusOS(
    sui_rpc_url="https://fullnode.mainnet.sui.io:443",
    package_id="0x1234...abcd",   # deployed WalrusOS Move package
)
```

### Deploying the Move package

WalrusOS's on-chain logic is written in Move. A pre-deployed package is available on testnet — you don't need to deploy your own.

To deploy your own:

```bash
python scripts/deploy_walrusos.py
# Outputs: WALRUSOS_PACKAGE_ID=0x...
export WALRUSOS_PACKAGE_ID=0x...
```

### Capability tokens

In production with Sui connected, capabilities are Move objects:

```python
# Grant capability on-chain
await workspace.grant(
    from_agent=owner,
    to_agent=collaborator,
    capability="write",
    stream=owner.stream("research"),
    valid_until_epoch=1000,    # 0 = never expires
)

# The collaborator now holds a Capability Move object
# They can write to the stream until you revoke it or it expires
```

Revoking a capability burns the Move object. The collaborator can no longer produce valid Sui transactions for that stream, regardless of what their local SQLite says.

---

## SQLite: the local cache

WalrusOS uses SQLite as a local write-through cache for:

- Event metadata (event_id, timestamp, blob_id, signature, parent_id)
- Agent identities
- Stream → Sui object ID mappings
- Encryption key records (wrapped DEKs)
- Vector embeddings (TF-IDF index)

The SQLite database is the primary source of truth for all reads. This means:

- Reads are fast (no network)
- Writes go to SQLite first, then to Walrus and Sui asynchronously
- SQLite can be rebuilt from Walrus + Sui via `walrusos recover`

**Database location:** `~/.walrusos/walrusos.db` (configurable)

**Security:** The database contains wrapped (encrypted) DEKs. An attacker who steals the database still cannot decrypt your blobs without your `WALRUSOS_KEY_PASSWORD` and `~/.walrusos/.machine_secret`.
