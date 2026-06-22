"""
LlamaIndex integration — ``WalrusChatStore`` and ``WalrusDocumentStore``

Persists LlamaIndex chat history and document embeddings to WalrusOS.

Usage::

    from walrusos import WalrusOS
    from walrusos.integrations.llamaindex import WalrusChatStore, WalrusDocumentStore

    runtime   = WalrusOS()
    workspace = runtime.workspace("rag")

    # Chat history
    chat_store = WalrusChatStore(workspace.stream("chat"))

    # Document store (index node metadata)
    doc_store  = WalrusDocumentStore(workspace.stream("docs"))

Compatibility: ``llama-index-core >= 0.10.0``
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from walrusos.sdk.stream import StreamClient

# Integration requires a bound StreamClient


class WalrusChatStore:
    """
    LlamaIndex ``BaseChatStore`` backed by a WalrusOS MemoryStream.

    Provides ``add_message`` / ``get_messages`` / ``delete_messages`` /
    ``delete_last_message`` with full conversation key isolation.
    """

    def __init__(self, stream: StreamClient) -> None:
        self.stream       = stream

    async def add_message(self, key: str, message: Any) -> None:
        """
        Append a LlamaIndex ``ChatMessage`` to the store.

        Serialises the message to a dict containing ``role`` and ``content``.
        """
        payload: Dict[str, Any] = {
            "type":    "llamaindex_message",
            "key":     key,
            "role":    getattr(message, "role",    "user"),
            "content": getattr(message, "content", str(message)),
        }
        # Preserve additional_kwargs if present
        extra = getattr(message, "additional_kwargs", {})
        if extra:
            payload["additional_kwargs"] = extra

        await self.stream.append(payload, memory_type="working")

    async def get_messages(self, key: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for a conversation key, oldest first."""
        tl = await self.stream.timeline()
        return [
            payload
            for _, payload in tl
            if payload.get("type") == "llamaindex_message"
            and payload.get("key") == key
            and not payload.get("_deleted")
        ]

    async def delete_messages(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """
        Logically delete all messages for ``key`` via a tombstone event.

        Returns the messages that were deleted, or ``None`` if none found.
        """
        existing = await self.get_messages(key)
        if not existing:
            return None
        await self.stream.append(
            {"type": "llamaindex_delete", "key": key, "count": len(existing)},
            memory_type="system"
        )
        return existing

    async def delete_last_message(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Delete the most recent message for ``key``.

        Returns the deleted message, or ``None`` if the key is empty.
        """
        messages = await self.get_messages(key)
        if not messages:
            return None
        last = messages[-1]
        await self.stream.append(
            {"type": "llamaindex_delete_last", "key": key},
            memory_type="system"
        )
        return last

    async def get_keys(self) -> List[str]:
        """Return all distinct conversation keys in the store."""
        tl = await self.stream.timeline()
        return list({
            payload["key"]
            for _, payload in tl
            if payload.get("type") == "llamaindex_message" and "key" in payload
        })


class WalrusDocumentStore:
    """
    LlamaIndex ``BaseDocumentStore`` backed by a WalrusOS MemoryStream.

    Stores node metadata (text, embeddings, relationships) as append-only
    events.  Suitable for RAG pipelines that ingest documents incrementally.
    """

    def __init__(self, stream: StreamClient) -> None:
        self.stream       = stream

    async def add_document(
        self,
        doc_id:   str,
        text:     str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a document node to the store."""
        payload: Dict[str, Any] = {
            "type":     "llamaindex_document",
            "doc_id":   doc_id,
            "text":     text,
            "metadata": metadata or {},
        }
        await self.stream.append(payload, memory_type="working")
        # Index text for semantic retrieval
        await self.stream._memory.vector.upsert(doc_id, text, metadata or {})

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the latest version of a document, or None if deleted."""
        tl = await self.stream.timeline()
        result: Optional[Dict[str, Any]] = None
        for _, payload in tl:
            if payload.get("doc_id") != doc_id:
                continue
            if payload.get("type") == "llamaindex_document":
                result = payload
            elif payload.get("type") == "llamaindex_doc_deleted":
                result = None  # Tombstone — logical delete
        return result

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Semantic search across all indexed documents."""
        return await self.stream.search(query, limit=limit)

    async def list_document_ids(self) -> List[str]:
        """Return all distinct document IDs in the store."""
        tl = await self.stream.timeline()
        return list({
            payload["doc_id"]
            for _, payload in tl
            if payload.get("type") == "llamaindex_document" and "doc_id" in payload
        })

    async def delete_document(self, doc_id: str) -> bool:
        """
        Logically delete a document (tombstone event + vector removal).

        Returns ``True`` if the document existed, ``False`` otherwise.
        """
        existing = await self.get_document(doc_id)
        if existing is None:
            return False
        await self.stream.append(
            {"type": "llamaindex_doc_deleted", "doc_id": doc_id},
            memory_type="system"
        )
        if hasattr(self.stream._memory, "vector"):
            await self.stream._memory.vector.delete(doc_id)
        return True
