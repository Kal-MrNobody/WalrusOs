from datetime import datetime, timezone
from typing import Optional

from walrusos.core.models.task import Task

class TaskClient:
    """SDK for managing an individual Task."""
    def __init__(self, task: Task, ledger: "LedgerAdapter"):
        self.task = task
        self.ledger = ledger
        
    def assign(self, agent: "AgentClient") -> "TaskClient":
        self.task.assigned_to = agent._agent_id_str
        self.task.updated_at = datetime.now(timezone.utc)
        self.ledger.save_task(self.task)
        return self

    def start(self) -> "TaskClient":
        if self.task.status == "pending":
            self.task.status = "in_progress"
            self.task.updated_at = datetime.now(timezone.utc)
            self.ledger.save_task(self.task)
        return self

    def submit_for_review(self) -> "TaskClient":
        if self.task.status == "in_progress":
            self.task.status = "review"
            self.task.updated_at = datetime.now(timezone.utc)
            self.ledger.save_task(self.task)
        return self

    def complete(self, notes: str = "") -> "TaskClient":
        self.task.status = "done"
        if notes:
            self.task.notes = notes
        now = datetime.now(timezone.utc)
        self.task.updated_at = now
        self.task.completed_at = now
        self.ledger.save_task(self.task)
        return self

    def fail(self, reason: str) -> "TaskClient":
        self.task.status = "failed"
        self.task.notes = reason
        self.task.updated_at = datetime.now(timezone.utc)
        self.ledger.save_task(self.task)
        return self

    def add_memory(self, event_id: str) -> "TaskClient":
        if event_id not in self.task.memory_refs:
            self.task.memory_refs.append(event_id)
            self.task.updated_at = datetime.now(timezone.utc)
            self.ledger.save_task(self.task)
        return self

    def add_subtask(self, title: str, assigned_to: Optional[str] = None) -> "TaskClient":
        from walrusos.core.models.task import Task
        subtask = Task(
            workspace_id=self.task.workspace_id,
            title=title,
            created_by=self.task.created_by,
            assigned_to=assigned_to,
            parent_task_id=self.task.task_id,
        )
        self.ledger.save_task(subtask)
        self.task.subtask_ids.append(subtask.task_id)
        self.task.updated_at = datetime.now(timezone.utc)
        self.ledger.save_task(self.task)
        return TaskClient(subtask, self.ledger)

    def add_tag(self, tag: str) -> "TaskClient":
        if tag not in self.task.tags:
            self.task.tags.append(tag)
            self.task.updated_at = datetime.now(timezone.utc)
            self.ledger.save_task(self.task)
        return self
