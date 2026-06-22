"""
Tests for domain models using plain Pydantic BaseModel validation.
SQLModel table=True models need the engine to enforce DB constraints,
so we test the validators directly via model_validate.
"""
import uuid
import pytest
from pydantic import ValidationError

from walrusos.core.models import Capability, Artifact


def test_user_sui_address_validator():
    """User.sui_address must start with '0x'."""
    from walrusos.core.models.identity import User
    # Valid
    u = User.model_validate({"sui_address": "0x" + "a" * 64})
    assert u.sui_address.startswith("0x")
    # Invalid — SQLModel validates on model_validate
    with pytest.raises((ValidationError, ValueError)):
        User.model_validate({"sui_address": "not-starting-with-0x"})


def test_agent_status_validator():
    """Agent.status must be ACTIVE | PAUSED | DEPRECATED."""
    from walrusos.core.models.identity import Agent
    workspace_id = uuid.uuid4()
    a = Agent.model_validate({
        "workspace_id": str(workspace_id),
        "name": "Test",
        "system_prompt": "You are helpful.",
    })
    assert a.status == "ACTIVE"

    with pytest.raises((ValidationError, ValueError)):
        Agent.model_validate({
            "workspace_id": str(workspace_id),
            "name": "Test",
            "system_prompt": "x",
            "status": "INVALID_STATUS",
        })


def test_capability_serialization():
    """Capability serialises to JSON correctly."""
    cap = Capability(
        id="0x999",
        owner_address="0xabc",
        target_stream_id="11111111-1111-1111-1111-111111111111",
        verb_bitmask=15,
        valid_until_epoch=999,
    )
    json_data = cap.model_dump_json()
    assert "0x999" in json_data
    assert "0xabc" in json_data


def test_artifact_fields():
    """Artifact validates stream_id and blob_id."""
    art = Artifact(
        stream_id="22222222-2222-2222-2222-222222222222",
        blob_id="blob-abc123",
        mime_type="application/json",
        byte_size=1024,
        lease_expiry_epoch=999,
        name="data.json",
    )
    assert art.blob_id == "blob-abc123"
    assert art.byte_size == 1024
