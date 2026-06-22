"""
Protocol Hardening Phase 1 — P0 Fix Integration Tests.

Tests every critical fix implemented in Protocol Hardening Phase 1.
These tests run with zero external dependencies (no Walrus network, no Sui node)
using mock/in-process adapters to verify the correctness guarantees.

For real network integration tests, see tests/integration/test_walrus.py
and tests/integration/test_sui.py (gated by WALRUS_INTEGRATION=1).

What is tested:
  Fix 1a: AES key is persisted to SQLite and survives process restart simulation.
  Fix 1b: Key rotation generates a new key; old blobs remain readable.
  Fix 1c: V1 blob format embeds key_id; correct key is resolved on decrypt.
  Fix 2:  Chunk manifest IDs are persisted; chunked blobs recoverable after restart.
  Fix 3:  Sui stream object mappings persist to SQLite and are restored on init.
  Fix 4:  delegate_capability now passes valid_until_epoch (4 args, not 3).
  Fix 5a: cmd_replay no longer uses use_mocks=True.
  Fix 5b: walrusos_bridge no longer uses use_mocks=True or hardcoded data.
  Fix 5c: All example files have been updated.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path) -> str:
    """Return a path to a temporary SQLite database."""
    return str(tmp_path / "test_walrusos.db")


@pytest.fixture
def key_store(tmp_db):
    """KeyStore backed by a temp SQLite database."""
    os.environ.setdefault("WALRUSOS_KEY_PASSWORD", "test-password-p0-hardening")
    from walrusos.adapters.key_store import KeyStore
    return KeyStore(db_path=tmp_db, wallet_address="0x" + "a" * 64)


@pytest.fixture
def sqlite_ledger(tmp_db):
    """SQLiteLedger backed by a temp database."""
    from walrusos.adapters.sqlite_ledger import SQLiteLedger
    return SQLiteLedger(db_path=tmp_db)


@pytest.fixture
def walrus_adapter(tmp_db):
    """WalrusAdapter in production-key mode (KeyStore) backed by temp DB."""
    os.environ.setdefault("WALRUSOS_KEY_PASSWORD", "test-password-p0-hardening")
    from walrusos.adapters.walrus import WalrusAdapter
    return WalrusAdapter(db_path=tmp_db, wallet_address="0x" + "a" * 64)


# ── FIX 1a: Key persistence survives restart simulation ──────────────────────

class TestKeyPersistence:
    """P0 Fix 1: AES keys are persisted and survive process restarts."""

    def test_key_store_creates_active_key_on_init(self, key_store):
        """A new KeyStore automatically generates an active key."""
        key_id, dek = key_store.active_key()
        assert isinstance(key_id, str) and len(key_id) == 36  # UUID format
        assert isinstance(dek, bytes) and len(dek) == 32  # 256-bit AES key

    def test_key_store_restores_key_after_reinit(self, tmp_db):
        """Simulating a process restart: same key is restored from SQLite."""
        os.environ.setdefault("WALRUSOS_KEY_PASSWORD", "test-password-p0-hardening")
        from walrusos.adapters.key_store import KeyStore

        # "Process 1" — create and get key
        ks1 = KeyStore(db_path=tmp_db, wallet_address="0x" + "a" * 64)
        key_id_1, dek_1 = ks1.active_key()

        # "Process 2" — new instance, same DB (simulates restart)
        ks2 = KeyStore(db_path=tmp_db, wallet_address="0x" + "a" * 64)
        key_id_2, dek_2 = ks2.active_key()

        assert key_id_1 == key_id_2, "Key ID must be identical across restarts"
        assert dek_1 == dek_2,       "DEK must be identical across restarts"

    def test_key_store_does_not_create_duplicate_keys(self, tmp_db):
        """Multiple KeyStore instances on the same DB don't multiply keys."""
        os.environ.setdefault("WALRUSOS_KEY_PASSWORD", "test-password-p0-hardening")
        from walrusos.adapters.key_store import KeyStore

        for _ in range(3):
            ks = KeyStore(db_path=tmp_db, wallet_address="0x" + "b" * 64)

        keys = ks.list_keys()
        active = [k for k in keys if k["is_active"]]
        assert len(active) == 1, "Must have exactly 1 active key"


# ── FIX 1b: Key rotation ──────────────────────────────────────────────────────

