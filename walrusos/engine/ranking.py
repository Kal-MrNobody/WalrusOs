"""
Relevance ranking for memory events.

Works with (MemoryEvent, payload_dict) tuples as returned by stream.timeline().
No external embedding API required — hybrid offline score with graceful degradation.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

_STOP = frozenset({
    "the", "a", "an", "is", "are", "of", "to", "in", "and", "or",
    "for", "on", "with", "how", "what", "do", "we",
})


def keyword_overlap_score(query: str, content: str) -> float:
    """0–1 score based on shared significant words."""
    def tokens(s: str) -> set:
        return {w for w in re.findall(r"[a-z0-9]+", s.lower())
                if w not in _STOP and len(w) > 2}

    q = tokens(query)
    c = tokens(content)
    if not q or not c:
        return 0.0
    return len(q & c) / len(q)


def rank_events(
    query: str,
    events: List[Tuple[Any, Dict[str, Any]]],
    *,
    recency_weight: float = 0.3,
    importance_weight: float = 0.2,
    relevance_weight: float = 0.5,
) -> List[Tuple[Any, Dict[str, Any]]]:
    """Return (event, payload) tuples sorted by combined score, highest first.

    Combines:
      relevance  — keyword overlap with query
      recency    — newer events score higher
      importance — the event's own importance field (0–1)

    Summary/decision events get a 1.2× boost (denser context per token).
    """
    if not events:
        return []

    now = time.time()

    def _to_ts(ev: Any) -> float:
        raw = getattr(ev, "timestamp", None)
        if not raw:
            return now
        try:
            if isinstance(raw, str):
                return datetime.fromisoformat(raw.replace("Z", "")).timestamp()
            if hasattr(raw, "timestamp"):
                return raw.timestamp()
        except Exception:
            pass
        return now

    timestamps = [_to_ts(ev) for ev, _ in events]
    oldest = min(timestamps)
    newest = max(timestamps)
    span = max(newest - oldest, 1)

    scored = []
    for pair, ts in zip(events, timestamps):
        ev, payload = pair
        # Content: string values only (excludes numeric metadata like importance)
        from walrusos.sdk.stream import _strip_internal
        stripped = _strip_internal(payload)
        content = " ".join(
            v for v in stripped.values()
            if isinstance(v, str) and v
        )

        relevance = keyword_overlap_score(query, content)
        recency = (ts - oldest) / span
        importance = float(getattr(ev, "importance", 0.5) or 0.5)

        mem_type = getattr(ev, "memory_type", "observation") or "observation"
        type_boost = 1.2 if mem_type in ("summary", "decision") else 1.0

        score = (
            relevance_weight * relevance
            + recency_weight * recency
            + importance_weight * importance
        ) * type_boost

        # Preserve the original pair reference so callers can use `is` identity checks
        scored.append((score, pair))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [pair for _, pair in scored]
