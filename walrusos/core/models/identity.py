import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field
from pydantic import EmailStr, field_validator

def utcnow() -> datetime:
    """Returns the current UTC datetime."""
    return datetime.now(timezone.utc)

class User(SQLModel, table=True):
    """
    Represents a human operator interacting with WalrusOS.
    Stored locally in the Index DB.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sui_address: str = Field(index=True, max_length=66)
    email: Optional[EmailStr] = None
    created_at: datetime = Field(default_factory=utcnow)
    
    @field_validator("sui_address")
    @classmethod
    def validate_sui_address(cls, v: str) -> str:
        if not v.startswith("0x"):
            raise ValueError("sui_address must start with '0x'")
        return v

class Workspace(SQLModel, table=True):
    """
    Represents an isolated organizational boundary.
    Acts as the Gas Station for Walrus storage.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=100)
    retention_policy_epochs: int = Field(default=365, ge=1)
    treasury_balance: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=utcnow)

class Agent(SQLModel, table=True):
    """
    Represents the mutable configuration of an AI instance.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(index=True)
    name: str = Field(min_length=1, max_length=100)
    system_prompt: str
    status: str = Field(default="ACTIVE")
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"ACTIVE", "PAUSED", "DEPRECATED"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v
