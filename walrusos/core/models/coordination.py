"""
Coordination models — task graph for autonomous multi-agent coordination.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

TaskStatus = Literal["pending", "assigned", "in_progress", "done", "failed", "blocked"]


class CoordinationTask(BaseModel):
    task_id:              str        = Field(default_factory=lambda: str(uuid4()))
    goal_id:              str
    title:                str
    description:          str
    required_capability:  str
    status:               TaskStatus = "pending"
    assigned_to:          Optional[str] = None   # agent_id (_agent_id_str)
    assigned_to_name:     Optional[str] = None
    depends_on:           List[str]  = Field(default_factory=list)  # task_ids
    result_event_id:      Optional[str] = None
    result_content:       Optional[str] = None
    created_at:           datetime   = Field(default_factory=datetime.utcnow)
    completed_at:         Optional[datetime] = None


class CoordinationPlan(BaseModel):
    goal_id:    str       = Field(default_factory=lambda: str(uuid4()))
    goal:       str
    tasks:      List[CoordinationTask] = Field(default_factory=list)
    status:     Literal["planning", "executing", "completed", "failed"] = "planning"
    created_at: datetime  = Field(default_factory=datetime.utcnow)


class CoordinationResult(BaseModel):
    goal_id:          str
    goal:             str
    plan:             CoordinationPlan
    tasks_completed:  int
    tasks_failed:     int
    agents_used:      List[str]
    events:           List[Any]  = Field(default_factory=list)
    final_summary:    str
    duration_seconds: float
    blob_ids:         List[str]  = Field(default_factory=list)
    sui_anchors:      List[str]  = Field(default_factory=list)
    completed:        bool
