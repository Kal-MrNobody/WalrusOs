"""
InMemory adapter implementations.

These are the default adapters used in ``WalrusOS(use_mocks=True)`` mode.
They are also used in all unit tests so the test suite runs with zero
external dependencies (no Walrus network, no Sui node).

Design goals:
- Fully correct semantics (same behaviour as production adapters)
- Real vector similarity via TF-IDF cosine similarity (no ML deps)
- Thread-safe enough for single-process asyncio use
"""
from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from walrusos.engine.interfaces import LedgerAdapter, StorageAdapter, VectorAdapter
from walrusos.core.models.memory import MemoryEvent
from walrusos.core.models.events import ProtocolEvent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


def _tf(tokens: List[str]) -> Dict[str, float]:
    counts: Dict[str, int] = defaultdict(int)
    for t in tokens:
        counts[t] += 1
    total = len(tokens) or 1
    return {k: v / total for k, v in counts.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values())) or 1.0
    mag_b = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (mag_a * mag_b)


# ── Storage ───────────────────────────────────────────────────────────────────

class InMemoryStorage(StorageAdapter):
    """Content-addressed blob store backed by a plain dict."""

    def __init__(self) -> None:
        self._blobs: Dict[str, bytes] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}

    async def store_blob(self, payload: bytes, mime_type: str = "application/json") -> str:
        blob_id = hashlib.sha256(payload).hexdigest()
        self._blobs[blob_id] = payload
        self._meta[blob_id] = {
            "blob_id":    blob_id,
            "mime_type":  mime_type,
            "size_bytes": len(payload),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return blob_id

    async def retrieve_blob(self, blob_id: str) -> bytes:
        if blob_id not in self._blobs:
            raise KeyError(f"Blob '{blob_id}' not found in InMemoryStorage")
        return self._blobs[blob_id]

    async def delete_blob(self, blob_id: str) -> None:
        self._blobs.pop(blob_id, None)
        self._meta.pop(blob_id, None)

    async def blob_metadata(self, blob_id: str) -> Dict[str, Any]:
        if blob_id not in self._meta:
            raise KeyError(f"Blob '{blob_id}' not found")
        return dict(self._meta[blob_id])


# ── Ledger ────────────────────────────────────────────────────────────────────

class InMemoryLedger(LedgerAdapter):
    """In-process DAG ledger. All data is lost on process exit."""

    def __init__(self) -> None:
        # stream_id → current head event_id (or "genesis" for empty)
        self.streams: Dict[uuid.UUID, str] = {}
        # event_id → MemoryEvent
        self.events: Dict[str, MemoryEvent] = {}
        # stream_id → ordered list of event_ids (append order)
        self._order: Dict[uuid.UUID, List[str]] = defaultdict(list)

    async def create_stream(self, agent_id: uuid.UUID) -> uuid.UUID:
        stream_id = uuid.uuid4()
        self.streams[stream_id] = "genesis"
        return stream_id

    async def delete_stream(self, stream_id: uuid.UUID) -> None:
        event_ids = self._order.pop(stream_id, [])
        for eid in event_ids:
            self.events.pop(eid, None)
        self.streams.pop(stream_id, None)

    async def append_event(self, stream_id: uuid.UUID, event: MemoryEvent) -> None:
        # Handle both MemoryEvent and ProtocolEvent during migration
        ev_id = getattr(event, "event_id", getattr(event, "id", None))
        if not ev_id:
            raise ValueError("Event is missing ID")

        self.events[ev_id] = event
        self.streams[stream_id] = ev_id
        self._order[stream_id].append(ev_id)

    async def get_event(self, event_id: str) -> Optional[MemoryEvent]:
        return self.events.get(event_id)

    async def append_protocol_event(self, event: ProtocolEvent) -> None:
        """Store an immutable ProtocolEvent."""
        self.events[event.event_id] = event # type: ignore
        # Index by agent and workspace for mock replays
        if not hasattr(self, "_agent_events"):
            self._agent_events = defaultdict(list)
            self._workspace_events = defaultdict(list)
            
        if event.agent_id:
            self._agent_events[event.agent_id].append(event)
        if event.workspace_id:
            self._workspace_events[event.workspace_id].append(event)
            
        # Update stream head is now handled by append_event for MemoryAppended events
        # to avoid duplicating entries when EventStoreEngine calls both.

    async def get_events_for_agent(self, agent_id: str) -> List[ProtocolEvent]:
        if hasattr(self, "_agent_events"):
            return self._agent_events.get(agent_id, [])
        return []

    async def get_events_for_workspace(self, workspace_id: str) -> List[ProtocolEvent]:
        if hasattr(self, "_workspace_events"):
            return self._workspace_events.get(workspace_id, [])
        return []

    async def get_head(self, stream_id: uuid.UUID) -> Optional[str]:
        head = self.streams.get(stream_id)
        return head if head != "genesis" else None

    async def timeline(self, stream_id: uuid.UUID) -> List[MemoryEvent]:
        # Implementation returns MemoryEvents or dictionaries, depending on caller logic.
        return [self.events[eid] for eid in self._order.get(stream_id, [])]

    # ── Task Methods (Mock for testing) ───────────────────────────────────────

    def save_task(self, task: "Task") -> None:
        if not hasattr(self, "_tasks"):
            self._tasks = {}
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> Optional["Task"]:
        if not hasattr(self, "_tasks"):
            return None
        return self._tasks.get(task_id)

    def list_tasks(self, workspace_id: str, status: Optional[str] = None, assigned_to: Optional[str] = None, tag: Optional[str] = None) -> List["Task"]:
        if not hasattr(self, "_tasks"):
            return []
        res = []
        for t in self._tasks.values():
            if t.workspace_id != workspace_id:
                continue
            if status and t.status != status:
                continue
            if assigned_to and t.assigned_to != assigned_to:
                continue
            if tag and tag not in t.tags:
                continue
            res.append(t)
        return res

    # ── Agent Identity methods ──────────────────────────────────────────────────────────────────────────────

    async def list_events(self, stream_id: uuid.UUID) -> List[MemoryEvent]:
        """Return all events in append order (oldest first)."""
        return [
            self.events[eid]
            for eid in self._order.get(stream_id, [])
            if eid in self.events
        ]


# ── Vector ────────────────────────────────────────────────────────────────────

class InMemoryVector(VectorAdapter):
    """
    TF-IDF cosine similarity vector index.

    No ML framework required — uses pure Python math.
    Sufficient for development, testing, and small corpora (<50K events).
    For production scale, swap with a pgvector or Qdrant adapter.
    """

    def __init__(self) -> None:
        # doc_id → {"tf": Dict[str, float], "metadata": Dict}
        self._index: Dict[str, Dict[str, Any]] = {}
        # term → set of doc_ids containing that term (for IDF)
        self._doc_freq: Dict[str, int] = defaultdict(int)

    def _idf(self, term: str) -> float:
        n_docs = len(self._index) or 1
        df = self._doc_freq.get(term, 0) + 1  # +1 smoothing
        return math.log(n_docs / df) + 1.0

    def _tfidf(self, tf: Dict[str, float]) -> Dict[str, float]:
        return {term: score * self._idf(term) for term, score in tf.items()}

    async def upsert(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
        tokens = _tokenize(text)
        if not tokens:
            return
        tf = _tf(tokens)
        # Remove old doc from doc_freq index if re-indexing
        old = self._index.get(doc_id)
        if old:
            for term in old["tf"]:
                self._doc_freq[term] = max(0, self._doc_freq[term] - 1)
        # Add new doc
        for term in tf:
            self._doc_freq[term] += 1
        self._index[doc_id] = {"tf": tf, "metadata": metadata, "text": text}

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self._index:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        q_tf     = _tf(q_tokens)
        q_tfidf  = self._tfidf(q_tf)

        results = []
        for doc_id, doc in self._index.items():
            d_tfidf = self._tfidf(doc["tf"])
            score   = _cosine(q_tfidf, d_tfidf)
            if score > 0:
                results.append({
                    "doc_id":   doc_id,
                    "score":    round(score, 6),
                    "metadata": doc["metadata"],
                    "text":     doc["text"],
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]

    async def delete(self, doc_id: str) -> None:
        doc = self._index.pop(doc_id, None)
        if doc:
            for term in doc["tf"]:
                self._doc_freq[term] = max(0, self._doc_freq[term] - 1)
