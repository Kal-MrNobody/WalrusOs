from typing import Any, Dict, List, Tuple
from walrusos.core.models.memory import MemoryEvent

class ContextBuilder:
    """
    Builds LLM-ready context strings from an agent's memory streams.
    """
    
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimation: 1 token ≈ 4 characters."""
        return len(text) // 4

    @staticmethod
    def _format_event(event: MemoryEvent, payload: Dict[str, Any]) -> str:
        """Format a single event into a readable string."""
        # Clean payload of internal meta fields if any exist
        clean_payload = {k: v for k, v in payload.items() if not k.startswith("_")}
        
        # Use a readable timestamp or epoch
        ts = payload.get("timestamp") or getattr(event, "created_at", f"Epoch {getattr(event, 'epoch', 0)}")
        author = payload.get("author") or getattr(event, "agent_id", "Unknown")
        
        # Build text representation of payload
        content = " | ".join(f"{k}: {v}" for k, v in clean_payload.items() if k not in ["timestamp", "author", "agent_id", "class_type", "memory_type", "stream_id"])
        
        return f"[{ts}] {author}: {content}"

    async def build_context(self, stream, query: str, max_tokens: int = 2000, strategy: str = "smart") -> str:
        """
        Build a formatted context string.
        Strategies:
        - "latest": Returns the most recent events that fit in max_tokens.
        - "search": Returns search results for the query that fit in max_tokens.
        - "smart": Returns the latest summary checkpoint + recent events + relevant search results.
        """
        context_blocks = []
        current_tokens = 0
        
        if strategy == "latest":
            # Just grab recent events until we hit token limit
            # We fetch a decent chunk and trim
            events = await stream.latest(50)
            
            for ev, p in events:
                formatted = self._format_event(ev, p)
                tokens = self._estimate_tokens(formatted)
                if current_tokens + tokens > max_tokens:
                    break
                context_blocks.append(formatted)
                current_tokens += tokens
                
            # Reverse back to chronological order for the prompt
            context_blocks.reverse()
            
        elif strategy == "search":
            events = await stream.search(query, limit=20)
            for p, score in events:
                # search returns tuple of (payload, score) instead of (event, payload)
                # But wait, we modified MemorySearch.search to return (MemoryEvent, Dict)
                # And StreamClient.search strips to (Dict, float)
                # So here `events` is from `stream.search`, which returns `(Dict, float)`
                # Let's handle the payload directly.
                clean_payload = {k: v for k, v in p.items() if not k.startswith("_")}
                content = " | ".join(f"{k}: {v}" for k, v in clean_payload.items())
                formatted = f"[Search Match | Score: {score:.2f}] {content}"
                tokens = self._estimate_tokens(formatted)
                if current_tokens + tokens > max_tokens:
                    break
                context_blocks.append(formatted)
                current_tokens += tokens
                
        elif strategy == "smart":
            # 1. Fetch latest summary checkpoint
            timeline = await stream.timeline()
            checkpoint_text = ""
            recent_events = []
            
            for ev, p in reversed(timeline):
                if getattr(ev, "memory_type", None) == "summary" and "checkpoint" in getattr(ev, "tags", []):
                    checkpoint_text = p.get("checkpoint_summary", "")
                    break
                recent_events.append((ev, p))
            
            if checkpoint_text:
                formatted_checkpoint = f"--- PREVIOUS CHECKPOINT ---\n{checkpoint_text}\n---------------------------"
                tokens = self._estimate_tokens(formatted_checkpoint)
                if current_tokens + tokens <= max_tokens:
                    context_blocks.append(formatted_checkpoint)
                    current_tokens += tokens
            
            # 2. Add recent raw events
            recent_blocks = []
            recent_events.reverse() # Chronological
            for ev, p in recent_events[-10:]: # Arbitrary limit of recent events
                formatted = self._format_event(ev, p)
                tokens = self._estimate_tokens(formatted)
                if current_tokens + tokens > max_tokens:
                    break
                recent_blocks.append(formatted)
                current_tokens += tokens
                
            context_blocks.extend(recent_blocks)
            
            # 3. Pad with search results
            if current_tokens < max_tokens:
                search_results = await stream.search(query, limit=5)
                search_blocks = []
                for p, score in search_results:
                    clean_payload = {k: v for k, v in p.items() if not k.startswith("_")}
                    content = " | ".join(f"{k}: {v}" for k, v in clean_payload.items())
                    formatted = f"[Search Match] {content}"
                    tokens = self._estimate_tokens(formatted)
                    if current_tokens + tokens > max_tokens:
                        break
                    search_blocks.append(formatted)
                    current_tokens += tokens
                
                if search_blocks:
                    context_blocks.append("--- RELEVANT PAST EVENTS ---")
                    context_blocks.extend(search_blocks)
        
        else:
            raise ValueError(f"Unknown context strategy: {strategy}")

        return "\n".join(context_blocks)

    # ── Recall (Sprint 6) ─────────────────────────────────────────────────────

    async def _get_all_events(self, stream) -> List[Tuple]:
        """Fetch all (event, payload) tuples from stream, with full metadata."""
        return await stream.timeline(include_metadata=True)

    async def build_recall_context(
        self,
        stream,
        query: str,
        max_tokens: int = 1500,
        include_checkpoints: bool = True,
    ) -> Dict[str, Any]:
        """Assemble the most relevant context for a query within a token budget.

        Assembly order (each respects the token budget):
          1. Most recent checkpoint summary (if any) — the big picture
          2. Top-ranked relevant events by keyword overlap + recency + importance
          3. The 2 most recent non-summary events — current state guarantee

        Returns
        -------
        dict with keys:
            context              — assembled text, ready for an LLM prompt
            token_estimate       — approximate tokens used
            events_considered    — total events in the stream
            events_included      — number of events that made it into context
            checkpoints_included — number of checkpoint summaries included
            sources              — list of event_ids included (for provenance)
        """
        from walrusos.engine.token_budget import TokenBudget
        from walrusos.engine.ranking import rank_events
        from walrusos.sdk.stream import _strip_internal

        budget = TokenBudget(max_tokens)
        parts: List[str] = []
        sources: List[str] = []
        checkpoints_included = 0

        all_events = await self._get_all_events(stream)
        considered = len(all_events)

        # 1. Latest checkpoint summary first (most compressed big-picture)
        if include_checkpoints:
            checkpoints = [
                (ev, p) for ev, p in all_events
                if getattr(ev, "memory_type", "") == "summary"
                and "checkpoint" in getattr(ev, "tags", [])
            ]
            if checkpoints:
                latest_cp_ev, latest_cp_p = max(
                    checkpoints,
                    key=lambda pair: getattr(pair[0], "epoch", 0),
                )
                summary_text = latest_cp_p.get("checkpoint_summary", "")
                if summary_text:
                    cp_text = f"[Summary] {summary_text}"
                    if budget.add(cp_text):
                        parts.append(cp_text)
                        sources.append(getattr(latest_cp_ev, "event_id", ""))
                        checkpoints_included = 1

        # 2. Top relevant non-summary events
        non_summary = [
            (ev, p) for ev, p in all_events
            if getattr(ev, "memory_type", "") != "summary"
        ]
        ranked = rank_events(query, non_summary)

        included = 0
        for ev, payload in ranked:
            eid = getattr(ev, "event_id", "") or getattr(ev, "id", "")
            if eid in sources:
                continue
            agent = payload.get("author") or (getattr(ev, "agent_id", "") or "")[:8] or "agent"
            stripped = _strip_internal(payload)
            content = " ".join(
                v for v in stripped.values()
                if isinstance(v, str) and v
            )
            if not content:
                continue
            line = f"[{agent}] {content}"
            if budget.add(line):
                parts.append(line)
                sources.append(eid)
                included += 1
            else:
                break

        # 3. Guarantee the 2 most recent events are present (current state)
        recent = sorted(
            non_summary,
            key=lambda pair: getattr(pair[0], "epoch", 0),
            reverse=True,
        )[:2]
        for ev, payload in recent:
            eid = getattr(ev, "event_id", "") or getattr(ev, "id", "")
            if eid in sources:
                continue
            agent = payload.get("author") or (getattr(ev, "agent_id", "") or "")[:8] or "agent"
            stripped = _strip_internal(payload)
            content = " ".join(
                v for v in stripped.values()
                if isinstance(v, str) and v
            )
            if not content:
                continue
            line = f"[recent] [{agent}] {content}"
            if budget.add(line):
                parts.append(line)
                sources.append(eid)
                included += 1

        context = "\n\n".join(parts)
        return {
            "context": context,
            "token_estimate": budget.used,
            "events_considered": considered,
            "events_included": included,
            "checkpoints_included": checkpoints_included,
            "sources": sources,
        }
