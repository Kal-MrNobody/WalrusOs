import uuid
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField

class MemoryStream(SQLModel, table=True):
    """
    Tracks an active memory DAG on Sui. 
    Stored locally for fast querying.
    """
    id: uuid.UUID = SQLField(default_factory=uuid.uuid4, primary_key=True)
    agent_id: uuid.UUID = SQLField(index=True)
    head_event_id: str = SQLField(index=True) # Sui Tx Hash pointer

class MemoryEvent(BaseModel):
    """
    Represents an immutable, mathematical pointer in the Sui DAG.
    This does NOT persist to the local SQL database, it maps to on-chain state.
    """
    id: str = Field(..., description="The Sui Transaction Hash")
    stream_id: uuid.UUID
    parent_id: str = Field(..., description="Chronological DAG pointer")
    epoch: int = Field(..., ge=0)
    memory_type: Literal[
        "semantic",
        "episodic",
        "procedural",
        "working",
        "system",
        "langgraph",
        "langgraph_write",
        "observation",
        "summary"
    ] = "observation"
    tags: List[str] = Field(default_factory=list)
    importance: float = 0.5
    summary: Optional[str] = None
    embedding: Optional[List[float]] = None
    project: Optional[str] = None
    
    content_blob_id: str = Field(..., description="Walrus content-addressed hash")
    attributions: List[str] = Field(default_factory=list)
    # Phase 2: persistent AgentIdentity reference (nullable for backward compat)
    agent_id: Optional[str] = Field(
        default=None,
        description="AgentIdentity.agent_id — the persistent UUID of the authoring agent",
    )
    # Phase 3: Cryptographic verification fields
    event_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of the canonical JSON payload",
    )
    signature: Optional[str] = Field(
        default=None,
        description="Base64 encoded Ed25519 signature of the event hash",
    )
    public_key: Optional[str] = Field(
        default=None,
        description="Hex encoded Ed25519 public key of the authoring agent",
    )

    # ── SDK duck-typing aliases ────────────────────────────────────────────────

    @property
    def event_id(self) -> str:
        """Alias for :attr:`id` — canonical event identifier used by StreamClient."""
        return self.id

    @property
    def timestamp(self) -> str:
        """Synthetic ISO-8601 timestamp based on epoch."""
        from datetime import datetime, timezone
        # epoch is a sequence number, not a Unix timestamp; return current time as fallback
        return datetime.now(timezone.utc).isoformat()


class Checkpoint(BaseModel):
    """
    A compressed snapshot of an agent's memory window to speed up resumption.
    """
    stream_id: uuid.UUID
    epoch: int = Field(..., ge=0)
    consolidated_blob_id: str = Field(..., description="Walrus hash of the summarized memory")
