"""
RunResult — the return value of WorkspaceClient.run().
"""
from __future__ import annotations

from typing import Any, List
from pydantic import BaseModel, Field


class RunResult(BaseModel):
    """Outcome of an autonomous multi-agent run."""

    goal:              str
    rounds_completed:  int
    events:            List[Any]   # List[MemoryEvent] — Any avoids circular import
    agents_involved:   List[str]
    final_summary:     str
    completed:         bool        # True = agent signalled DONE; False = max_rounds hit
    duration_seconds:  float
    blob_ids:          List[str]
    sui_anchors:       List[str]
