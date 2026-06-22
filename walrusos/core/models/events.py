"""
WalrusOS Protocol Event model.

``ProtocolEvent`` is the immutable record returned by every write operation.
"""
import uuid
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    WorkspaceCreated  = "WorkspaceCreated"
    WorkspaceDeleted  = "WorkspaceDeleted"
    AgentRegistered   = "AgentRegistered"
    AgentPaused       = "AgentPaused"
    AgentResumed      = "AgentResumed"
    AgentTerminated   = "AgentTerminated"
    CapabilityGranted = "CapabilityGranted"
    CapabilityRevoked = "CapabilityRevoked"
    MemoryAppended    = "MemoryAppended"
    MemoryForked      = "MemoryForked"
    MemoryMerged      = "MemoryMerged"
    ArtifactUploaded  = "ArtifactUploaded"
    ArtifactDeleted   = "ArtifactDeleted"
    ValidationPassed  = "ValidationPassed"
    ValidationFailed  = "ValidationFailed"
    RecoveryStarted   = "RecoveryStarted"
    RecoveryFinished  = "RecoveryFinished"
    ReplayStarted     = "ReplayStarted"
    ReplayFinished    = "ReplayFinished"


class ProtocolEvent(BaseModel):
    """
    Immutable record of any state change in WalrusOS.

    Returned by :meth:`~walrusos.sdk.stream.StreamClient.append` and
    every other write operation.

    Key fields:

    ``event_id``
        SHA-256 content hash of the signed payload.  Use this as a stable
        reference to a specific event.

    ``timestamp``
        ISO-8601 UTC timestamp when the event was created locally.

    ``blob_hash``
        Hash of the Walrus blob (``None`` if using mocks).

    ``signature``
        Ed25519 signature of the canonical payload.

    ``parent_event``
        ``event_id`` of the previous event in this stream.

    Example::

        event = await stream.append({"thought": "..."})
        print(event.event_id)      # SHA-256 hash
        print(event.timestamp)     # "2026-06-17T05:00:00.123456+00:00"
        print(event.parent_event)  # previous event's event_id
    """

    event_id:           str = Field(..., description="SHA-256 content hash of the event payload")
    event_type:         EventType
    workspace_id:       str
    agent_id:           Optional[str] = None
    wallet:             str
    blob_id:            Optional[str] = None
    blob_hash:          Optional[str] = None
    parent_event:       Optional[str] = None
    previous_hash:      Optional[str] = None
    signature:          str = ""
    timestamp:          str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    transaction_digest: Optional[str] = None
    payload:            Dict[str, Any] = Field(default_factory=dict)

    # ── Aliases ───────────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Alias for :attr:`event_id` — both are equivalent."""
        return self.event_id

    @property
    def parent_id(self) -> Optional[str]:
        """Alias for :attr:`parent_event` for compatibility with merge tests."""
        return self.parent_event

    @property
    def content_blob_id(self) -> Optional[str]:
        """Alias for :attr:`blob_id` for compatibility with MemoryEvent."""
        return self.blob_id

    @property
    def event_hash(self) -> str:
        """Alias for :attr:`event_id` for compatibility with verification tests."""
        return self.event_id

    @property
    def public_key(self) -> Optional[str]:
        """Return the public key of the signing agent from the payload envelope."""
        return self.payload.get("public_key")
