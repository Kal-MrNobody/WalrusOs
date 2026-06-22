import uuid
from typing import Any, Dict, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField, JSON

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Task(SQLModel, table=True):
    """
    A pending background job for the internal Scheduler.
    Local ephemeral queue.
    """
    id: uuid.UUID = SQLField(default_factory=uuid.uuid4, primary_key=True)
    type: str = SQLField(index=True) # e.g., INDEX_ARTIFACT
    payload: Dict[str, Any] = SQLField(default_factory=dict, sa_type=JSON)
    retries: int = SQLField(default=0)
    created_at: datetime = SQLField(default_factory=utcnow)

class Execution(SQLModel, table=True):
    """
    The sandbox lifecycle of an external Agent Framework (e.g., LangGraph).
    """
    id: uuid.UUID = SQLField(default_factory=uuid.uuid4, primary_key=True)
    agent_id: uuid.UUID = SQLField(index=True)
    pid: int
    started_at: datetime = SQLField(default_factory=utcnow)

class Subscription(BaseModel):
    """
    An active WebSocket connection.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    filter_topics: List[str] = Field(default_factory=list)
    client_ip: str
    connected_at: datetime = Field(default_factory=utcnow)

class ValidationResult(BaseModel):
    """
    Output of the local Critic Model evaluating a memory event.
    """
    event_id: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    contradiction_detected: bool = False
    rationale: str
