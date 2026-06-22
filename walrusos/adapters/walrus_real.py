"""
Raw Walrus HTTP Adapter — direct blob I/O against the Walrus testnet.

This adapter performs **unencrypted, uncompressed** blob operations
against the Walrus publisher and aggregator.  It is the lowest-level
interface to Walrus and is designed for:

  - Integration testing (verify real network round-trips)
  - Debugging (inspect raw blob contents in a browser)
  - Benchmarking (measure true network latency without crypto overhead)

For production use, prefer ``WalrusAdapter`` which adds AES-256-GCM
encryption and zstd compression on top of these same HTTP calls.

Endpoints (testnet defaults):
  Publisher:  https://publisher.walrus-testnet.walrus.space
  Aggregator: https://aggregator.walrus-testnet.walrus.space

Retry policy:
  3 attempts on network errors and HTTP 5xx, with exponential backoff
  (1 s → 2 s → 4 s).

Timeouts:
  Upload:   30 s
  Download: 15 s
  HEAD:     10 s
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────

PUBLISHER_URL  = "https://publisher.walrus-testnet.walrus.space"
AGGREGATOR_URL = "https://aggregator.walrus-testnet.walrus.space"

# ── Exceptions ────────────────────────────────────────────────────────────────


class WalrusError(Exception):
    """Base exception for Walrus HTTP errors."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Walrus HTTP {status_code}: {body[:500]}")


class WalrusUploadError(WalrusError):
    """Raised when a blob upload returns an unexpected response shape."""


class WalrusBlobNotFound(Exception):
    """Raised when a blob_id does not exist on the aggregator (HTTP 404)."""

    def __init__(self, blob_id: str) -> None:
        self.blob_id = blob_id
        super().__init__(
            f"Blob '{blob_id}' not found on Walrus aggregator. "
            "It may not yet be certified or its epoch may have expired."
        )


# ── Retry helper ──────────────────────────────────────────────────────────────

_RETRY_ATTEMPTS = 3
_BACKOFF_SECONDS = [1, 2, 4]


def _should_retry(exc: Exception) -> bool:
    """Return True if the exception is retryable."""
    if isinstance(exc, httpx.RequestError):
        return True  # Network-level errors (timeout, DNS, connection reset)
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


# ── RealWalrusClient ──────────────────────────────────────────────────────────


