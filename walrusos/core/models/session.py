"""
Agent Session Protocol — domain model for real-time presence.

AgentSession tracks what an agent is doing right now.
SessionActivity is a single log entry inside that session.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

# ── Type aliases ──────────────────────────────────────────────────────────────

SessionStatus = Literal[
    "online", "thinking", "working", "idle", "waiting", "offline"
]

SessionAction = Literal[
    "read_memory", "write_memory", "search_memory",
    "open_file", "create_task", "claim_task", "complete_task",
    "publish_artifact", "send_message", "run_started", "run_complete",
]

# ── Models ────────────────────────────────────────────────────────────────────

class SessionActivity(BaseModel):
    timestamp: datetime    = Field(default_factory=datetime.utcnow)
    action:    SessionAction
    detail:    str                   # human readable: "Read 7 memories about OAuth"
    metadata:  dict        = Field(default_factory=dict)


class AgentSession(BaseModel):
    session_id:  str      = Field(default_factory=lambda: str(uuid4()))
    agent_id:    str
    agent_name:  str
    workspace_id: str
    framework:   str      = "custom"

    # Lifecycle
    started_at:      datetime       = Field(default_factory=datetime.utcnow)
    ended_at:        Optional[datetime] = None
    last_heartbeat:  datetime       = Field(default_factory=datetime.utcnow)

    # Current state
    status:               SessionStatus   = "online"
    current_task_id:      Optional[str]   = None
    current_task_label:   Optional[str]   = None
    current_file:         Optional[str]   = None
    current_memory_query: Optional[str]   = None

    # Session counters
    memory_reads:        int = 0
    memory_writes:       int = 0
    artifacts_published: int = 0
    tasks_completed:     int = 0

    # Activity log — last 20 only
    activity_log: list[SessionActivity] = Field(default_factory=list)

    def log(self, action: SessionAction, detail: str, **metadata) -> None:
        entry = SessionActivity(action=action, detail=detail, metadata=metadata)
        self.activity_log.append(entry)
        if len(self.activity_log) > 20:
            self.activity_log = self.activity_log[-20:]
        self.last_heartbeat = datetime.utcnow()

    @property
    def last_seen_seconds(self) -> int:
        delta = datetime.utcnow() - self.last_heartbeat
        return int(delta.total_seconds())

    @property
    def is_stale(self) -> bool:
        return self.last_seen_seconds > 30