class TestKeyRotation:
    """P0 Fix 1: Key rotation generates a new key; old blobs remain readable."""

    def test_rotate_generates_new_key_id(self, key_store):
        """rotate() returns a different key_id."""
        key_id_before, _ = key_store.active_key()
        new_key_id        = key_store.rotate()
        key_id_after, _   = key_store.active_key()

        assert new_key_id != key_id_before
        assert key_id_after == new_key_id

    def test_rotate_retires_old_key_but_keeps_it(self, key_store):
        """Retired key is kept in the store for old-blob decryption."""
        old_key_id, old_dek = key_store.active_key()
        key_store.rotate()

        # Old key must still be resolvable
        _, resolved_dek = key_store.key_by_id(old_key_id)
        assert resolved_dek == old_dek

    def test_rotate_increments_generation(self, key_store):
        """Each rotation increments the generation counter."""
        key_store.rotate()
        keys = key_store.list_keys()
        active = [k for k in keys if k["is_active"]][0]
        assert active["generation"] == 2

    def test_old_blob_readable_after_rotation(self, walrus_adapter):
        """
        A blob encrypted with key gen-1 is still decryptable after rotating to gen-2.
        Uses WalrusAdapter in-process (no network) — only tests crypto path.
        """
        # Encrypt with current (gen-1) key
        plaintext = b"important data from before rotation"
        encrypted = walrus_adapter._encrypt(walrus_adapter._compress(plaintext))

        # Rotate to gen-2
        walrus_adapter.rotate_key()

        # V1 header embeds the gen-1 key_id — decryption should succeed
        decrypted = walrus_adapter._decompress(walrus_adapter._decrypt(encrypted))
        assert decrypted == plaintext, "Old blob must remain readable after key rotation"


# ── FIX 1c: V1 blob format ───────────────────────────────────────────────────

class TestBlobFormatV1:
    """P0 Fix 1: V1 blob format embeds key_id so correct key is always resolved."""

    def test_v1_blob_has_wkey_magic(self, walrus_adapter):
        """Blobs produced by the KeyStore-backed adapter have the WKEY header."""
        if not walrus_adapter._use_v1_fmt:
            pytest.skip("V1 format requires a configured KeyStore")
        payload   = b"test payload for v1 format"
        encrypted = walrus_adapter._encrypt(walrus_adapter._compress(payload))
        assert encrypted[:4] == b"WKEY", "V1 blob must start with WKEY magic"

    def test_v1_blob_key_id_is_parseable(self, walrus_adapter):
        """The key_id embedded in the V1 blob header matches the active key."""
        if not walrus_adapter._use_v1_fmt:
            pytest.skip("V1 format requires a configured KeyStore")
        from walrusos.adapters.key_store import KeyStore
        active_kid, _ = walrus_adapter._key_store.active_key()
        encrypted      = walrus_adapter._encrypt(walrus_adapter._compress(b"data"))
        parsed_kid, nonce, ct = KeyStore.parse_v1_header(encrypted)
        assert parsed_kid == active_kid, "Parsed key_id must match active key"

    def test_v0_blob_decrypts_with_current_key(self):
        """V0 blobs (no WKEY header) still decrypt correctly."""
        from walrusos.adapters.walrus import WalrusAdapter
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os as _os

        # Build adapter in legacy/test mode (aes_key=supplied, no KeyStore)
        key  = AESGCM.generate_key(bit_length=256)
        adp  = WalrusAdapter(aes_key=key)
        data = b"v0 legacy blob"

        enc = adp._encrypt(adp._compress(data))
        assert enc[:4] != b"WKEY", "Legacy adapter must produce V0 format"
        dec = adp._decompress(adp._decrypt(enc))
        assert dec == data


# ── FIX 2: Chunk manifest persistence ─────────────────────────────────────────

class TestChunkManifestPersistence:
    """P0 Fix 2: Chunk manifests are persisted to SQLite and survive restarts."""

    def test_save_and_get_blob_manifest(self, sqlite_ledger):
        """save_blob_manifest + get_blob_manifest round-trip."""
        manifest_id = "manifest:abc123def456"
        chunk_ids   = ["chunk-1", "chunk-2", "chunk-3"]

        sqlite_ledger.save_blob_manifest(
            manifest_blob_id=manifest_id,
            chunk_ids=chunk_ids,
            original_size=12_582_912,  # 12 MiB
            mime_type="application/octet-stream",
        )

        result = sqlite_ledger.get_blob_manifest(manifest_id)
        assert result == chunk_ids

    def test_get_blob_manifest_returns_none_for_unknown(self, sqlite_ledger):
        """get_blob_manifest returns None for an unknown manifest ID."""
        result = sqlite_ledger.get_blob_manifest("manifest:not-in-db")
        assert result is None

    def test_save_blob_manifest_is_idempotent(self, sqlite_ledger):
        """Calling save_blob_manifest twice for the same ID does not error."""
        manifest_id = "manifest:idempotency-test"
        sqlite_ledger.save_blob_manifest(manifest_id, ["a", "b"], 100)
        sqlite_ledger.save_blob_manifest(manifest_id, ["a", "b"], 100)  # second call — must not raise

    @pytest.mark.asyncio
    async def test_adapter_persists_manifest_on_chunked_upload(self, tmp_db, monkeypatch):
        """
        When WalrusAdapter uploads a chunked blob (>4 MiB), it persists the
        manifest to SQLite via self._sqlite.save_blob_manifest().
        """
        os.environ.setdefault("WALRUSOS_KEY_PASSWORD", "test-pw")
        from walrusos.adapters.walrus import WalrusAdapter, CHUNK_SIZE

        # Intercept HTTP so we don't hit real Walrus
        upload_counter = [0]
        async def fake_http_put(self, data):
            upload_counter[0] += 1
            return {"blob_id": f"fake-blob-{upload_counter[0]:04d}", "size": len(data), "end_epoch": 5}

        monkeypatch.setattr(WalrusAdapter, "_http_put", fake_http_put)

        adapter = WalrusAdapter(db_path=tmp_db)
        payload = b"X" * (CHUNK_SIZE + 1024)   # > 4 MiB
        blob_id = await adapter.store_blob(payload)

        assert blob_id.startswith("manifest:")

        # Manifest must be in SQLite
        result = adapter._sqlite.get_blob_manifest(blob_id)
        assert result is not None
        assert len(result) == 2   # 2 chunks (one full, one partial)


