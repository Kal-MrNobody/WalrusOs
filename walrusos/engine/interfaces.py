"""
Abstract interfaces for WalrusOS storage adapters.

All storage, ledger, and vector operations are defined here.
The MemoryEngine depends only on these abstractions — never on concrete adapters.
This enables swapping InMemory ↔ Walrus/Sui without touching engine logic.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple

from walrusos.core.models.memory import MemoryEvent


# ── Storage ───────────────────────────────────────────────────────────────────

class StorageAdapter(ABC):
    """Abstract blob storage: compress, encrypt, upload, download."""

    @abstractmethod
    async def store_blob(self, payload: bytes, mime_type: str = "application/json") -> str:
        """Persist bytes and return a content-addressed blob ID."""

    @abstractmethod
    async def retrieve_blob(self, blob_id: str) -> bytes:
        """Fetch raw bytes by blob ID. Raises ``KeyError`` if not found."""

    @abstractmethod
    async def delete_blob(self, blob_id: str) -> None:
        """Remove a blob from storage. No-op if not found."""

    @abstractmethod
    async def blob_metadata(self, blob_id: str) -> Dict[str, Any]:
        """Return size, mime_type, created_at, and any adapter-specific metadata."""


# ── Ledger ────────────────────────────────────────────────────────────────────

class LedgerAdapter(ABC):
    """Abstract event ledger: DAG of immutable MemoryEvents."""

    @abstractmethod
    async def create_stream(self, agent_id: uuid.UUID) -> uuid.UUID:
        """Create a new MemoryStream and return its ID."""

    @abstractmethod
    async def delete_stream(self, stream_id: uuid.UUID) -> None:
        """Remove a stream and all its events. Irreversible."""

    @abstractmethod
    async def append_event(self, stream_id: uuid.UUID, event: MemoryEvent) -> None:
        """Append an event to the stream and advance its head pointer."""

    @abstractmethod
    async def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        """Fetch a single event by its deterministic ID."""

    @abstractmethod
    async def get_head(self, stream_id: uuid.UUID) -> Optional[str]:
        """Return the current head event ID, or ``None`` for an empty stream."""

    @abstractmethod
    async def list_events(self, stream_id: uuid.UUID) -> List[MemoryEvent]:
        """Return all events in a stream in append order (oldest first)."""


# ── Vector ────────────────────────────────────────────────────────────────────

class VectorAdapter(ABC):
    """Abstract vector index for semantic similarity search."""

    @abstractmethod
    async def upsert(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
        """Index or update a document. Called on every append."""

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return top-``limit`` results ranked by cosine similarity.

        Each result dict has keys: ``doc_id``, ``score``, ``metadata``.
        """

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        """Remove a document from the index."""
