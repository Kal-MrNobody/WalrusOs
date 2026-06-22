from datetime import datetime
from typing import List, Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

class Task(BaseModel):
    """
    Represents a unit of work assigned to an agent or pending processing.
    Stored only in local SQLite cache, not anchored to Sui or Walrus.
    """
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str
    title: str
    description: str = ""
    created_by: str          # agent_id
    assigned_to: Optional[str] = None  # agent_id, None = unassigned
    status: Literal["pending", "in_progress", "review", "done", "failed"] = "pending"
    priority: int = 3        # 1 (highest) to 5 (lowest)
    parent_task_id: Optional[str] = None
    subtask_ids: List[str] = Field(default_factory=list)
    memory_refs: List[str] = Field(default_factory=list)    # event_ids related to this task
    artifact_refs: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    notes: str = ""