class RealWalrusClient:
    """
    Async HTTP client for raw Walrus blob operations.

    All methods are ``async`` and use ``httpx.AsyncClient`` internally.
    The client is created lazily and reused across calls for connection pooling.

    Args:
        publisher_url:  Walrus publisher endpoint (PUT blobs).
        aggregator_url: Walrus aggregator endpoint (GET/HEAD blobs).
    """

    def __init__(
        self,
        publisher_url: str = PUBLISHER_URL,
        aggregator_url: str = AGGREGATOR_URL,
    ) -> None:
        self._publisher = publisher_url.rstrip("/")
        self._aggregator = aggregator_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialise the shared httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=30.0,
                    write=30.0,
                    pool=10.0,
                ),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── upload_blob ───────────────────────────────────────────────────────────

    async def upload_blob(
        self,
        data: bytes,
        store_epochs: int = 5,
    ) -> str:
        """
        Upload raw bytes to the Walrus publisher.

        Args:
            data:         Raw bytes to store.
            store_epochs: Number of Walrus epochs to retain the blob (default 5).

        Returns:
            The blob_id string assigned by Walrus.

        Raises:
            WalrusUploadError: If the response shape is unexpected.
            WalrusError:       On non-retryable HTTP errors.
        """
        client = await self._get_client()
        url = f"{self._publisher}/v1/blobs?epochs={store_epochs}"
        last_exc: Optional[Exception] = None

        for attempt in range(_RETRY_ATTEMPTS):
            t0 = time.perf_counter()
            try:
                resp = await client.put(
                    url,
                    content=data,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=httpx.Timeout(
                        connect=10.0, read=30.0, write=30.0, pool=10.0
                    ),
                )

                latency_ms = (time.perf_counter() - t0) * 1000

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                if resp.status_code >= 400:
                    raise WalrusError(resp.status_code, resp.text)

                body = resp.json()

                # Parse blob_id from response
                blob_id: Optional[str] = None
                if "newlyCreated" in body:
                    blob_id = body["newlyCreated"]["blobObject"]["blobId"]
                elif "alreadyCertified" in body:
                    blob_id = body["alreadyCertified"]["blobId"]

                if not blob_id:
                    raise WalrusUploadError(
                        resp.status_code,
                        f"Unexpected response shape — no blob_id found. "
                        f"Keys: {list(body.keys())}. Full body: {resp.text[:1000]}",
                    )

                logger.info(
                    "Walrus upload: blob_id=%s size=%d bytes latency=%.1f ms",
                    blob_id,
                    len(data),
                    latency_ms,
                )
                return blob_id

            except Exception as exc:
                last_exc = exc
                if _should_retry(exc) and attempt < _RETRY_ATTEMPTS - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Walrus upload attempt %d/%d failed (%s), retrying in %ds…",
                        attempt + 1,
                        _RETRY_ATTEMPTS,
                        exc,
                        wait,
                    )
                    import asyncio

                    await asyncio.sleep(wait)
                    continue
                raise

        # Should never reach here, but satisfy type checker
        raise last_exc  # type: ignore[misc]

    # ── download_blob ─────────────────────────────────────────────────────────

    async def download_blob(self, blob_id: str) -> bytes:
        """
        Download raw bytes from the Walrus aggregator.

        Args:
            blob_id: The blob ID returned by ``upload_blob``.

        Returns:
            The raw bytes of the blob.

        Raises:
            WalrusBlobNotFound: If the blob does not exist (HTTP 404).
            WalrusError:        On non-retryable HTTP errors.
        """
        client = await self._get_client()
        url = f"{self._aggregator}/v1/blobs/{blob_id}"
        last_exc: Optional[Exception] = None

        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = await client.get(
                    url,
                    timeout=httpx.Timeout(
                        connect=10.0, read=15.0, write=15.0, pool=10.0
                    ),
                )

                if resp.status_code == 404:
                    raise WalrusBlobNotFound(blob_id)

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                if resp.status_code >= 400:
                    raise WalrusError(resp.status_code, resp.text)

                return resp.content

            except WalrusBlobNotFound:
                raise  # Don't retry 404s
            except Exception as exc:
                last_exc = exc
                if _should_retry(exc) and attempt < _RETRY_ATTEMPTS - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Walrus download attempt %d/%d failed (%s), retrying in %ds…",
                        attempt + 1,
                        _RETRY_ATTEMPTS,
                        exc,
                        wait,
                    )
                    import asyncio

                    await asyncio.sleep(wait)
                    continue
                raise

        raise last_exc  # type: ignore[misc]

    # ── blob_exists ───────────────────────────────────────────────────────────

    async def blob_exists(self, blob_id: str) -> bool:
        """
        Check whether a blob exists on the Walrus aggregator (HEAD request).

        Returns True if the status code is 2xx, False on 404.
        Retries on 5xx and network errors.
        """
        client = await self._get_client()
        url = f"{self._aggregator}/v1/blobs/{blob_id}"

        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = await client.head(
                    url,
                    timeout=httpx.Timeout(
                        connect=10.0, read=10.0, write=10.0, pool=10.0
                    ),
                )

                if resp.status_code == 404:
                    return False

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )

                return 200 <= resp.status_code < 300

            except Exception as exc:
                if _should_retry(exc) and attempt < _RETRY_ATTEMPTS - 1:
                    wait = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Walrus HEAD attempt %d/%d failed (%s), retrying in %ds…",
                        attempt + 1,
                        _RETRY_ATTEMPTS,
                        exc,
                        wait,
                    )
                    import asyncio

                    await asyncio.sleep(wait)
                    continue
                # On final failure, return False rather than crashing
                logger.error("Walrus HEAD failed after %d attempts: %s", _RETRY_ATTEMPTS, exc)
                return False

        return False
