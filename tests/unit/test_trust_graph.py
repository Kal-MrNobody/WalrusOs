import pytest
from walrusos.core.models.agent_identity import AgentIdentity, AgentStatus
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.core.projections.engine import ProjectionEngine

def test_agent_trust_root_accumulator():
    # 1. Create Identity
    agent = AgentIdentity.create(
        workspace_name="test_ws",
        agent_name="test_agent",
        owner_wallet="0x123",
        public_key_hex="abcdef"
    )
    
    initial_trust_root = agent.trust_root
    
    # 2. Apply MemoryAppended (Valid Signature)
    event1 = ProtocolEvent(
        event_id="hash_event_1",
        event_type=EventType.MemoryAppended,
        workspace_id=agent.workspace_id,
        agent_id=agent.agent_id,
        wallet=agent.owner_wallet,
        payload={"message": "hello"},
        signature="sig"
    )
    
    agent = ProjectionEngine.apply_agent_event(agent, event1)
    
    # Assert reputation counters
    assert agent.reputation.memory_writes == 1
    assert agent.reputation.successful_signatures == 1
    
    # Assert TrustRoot rolled forward
    assert agent.trust_root != initial_trust_root
    rolled_trust_root_1 = agent.trust_root
    
    # 3. Apply ValidationFailed (Bad Signature caught by ReplayEngine)
    event2 = ProtocolEvent(
        event_id="hash_event_2",
        event_type=EventType.ValidationFailed,
        workspace_id=agent.workspace_id,
        agent_id=agent.agent_id,
        wallet=agent.owner_wallet,
        payload={"reason": "bad_signature"},
        signature=""
    )
    
    agent = ProjectionEngine.apply_agent_event(agent, event2)
    
    assert agent.reputation.validation_failures == 1
    assert agent.reputation.failed_verifications == 1
    assert agent.trust_root != rolled_trust_root_1
