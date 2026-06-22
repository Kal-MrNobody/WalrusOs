import uuid
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class Permission(str, Enum):
    """Human readable permissions mapping to the bitmask."""
    READ = "READ"
    APPEND = "APPEND"
    REVOKE = "REVOKE"
    FORK = "FORK"
    MERGE = "MERGE"

class Capability(BaseModel):
    """
    Represents an Address-Owned Object capability on the Sui Blockchain.
    """
    id: str = Field(..., description="Sui Object ID")
    owner_address: str = Field(..., max_length=66)
    target_stream_id: uuid.UUID
    verb_bitmask: int = Field(..., ge=0, description="Binary permissions mask")
    valid_until_epoch: int = Field(..., ge=0)
    parent_cap_id: Optional[str] = None

    @field_validator("owner_address")
    @classmethod
    def validate_sui_address(cls, v: str) -> str:
        if not v.startswith("0x"):
            raise ValueError("owner_address must start with '0x'")
        return v