# ── FIX 3: Sui stream object persistence ─────────────────────────────────────

class TestSuiStreamObjectPersistence:
    """P0 Fix 3: stream_id → Sui object ID mappings persist across restarts."""

    def test_save_and_load_sui_stream_object(self, sqlite_ledger):
        """save_sui_stream_object + get_sui_stream_objects round-trip."""
        stream_id  = uuid.uuid4()
        sui_obj_id = "0x" + "a" * 64

        sqlite_ledger.save_sui_stream_object(stream_id, sui_obj_id)
        mapping = sqlite_ledger.get_sui_stream_objects()

        assert str(stream_id) in mapping
        assert mapping[str(stream_id)] == sui_obj_id

    def test_delete_sui_stream_object(self, sqlite_ledger):
        """delete_sui_stream_object removes the mapping."""
        stream_id  = uuid.uuid4()
        sqlite_ledger.save_sui_stream_object(stream_id, "0x" + "b" * 64)
        sqlite_ledger.delete_sui_stream_object(stream_id)
        mapping = sqlite_ledger.get_sui_stream_objects()
        assert str(stream_id) not in mapping

    def test_sui_stream_objects_restored_on_adapter_init(self, tmp_db):
        """
        SuiLedgerAdapter._stream_objects is populated from SQLite at __init__,
        not empty as it was before the P0 fix.
        """
        from walrusos.adapters.sqlite_ledger import SQLiteLedger

        # Pre-populate SQLite with a mapping
        ledger     = SQLiteLedger(db_path=tmp_db)
        stream_id  = uuid.uuid4()
        sui_obj_id = "0x" + "c" * 64
        ledger.save_sui_stream_object(stream_id, sui_obj_id)

        # Build a SuiLedgerAdapter over the same DB
        from walrusos.adapters.sui import SuiIdentityAdapter, SuiLedgerAdapter
        identity = SuiIdentityAdapter.__new__(SuiIdentityAdapter)
        identity.active_address = "0x" + "0" * 64
        identity.is_connected   = False
        identity._config        = None
        identity._client        = None
        identity._rpc_url       = None

        sui_ledger = SuiLedgerAdapter(
            identity=identity,
            package_id=None,
            db_path=tmp_db,
        )

        # _stream_objects must be restored from SQLite
        assert str(stream_id) in sui_ledger._stream_objects
        assert sui_ledger._stream_objects[str(stream_id)] == sui_obj_id


# ── FIX 4: delegate_capability parameter count ───────────────────────────────

