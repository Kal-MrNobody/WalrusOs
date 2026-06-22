"""
Walrus Storage Adapter — Production HTTP implementation.

Handles the full blob lifecycle:

  WRITE:  compress (zstd) → encrypt (AES-256-GCM, V1 format) → HTTP PUT → blob_id
  READ:   HTTP GET → parse V1 header → decrypt (AES-256-GCM) → decompress (zstd) → bytes

Key design decisions:

  AES-256-GCM so Walrus never sees plaintext.

  zstd level-3 compression (~3–10× reduction on JSON payloads).

  V1 blob format embeds the key_id in every blob header so the correct
  decryption key is always resolvable even after key rotation.

  Blob format V1 (P0 Fix — key persistence):
    b"WKEY" (4)  magic number
    b"\\x01" (1)  format version
    key_id (16)  UUID bytes of the DEK used
    nonce  (12)  AES-GCM nonce
    ct     (N)   AES-GCM ciphertext + 16-byte GCM tag
  V0 blobs (legacy) have no header; they are decrypted with whatever key
  was active at upload time.

  Walrus has NO delete API. Blobs are immutable until their storage epoch
  expires. ``delete_blob`` therefore only removes local metadata.
  ``shred_key()`` is the production deletion strategy: destroying the AES key
  makes all ciphertext permanently unreadable even if the bytes are on Walrus.

  Chunked upload for payloads > 4 MiB.
  Manifest mappings are persisted to SQLite (P0 Fix).

  Retry with exponential backoff via tenacity (5 attempts, 2–30 s).

Testnet endpoints (defaults):
  Publisher:  https://publisher.walrus-testnet.walrus.space
  Aggregator: https://aggregator.walrus-testnet.walrus.space

Mainnet: swap endpoints via WalrusOSConfig.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import zstandard as zstd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from walrusos.engine.interfaces import StorageAdapter

# Default Walrus testnet endpoints
TESTNET_PUBLISHER  = "https://publisher.walrus-testnet.walrus.space"
TESTNET_AGGREGATOR = "https://aggregator.walrus-testnet.walrus.space"

# Chunk threshold (4 MiB)
CHUNK_SIZE = 4 * 1024 * 1024

# V1 blob header magic
_BLOB_MAGIC   = b"WKEY"
_BLOB_VERSION = b"\x01"
# Header: magic(4) + version(1) + key_id(16) + nonce(12) = 33 bytes
_BLOB_HEADER_SIZE = 33


class WalrusNetworkError(Exception):
    """Raised when the Walrus network returns an unexpected response."""


class WalrusKeyDestroyedError(Exception):
    """Raised when attempting to decrypt after shred_key() was called."""


# ── Optional KeyStore import (graceful degradation) ───────────────────────────

def _load_key_store(db_path: Optional[str], wallet_address: Optional[str]):
    """
    Import and instantiate a KeyStore for persistent key management.

    Returns None if key_store is not available (test mode / no db_path).
    """
    if db_path is None:
        return None
    try:
        from walrusos.adapters.key_store import KeyStore
        return KeyStore(db_path=db_path, wallet_address=wallet_address)
    except Exception:
        return None


def _load_sqlite_ledger(db_path: Optional[str]):
    """Import SQLiteLedger for persisting manifests. Returns None if unavailable."""
    if db_path is None:
        return None
    try:
        from walrusos.adapters.sqlite_ledger import SQLiteLedger
        return SQLiteLedger(db_path=db_path)
    except Exception:
        return None


class WalrusAdapter(StorageAdapter):
    """
    Production adapter for the Walrus decentralised storage network.

    Args:
        publisher_url:  Walrus publisher endpoint.
        aggregator_url: Walrus aggregator endpoint.
        aes_key:        Optional 32-byte AES-256 key (legacy/test; if set,
                        KeyStore is not used and keys are ephemeral).
        epochs:         Number of Walrus epochs to retain blob (default: 5).
        db_path:        Path to the SQLite database for key persistence and
                        manifest storage.  If None, uses ephemeral keys (test mode).
        wallet_address: Sui wallet address used to strengthen KEK derivation.
    """

    def __init__(
        self,
        publisher_url:  str = TESTNET_PUBLISHER,
        aggregator_url: str = TESTNET_AGGREGATOR,
        aes_key:        Optional[bytes] = None,
        epochs:         int = 5,
        db_path:        Optional[str] = None,
        wallet_address: Optional[str] = None,
    ) -> None:
        self.publisher  = publisher_url.rstrip("/")
        self.aggregator = aggregator_url.rstrip("/")
        self.epochs     = epochs

        # Key management: KeyStore (persistent) takes priority over raw aes_key.
        if aes_key is not None:
            # Legacy/test mode: caller-supplied ephemeral key, no persistence.
            self._key_store   = None
            self._active_kid  = "legacy"
            self._aes_key     = bytes(aes_key)
            self._aead        = AESGCM(self._aes_key)
            self._use_v1_fmt  = False   # Don't embed key_id in legacy blobs
        elif db_path is not None:
            # Production mode: persistent KeyStore with V1 blob format.
            self._key_store  = _load_key_store(db_path, wallet_address)
            if self._key_store is not None:
                self._active_kid, dek = self._key_store.active_key()
                self._aes_key         = dek
                self._aead            = AESGCM(dek)
            else:
                # KeyStore failed (missing deps?) — fall back to ephemeral key
                self._active_kid = "ephemeral"
                self._aes_key    = AESGCM.generate_key(bit_length=256)
                self._aead       = AESGCM(self._aes_key)
            self._use_v1_fmt  = (self._key_store is not None)
        else:
            # No db_path and no aes_key — ephemeral (unit tests).
            self._key_store  = None
            self._active_kid = "ephemeral"
            self._aes_key    = AESGCM.generate_key(bit_length=256)
            self._aead       = AESGCM(self._aes_key)
            self._use_v1_fmt = False

        self._zctx_compress   = zstd.ZstdCompressor(level=3)
        self._zctx_decompress = zstd.ZstdDecompressor()

        # Manifest persistence: reuse the SQLite DB for chunk manifests
        self._sqlite = _load_sqlite_ledger(db_path)

        # In-process metadata cache: blob_id → dict (augments SQLite)
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}

        # Raw HTTP client — direct access to Walrus without crypto/compression
        # Used for integration tests, debugging, and benchmarking
        use_mocks = os.environ.get("WALRUSOS_USE_MOCKS", "").lower() in ("1", "true", "yes")
        if not use_mocks:
            from walrusos.adapters.walrus_real import RealWalrusClient
            self._raw_client: Optional[Any] = RealWalrusClient(
                publisher_url=publisher_url,
                aggregator_url=aggregator_url,
            )
        else:
            self._raw_client = None

    @property
    def raw(self):
        """
        Access the raw ``RealWalrusClient`` for unencrypted blob operations.

        Returns None when ``WALRUSOS_USE_MOCKS=1`` is set (unit test mode).
        Use this for integration testing or when you need direct blob access
        without encryption/compression.
        """
        return self._raw_client


    # ── Crypto ────────────────────────────────────────────────────────────────

    def _compress(self, data: bytes) -> bytes:
        return self._zctx_compress.compress(data)

    def _decompress(self, data: bytes) -> bytes:
        return self._zctx_decompress.decompress(data)

    def _ensure_active_aead(self) -> None:
        if self._aead is None:
            raise WalrusKeyDestroyedError(
                "AES key has been shredded — blob is permanently unreadable."
            )

    def _encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt and return bytes in V1 (with key_id header) or V0 format."""
        self._ensure_active_aead()
        nonce = os.urandom(12)
        ct    = self._aead.encrypt(nonce, plaintext, None)  # type: ignore[union-attr]

        if self._use_v1_fmt and self._key_store is not None:
            import uuid as _uuid
            kid_bytes = _uuid.UUID(self._active_kid).bytes
            return _BLOB_MAGIC + _BLOB_VERSION + kid_bytes + nonce + ct
        # V0 format (legacy / test)
        return nonce + ct

    def _decrypt(self, payload: bytes) -> bytes:
        """Decrypt a V1 or V0 blob. Resolves the correct DEK from the header."""
        if len(payload) < 13:
            raise ValueError("Ciphertext too short to contain nonce + tag")

        # Detect V1 format
        if len(payload) >= _BLOB_HEADER_SIZE and payload[:4] == _BLOB_MAGIC and payload[4:5] == _BLOB_VERSION:
            import uuid as _uuid
            key_id   = str(_uuid.UUID(bytes=payload[5:21]))
            nonce    = payload[21:33]
            ct       = payload[33:]
            aead     = self._resolve_aead(key_id)
        else:
            # V0 format: no header, use current key
            if self._aead is None:
                raise WalrusKeyDestroyedError(
                    "AES key has been shredded — blob is permanently unreadable."
                )
            nonce, ct = payload[:12], payload[12:]
            aead      = self._aead

        return aead.decrypt(nonce, ct, None)

    def _resolve_aead(self, key_id: str) -> AESGCM:
        """
        Return an AESGCM instance for the given key_id.

        Checks the current active key first (fast path), then falls back to
        the KeyStore (which may need to unwrap the retired key from SQLite).
        """
        # Fast path: current active key
        if key_id == self._active_kid and self._aead is not None:
            return self._aead

        if self._key_store is None:
            if self._aead is None:
                raise WalrusKeyDestroyedError("AES key destroyed, no key store available")
            return self._aead  # type: ignore[return-value]

        # Look up the key from the persistent store (may be a retired key)
        _, dek = self._key_store.key_by_id(key_id)
        return AESGCM(dek)

    # ── HTTP ──────────────────────────────────────────────────────────────────

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(
            (httpx.RequestError, httpx.HTTPStatusError, WalrusNetworkError)
        ),
    )
    async def _http_put(self, data: bytes) -> Dict[str, Any]:
        """PUT bytes to the Walrus publisher. Returns the blob info dict."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.put(
                f"{self.publisher}/v1/blobs?epochs={self.epochs}",
                content=data,
                headers={"Content-Type": "application/octet-stream"},
            )
            resp.raise_for_status()
            body = resp.json()

        # Walrus returns one of two shapes:
        if "newlyCreated" in body:
            info      = body["newlyCreated"]
            blob_id   = info["blobObject"]["blobId"]
            size      = info["blobObject"].get("size", len(data))
            end_epoch = info["blobObject"].get("storedEpoch", self.epochs)
        elif "alreadyCertified" in body:
            info      = body["alreadyCertified"]
            blob_id   = info["blobId"]
            size      = len(data)
            end_epoch = info.get("endEpoch", self.epochs)
        else:
            raise WalrusNetworkError(
                f"Unexpected Walrus publisher response shape: {list(body.keys())}"
            )

        return {"blob_id": blob_id, "size": size, "end_epoch": end_epoch}

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(
            (httpx.RequestError, httpx.HTTPStatusError)
        ),
    )
    async def _http_get(self, blob_id: str) -> bytes:
        """GET blob bytes from the Walrus aggregator."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(
                f"{self.aggregator}/v1/blobs/{blob_id}"
            )
            if resp.status_code == 404:
                raise KeyError(
                    f"Blob '{blob_id}' not found on Walrus aggregator. "
                    "It may not yet be certified or its epoch may have expired."
                )
            resp.raise_for_status()
            return resp.content

    async def _http_head(self, blob_id: str) -> bool:
        """Check whether a blob exists on the aggregator (HEAD request)."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.head(
                    f"{self.aggregator}/v1/blobs/{blob_id}"
                )
            return resp.status_code == 200
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    # ── Chunked upload ────────────────────────────────────────────────────────

    async def _chunked_upload(self, payload: bytes, mime_type: str) -> str:
        """
        Split large payloads into CHUNK_SIZE chunks, upload each, and store a
        manifest blob that lists all chunk blob_ids.

        P0 Fix: the manifest mapping is now also persisted to SQLite so that
        ``retrieve_blob("manifest:<id>")`` works after process restart.

        Returns a ``"manifest:<manifest_blob_id>"`` string.
        """
        chunks    = [payload[i: i + CHUNK_SIZE] for i in range(0, len(payload), CHUNK_SIZE)]
        chunk_ids: List[str] = []

        for chunk in chunks:
            enc  = self._encrypt(self._compress(chunk))
            info = await self._http_put(enc)
            chunk_ids.append(info["blob_id"])

        manifest     = json.dumps({"chunks": chunk_ids, "mime_type": mime_type}).encode()
        manifest_enc = self._encrypt(self._compress(manifest))
        info         = await self._http_put(manifest_enc)
        manifest_blob_id = "manifest:" + info["blob_id"]

        # P0 Fix: persist the manifest mapping so it survives restart
        if self._sqlite is not None:
            self._sqlite.save_blob_manifest(
                manifest_blob_id=manifest_blob_id,
                chunk_ids=chunk_ids,
                original_size=len(payload),
                mime_type=mime_type,
            )

        return manifest_blob_id

    # ── StorageAdapter interface ──────────────────────────────────────────────

    async def store_blob(self, payload: bytes, mime_type: str = "application/json") -> str:
        """
        Compress → encrypt → upload to Walrus. Returns the blob_id.

        For payloads > CHUNK_SIZE (4 MiB), uses chunked upload automatically.
        All blobs are encrypted with the V1 format (key_id embedded in header)
        when a KeyStore is configured.
        """
        if len(payload) > CHUNK_SIZE:
            blob_id = await self._chunked_upload(payload, mime_type)
            size    = len(payload)
        else:
            enc     = self._encrypt(self._compress(payload))
            info    = await self._http_put(enc)
            blob_id = info["blob_id"]
            size    = len(payload)

        self._metadata_cache[blob_id] = {
            "blob_id":    blob_id,
            "mime_type":  mime_type,
            "size_bytes": size,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "epochs":     self.epochs,
            "key_id":     self._active_kid,
        }
        return blob_id

    async def retrieve_blob(self, blob_id: str) -> bytes:
        """
        Download → decrypt → decompress. Handles manifest blobs transparently.

        After a process restart:
        - V1 blobs: key_id is embedded in the blob header, auto-resolved.
        - Manifest blobs: chunk list is recovered from SQLite (P0 Fix).
        """
        if blob_id.startswith("manifest:"):
            return await self._retrieve_manifest(blob_id[len("manifest:"):], blob_id)

        enc = await self._http_get(blob_id)
        dec = self._decrypt(enc)
        return self._decompress(dec)

    async def _retrieve_manifest(self, manifest_raw_id: str, full_blob_id: str) -> bytes:
        """
        Download and reassemble a chunked blob from its manifest.

        P0 Fix: if the manifest blob is not in the metadata cache (e.g., after
        restart), look up the chunk list from SQLite before falling back to
        downloading and decrypting the manifest blob from Walrus.
        """
        # Fast path: check SQLite for the persisted chunk list
        if self._sqlite is not None:
            chunk_ids = self._sqlite.get_blob_manifest(full_blob_id)
            if chunk_ids is not None:
                parts = [await self.retrieve_blob(cid) for cid in chunk_ids]
                return b"".join(parts)

        # Fallback: download and decrypt the manifest blob from Walrus
        enc      = await self._http_get(manifest_raw_id)
        manifest = json.loads(self._decompress(self._decrypt(enc)).decode())
        chunk_ids = manifest["chunks"]

        # Opportunistically persist the recovered manifest for next time
        if self._sqlite is not None:
            self._sqlite.save_blob_manifest(
                manifest_blob_id=full_blob_id,
                chunk_ids=chunk_ids,
                original_size=0,
                mime_type=manifest.get("mime_type", "application/octet-stream"),
            )

        parts = [await self.retrieve_blob(cid) for cid in chunk_ids]
        return b"".join(parts)

    async def delete_blob(self, blob_id: str) -> None:
        """
        Remove local metadata cache entry.

        !! IMPORTANT: Walrus has NO blob delete API. !!
        Blobs stored on Walrus are immutable until their epoch lease expires.
        To make blob content permanently unreadable, call ``shred_key()`` to
        destroy the AES decryption key. Anyone who obtained the ciphertext
        before key destruction cannot decrypt it.

        Physical deletion from the Walrus network is not possible in v0.1.
        """
        self._metadata_cache.pop(blob_id, None)

    async def blob_metadata(self, blob_id: str) -> Dict[str, Any]:
        """Return locally cached metadata. Raises KeyError if not in cache."""
        if blob_id not in self._metadata_cache:
            raise KeyError(
                f"No local metadata cached for blob '{blob_id}'. "
                "Metadata is only available for blobs uploaded in this session."
            )
        return dict(self._metadata_cache[blob_id])

    async def blob_exists(self, blob_id: str) -> bool:
        """
        Check whether a blob is accessible on the Walrus aggregator.

        Uses a HEAD request — no download occurs.
        """
        if blob_id.startswith("manifest:"):
            return await self._http_head(blob_id[len("manifest:"):])
        return await self._http_head(blob_id)

    # ── Key Management ────────────────────────────────────────────────────────

    def shred_key(self) -> None:
        """
        Cryptographic shredding: destroy the active AES key from memory.

        After calling this, blobs uploaded with the current active key become
        permanently unreadable in this process instance.  If a KeyStore is
        configured, the key record in SQLite is retired so it cannot be
        recovered.  This is the WalrusOS equivalent of secure deletion.

        Note: ``shred_key()`` does NOT destroy retired keys used for older
        blobs.  To make ALL blobs unreadable, rotate the key first, then
        shred all previous generations via ``key_store.list_keys()``.
        """
        if self._aes_key:
            # Overwrite in-place before releasing reference
            self._aes_key = b"\x00" * len(self._aes_key)
        self._aes_key = None
        self._aead    = None

    def export_key(self) -> bytes:
        """
        Return the raw AES-256 key bytes for secure backup or escrow.

        Handle with extreme care — anyone with this key can decrypt all blobs
        uploaded by this adapter instance with the current active key.
        """
        if self._aes_key is None:
            raise WalrusKeyDestroyedError("AES key has been shredded.")
        return bytes(self._aes_key)

    def rotate_key(self) -> str:
        """
        Rotate the active AES key.  Requires a configured KeyStore.

        Old blobs remain readable (retired keys are kept in the key store).
        New blobs will be encrypted with the newly generated key.

        Returns the new key_id.
        Raises RuntimeError if no KeyStore is configured.
        """
        if self._key_store is None:
            raise RuntimeError(
                "Key rotation requires a persistent KeyStore. "
                "Provide db_path= when constructing WalrusAdapter."
            )
        new_key_id = self._key_store.rotate()
        _, dek     = self._key_store.active_key()
        # Update the active AEAD context
        self._active_kid = new_key_id
        self._aes_key    = dek
        self._aead       = AESGCM(dek)
        return new_key_id
