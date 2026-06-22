import uuid
from typing import Literal, Optional
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField

class Artifact(BaseModel):
    """
    Represents a heavy binary payload stored on Walrus.
    Immutable.
    """
    blob_id: str = Field(..., description="Walrus content-addressed hash")
    mime_type: str = Field(..., description="e.g., application/json or application/pdf")
    byte_size: int = Field(..., ge=0)
    compression: Literal["none", "zstd"] = "zstd"
    aes_key_id: Optional[uuid.UUID] = None
    lease_expiry_epoch: int = Field(..., ge=0)

class Embedding(SQLModel, table=True):
    """
    Represents a dense vector representation of an Artifact.
    Stored locally in pgvector.
    """
    id: uuid.UUID = SQLField(default_factory=uuid.uuid4, primary_key=True)
    source_artifact_id: str = SQLField(index=True)
    model: str = SQLField(default="text-embedding-3-small")
    # Note: In a real SQLModel/pgvector implementation, the vector column requires special SQLAlchemy types.
    # We use a JSON string mapping for generic compatibility in the pure domain layer.
    vector_json: str