class TestDelegateCapabilityParameters:
    """P0 Fix 4: delegate_capability passes all 4 arguments to the Move PTB."""

    def test_delegate_capability_signature_has_valid_until_epoch(self):
        """SuiIdentityAdapter.delegate_capability has a valid_until_epoch param."""
        import inspect
        from walrusos.adapters.sui import SuiIdentityAdapter
        sig = inspect.signature(SuiIdentityAdapter.delegate_capability)
        assert "valid_until_epoch" in sig.parameters, (
            "delegate_capability must have valid_until_epoch parameter to match Move"
        )

    def test_delegate_capability_valid_until_epoch_defaults_to_zero(self):
        """valid_until_epoch defaults to 0 (never expires) for backward compat."""
        import inspect
        from walrusos.adapters.sui import SuiIdentityAdapter
        sig     = inspect.signature(SuiIdentityAdapter.delegate_capability)
        default = sig.parameters["valid_until_epoch"].default
        assert default == 0, "valid_until_epoch default must be 0 (never expires)"

    @pytest.mark.asyncio
    async def test_delegate_capability_passes_four_args_to_ptb(self):
        """
        When delegate_capability calls move_call, it must pass exactly 4 arguments
        (target_stream, bitmask, recipient, valid_until_epoch), matching the Move
        function signature in identity.move.
        """
        from walrusos.adapters.sui import SuiIdentityAdapter

        identity = SuiIdentityAdapter.__new__(SuiIdentityAdapter)
        identity.active_address = "0x" + "1" * 64
        identity.is_connected   = True
        identity._config        = None
        identity._rpc_url       = None

        recorded_args = []

        class FakeTxn:
            def pure(self, value, encode_as):
                return {"val": value, "as": encode_as}
            def move_call(self, target, arguments, type_arguments):
                recorded_args.extend(arguments)
            async def execute(self, gas_budget):
                r = MagicMock()
                r.is_err.return_value = False
                r.result_data.digest = "fake-digest-" + "a" * 40
                return r

        with patch.object(
            identity, "_require_connected", return_value=None
        ), patch(
            "walrusos.adapters.sui._import_pysui",
            return_value=(None, None, lambda client: FakeTxn()),
        ):
            identity._client = None
            await identity.delegate_capability(
                target_stream_address="0x" + "2" * 64,
                bitmask=3,
                recipient="0x" + "3" * 64,
                package_id="0x" + "4" * 64,
                valid_until_epoch=100,
            )

        assert len(recorded_args) == 4, (
            f"Expected 4 PTB arguments, got {len(recorded_args)}: {recorded_args}"
        )
        # Verify the 4th arg is valid_until_epoch=100
        assert recorded_args[3] == {"val": 100, "as": "u64"}, (
            f"4th argument must be valid_until_epoch=100, got: {recorded_args[3]}"
        )


# ── FIX 5: No use_mocks in production code ────────────────────────────────────

class TestNoProductionMocks:
    """P0 Fix 5: Production files must not contain use_mocks=True."""

    PRODUCTION_FILES = [
        "walrusos/cli/cmd_replay.py",
        "dashboard/walrusos_bridge.py",
        "examples/01_research_team/main.py",
        "examples/02_software_engineering/main.py",
        "examples/03_trading_team/main.py",
        "examples/04_customer_support/main.py",
        "examples/05_scientific_research/main.py",
        "examples/firebase_like_api.py",
        "examples/integration_langgraph.py",
    ]

    @pytest.mark.parametrize("rel_path", PRODUCTION_FILES)
    def test_no_use_mocks_true_in_production_file(self, rel_path):
        """Production files must not hard-code use_mocks=True as executable code."""
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        full_path = os.path.join(repo_root, rel_path)

        if not os.path.exists(full_path):
            pytest.skip(f"File not found: {full_path}")

        content = open(full_path, encoding="utf-8").read()

        # Strip all comments and triple-quoted strings before searching.
        # We only care about executable use_mocks=True, not documentation.
        import ast, tokenize, io
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
        except tokenize.TokenError:
            tokens = []

        code_only_lines = set()
        for tok in tokens:
            if tok.type not in (
                tokenize.COMMENT,
                tokenize.STRING,   # catches docstrings too
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.ENCODING,
            ):
                code_only_lines.add(tok.start[0])

        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if i not in code_only_lines:
                continue   # comment, docstring, or whitespace-only — skip
            if "use_mocks=True" in line:
                pytest.fail(
                    f"{rel_path}:{i}: Found use_mocks=True in executable code: {line!r}"
                )

    def test_cmd_replay_uses_get_runtime(self):
        """cmd_replay must use get_runtime() not WalrusOS(use_mocks=True)."""
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        path      = os.path.join(repo_root, "walrusos/cli/cmd_replay.py")
        content   = open(path, encoding="utf-8").read()
        assert "get_runtime()" in content, "cmd_replay must use get_runtime()"

    def test_bridge_uses_get_runtime(self):
        """dashboard bridge must use get_runtime() not WalrusOS(use_mocks=True)."""
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        path      = os.path.join(repo_root, "dashboard/walrusos_bridge.py")
        content   = open(path, encoding="utf-8").read()
        assert "get_runtime()" in content, "walrusos_bridge must use get_runtime()"
        # Must not have hardcoded fake workspace data from before the fix
        assert '"Research Lab"' not in content, (
            "Bridge must not have hardcoded 'Research Lab' fake workspace"
        )


# ── WAL mode enabled ──────────────────────────────────────────────────────────

class TestSQLiteWALMode:
    """SQLite ledger must run in WAL mode for crash safety."""

    def test_sqlite_wal_mode_enabled(self, sqlite_ledger):
        """The SQLite ledger must be running in WAL journal mode."""
        import sqlalchemy as sa
        with sqlite_ledger._engine.connect() as conn:
            mode = conn.execute(sa.text("PRAGMA journal_mode;")).scalar()
        assert mode.lower() == "wal", (
            f"SQLite must use WAL journal mode for crash safety, got: {mode!r}"
        )
