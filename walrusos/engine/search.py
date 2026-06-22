import json
from datetime import datetime
from typing import List, Optional, Tuple, Any, Dict
import uuid

from walrusos.core.models.memory import MemoryEvent
from walrusos.engine.memory import MemoryEngine

class MemorySearch:
    """
    Intelligent query layer for Memory Streams.
    
    Bypasses slow timeline reads by querying the underlying SQLite ledger directly
    if available. Otherwise falls back to Python-level filtering of the timeline.
    """
    
    def __init__(self, memory_engine: MemoryEngine, stream_id: uuid.UUID):
        self.engine = memory_engine
        self.stream_id = stream_id
        
    @property
    def _is_sqlite(self) -> bool:
        return hasattr(self.engine.ledger, "_engine")

    async def _fallback_timeline(self) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        return await self.engine.timeline(self.stream_id)

    async def search(self, query: str, limit: int = 10) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """
        Keyword/Semantic search across the stream.
        Delegates to the engine's vector store if available.
        """
        if hasattr(self.engine, "semantic_search"):
            # The MemoryEngine semantic_search method handles the vector store.
            # However, stream client expects List[Tuple[Dict, float]]. We return MemoryEvent tuples.
            # But wait, MemoryEngine semantic_search currently returns raw list of dictionaries.
            # Actually, the StreamClient in walrusos/sdk/stream.py already handles semantic_search via engine!
            # We will provide a unified interface here.
            raw_results = await self.engine.semantic_search(query, limit=limit) # type: ignore
            events_with_payload = []
            for item in raw_results:
                if isinstance(item, dict):
                    doc_id = item.get("doc_id", "")
                else:
                    doc_id = item[0] if isinstance(item, tuple) else ""
                    
                if doc_id:
                    try:
                        event = await self.engine.ledger.get_event(doc_id)
                        if event:
                            payload = await self.engine.read(doc_id)
                            events_with_payload.append((event, payload))
                    except Exception:
                        pass
            return events_with_payload[:limit]
        else:
            # Fallback to basic string containment
            timeline = await self._fallback_timeline()
            results = []
            q_lower = query.lower()
            for ev, payload in timeline:
                text = " ".join(str(v) for v in payload.values() if isinstance(v, (str, int, float))).lower()
                if q_lower in text:
                    results.append((ev, payload))
            return list(reversed(results))[:limit]

    async def latest(self, n: int = 10) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Get the n most recent events."""
        if self._is_sqlite:
            from sqlmodel import Session, select
            from walrusos.adapters.sqlite_ledger import MemoryEventRecord
            with Session(self.engine.ledger._engine) as session: # type: ignore
                records = session.exec(
                    select(MemoryEventRecord)
                    .where(MemoryEventRecord.stream_id == str(self.stream_id))
                    .order_by(MemoryEventRecord.epoch.desc()) # type: ignore
                    .limit(n)
                ).all()
                # Reverse to get chronological order of the latest n
                records = list(reversed(records))
                
                result = []
                for r in records:
                    ev = await self.engine.ledger.get_event(r.id)
                    if ev:
                        try:
                            payload = await self.engine.read(r.id)
                        except Exception:
                            payload = {}
                        result.append((ev, payload))
                return result
        else:
            tl = await self._fallback_timeline()
            return tl[-n:] if tl else []

    async def by_agent(self, agent_id: str, limit: int = 20) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Filter events by the authoring agent."""
        if self._is_sqlite:
            from sqlmodel import Session, select
            from walrusos.adapters.sqlite_ledger import MemoryEventRecord
            with Session(self.engine.ledger._engine) as session: # type: ignore
                records = session.exec(
                    select(MemoryEventRecord)
                    .where(MemoryEventRecord.stream_id == str(self.stream_id))
                    .where(MemoryEventRecord.agent_id == agent_id)
                    .order_by(MemoryEventRecord.epoch.desc()) # type: ignore
                    .limit(limit)
                ).all()
                records = list(reversed(records))
                result = []
                for r in records:
                    ev = await self.engine.ledger.get_event(r.id)
                    if ev:
                        payload = await self.engine.read(r.id)
                        result.append((ev, payload))
                return result
        else:
            tl = await self._fallback_timeline()
            results = [(ev, p) for ev, p in tl if getattr(ev, "agent_id", None) == agent_id]
            return results[-limit:]

    async def by_type(self, memory_type: str, limit: int = 20) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Filter events by memory_type."""
        if self._is_sqlite:
            from sqlmodel import Session, select
            from walrusos.adapters.sqlite_ledger import MemoryEventRecord
            with Session(self.engine.ledger._engine) as session: # type: ignore
                records = session.exec(
                    select(MemoryEventRecord)
                    .where(MemoryEventRecord.stream_id == str(self.stream_id))
                    .where(MemoryEventRecord.memory_type == memory_type)
                    .order_by(MemoryEventRecord.epoch.desc()) # type: ignore
                    .limit(limit)
                ).all()
                records = list(reversed(records))
                result = []
                for r in records:
                    ev = await self.engine.ledger.get_event(r.id)
                    if ev:
                        payload = await self.engine.read(r.id)
                        result.append((ev, payload))
                return result
        else:
            tl = await self._fallback_timeline()
            results = [(ev, p) for ev, p in tl if getattr(ev, "memory_type", None) == memory_type]
            return results[-limit:]

    async def by_tag(self, tag: str, limit: int = 20) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Filter events that contain the specified tag."""
        if self._is_sqlite:
            from sqlmodel import Session, select
            from walrusos.adapters.sqlite_ledger import MemoryEventRecord
            with Session(self.engine.ledger._engine) as session: # type: ignore
                # Simple LIKE search on the JSON array text
                records = session.exec(
                    select(MemoryEventRecord)
                    .where(MemoryEventRecord.stream_id == str(self.stream_id))
                    .where(MemoryEventRecord.tags.like(f'%"{tag}"%')) # type: ignore
                    .order_by(MemoryEventRecord.epoch.desc()) # type: ignore
                    .limit(limit)
                ).all()
                records = list(reversed(records))
                result = []
                for r in records:
                    ev = await self.engine.ledger.get_event(r.id)
                    if ev:
                        payload = await self.engine.read(r.id)
                        result.append((ev, payload))
                return result
        else:
            tl = await self._fallback_timeline()
            results = [(ev, p) for ev, p in tl if tag in getattr(ev, "tags", [])]
            return results[-limit:]

    async def timeline(self, start: datetime, end: datetime) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Get events between two timestamps."""
        # Using fallback for timeline timestamp filtering as we need payload access if timestamp isn't indexed
        tl = await self._fallback_timeline()
        result = []
        for ev, p in tl:
            # We don't have a reliable timestamp on MemoryEvent, usually it's in the payload or we map it
            # The prompt requested `timeline(start: datetime, end: datetime)`.
            # If we don't have timestamp indexed, we just return empty or use event metadata.
            # In live.py timestamp is tracked. But in the SDK, the closest is _meta or we use fallback.
            ts_str = p.get("timestamp") or getattr(ev, "created_at", None)
            if not ts_str:
                continue
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if start <= dt <= end:
                    result.append((ev, p))
            except Exception:
                pass
        return result

    async def related(self, event_id: str, limit: int = 5) -> List[Tuple[MemoryEvent, Dict[str, Any]]]:
        """Fetch nearby/related events. Basic implementation grabs latest if event_id is generic."""
        # A more sophisticated implementation would use cosine similarity on the embeddings.
        # For this phase, we map it to vector search if available.
        try:
            payload = await self.engine.read(event_id)
            text = " ".join(str(v) for v in payload.values() if isinstance(v, (str, int, float)))
            return await self.search(text, limit=limit)
        except Exception:
            return await self.latest(limit)
