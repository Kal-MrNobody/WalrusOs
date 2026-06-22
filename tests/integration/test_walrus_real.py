"""
Integration tests for the raw Walrus HTTP adapter.

These tests call the REAL Walrus testnet — they require network access
and are gated behind the ``WALRUS_INTEGRATION=1`` environment variable.

Run with:
    WALRUS_INTEGRATION=1 pytest tests/integration/test_walrus_real.py -v -s

Every test that uploads prints the blob_id so you can manually verify
the blob in a browser at:
    https://aggregator.walrus-testnet.walrus.space/v1/blobs/<blob_id>
"""
from __future__ import annotations

import hashlib
import os
import time

import pytest
import pytest_asyncio

# Gate: only run when WALRUS_INTEGRATION=1 is set
pytestmark = pytest.mark.skipif(
    os.environ.get("WALRUS_INTEGRATION", "").lower() not in ("1", "true", "yes"),
    reason="Set WALRUS_INTEGRATION=1 to run real Walrus integration tests",
)


from walrusos.adapters.walrus_real import (
    RealWalrusClient,
    WalrusBlobNotFound,
)

AGGREGATOR = "https://aggregator.walrus-testnet.walrus.space"


@pytest_asyncio.fixture
async def walrus():
    """Create and tear down a RealWalrusClient."""
    client = RealWalrusClient()
    yield client
    await client.close()


# ── test_upload_and_download ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_and_download(walrus: RealWalrusClient):
    """Upload a payload, download it back, and assert byte-perfect equality."""
    payload = b"walrusos test payload" * 500  # ~10 KB

    # Upload
    t0 = time.perf_counter()
    blob_id = await walrus.upload_blob(payload, store_epochs=5)
    upload_ms = (time.perf_counter() - t0) * 1000

    print(f"\n{'='*60}")
    print(f"  Blob ID:     {blob_id}")
    print(f"  Upload size: {len(payload):,} bytes")
    print(f"  Upload time: {upload_ms:.1f} ms")
    print(f"  Verify at:   {AGGREGATOR}/v1/blobs/{blob_id}")
    print(f"{'='*60}")

    # Download
    t0 = time.perf_counter()
    downloaded = await walrus.download_blob(blob_id)
    download_ms = (time.perf_counter() - t0) * 1000

    print(f"  Download:    {len(downloaded):,} bytes in {download_ms:.1f} ms")

    assert downloaded == payload, (
        f"Data mismatch! Uploaded {len(payload)} bytes, got back {len(downloaded)} bytes."
    )


# ── test_blob_exists_true ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blob_exists_true(walrus: RealWalrusClient):
    """Upload a small payload, then verify blob_exists returns True."""
    payload = b"walrusos exists check"

    blob_id = await walrus.upload_blob(payload, store_epochs=5)
    print(f"\n  Blob ID: {blob_id}")
    print(f"  Verify at: {AGGREGATOR}/v1/blobs/{blob_id}")

    exists = await walrus.blob_exists(blob_id)
    assert exists is True, f"blob_exists returned False for just-uploaded blob {blob_id}"


# ── test_blob_exists_false ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blob_exists_false(walrus: RealWalrusClient):
    """Verify blob_exists returns False for a non-existent blob."""
    fake_id = "0000000000000000000000000000000000000000000"
    exists = await walrus.blob_exists(fake_id)
    assert exists is False, f"blob_exists returned True for fake blob {fake_id}"


# ── test_upload_1mb ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_1mb(walrus: RealWalrusClient):
    """Upload 1 MB of random bytes, download, and verify SHA-256 hash match."""
    payload = os.urandom(1 * 1024 * 1024)  # 1 MB
    expected_hash = hashlib.sha256(payload).hexdigest()

    # Upload
    t0 = time.perf_counter()
    blob_id = await walrus.upload_blob(payload, store_epochs=5)
    upload_ms = (time.perf_counter() - t0) * 1000

    print(f"\n{'='*60}")
    print(f"  Blob ID:      {blob_id}")
    print(f"  Upload size:  {len(payload):,} bytes (1 MB)")
    print(f"  Upload time:  {upload_ms:.1f} ms")
    print(f"  SHA-256:      {expected_hash[:32]}…")
    print(f"  Verify at:    {AGGREGATOR}/v1/blobs/{blob_id}")

    # Download
    t0 = time.perf_counter()
    downloaded = await walrus.download_blob(blob_id)
    download_ms = (time.perf_counter() - t0) * 1000

    actual_hash = hashlib.sha256(downloaded).hexdigest()

    print(f"  Download:     {len(downloaded):,} bytes in {download_ms:.1f} ms")
    print(f"  SHA-256 match: {actual_hash == expected_hash}")
    print(f"{'='*60}")

    assert len(downloaded) == len(payload), (
        f"Size mismatch: uploaded {len(payload)}, downloaded {len(downloaded)}"
    )
    assert actual_hash == expected_hash, (
        f"SHA-256 mismatch!\n"
        f"  Expected: {expected_hash}\n"
        f"  Got:      {actual_hash}"
    )


# ── test_download_nonexistent_raises ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_nonexistent_raises(walrus: RealWalrusClient):
    """Verify that downloading a non-existent blob raises WalrusBlobNotFound."""
    fake_id = "0000000000000000000000000000000000000000000"
    with pytest.raises(WalrusBlobNotFound):
        await walrus.download_blob(fake_id)
