from typing import Dict, Optional, Any
from walrusos.core.models.events import ProtocolEvent, EventType
from walrusos.core.models.agent_identity import AgentIdentity, AgentStatus

class ProjectionEngine:
    """
    Reduces ProtocolEvents into concrete state models (Projections).
    """

    @staticmethod
    def apply_agent_event(state: Optional[AgentIdentity], event: ProtocolEvent) -> AgentIdentity:
        """
        Fold an event into an AgentIdentity projection.
        """
        if event.event_type == EventType.AgentRegistered:
            if state is not None:
                raise ValueError(f"Agent already registered: {event.agent_id}")
            agent = AgentIdentity(
                agent_id=event.agent_id or "",
                workspace_id=event.workspace_id,
                agent_name=event.payload.get("agent_name", ""),
                owner_wallet=event.wallet,
                public_key=event.payload.get("public_key", ""),
                trust_root=event.payload.get("trust_root", ""),
                metadata=event.payload.get("metadata", {}),
                status=AgentStatus.ACTIVE,
                created_at=event.timestamp,
            )
            return agent
        
        if state is None:
            raise ValueError(f"Cannot apply {event.event_type} to missing agent state.")

        if event.event_type == EventType.AgentPaused:
            state.status = AgentStatus.PAUSED
        elif event.event_type == EventType.AgentResumed:
            state.status = AgentStatus.ACTIVE
        elif event.event_type == EventType.AgentTerminated:
            state.status = AgentStatus.TERMINATED
        elif event.event_type == EventType.MemoryAppended:
            state.memory_counter += 1
            state.execution_counter += 1
            state.reputation.memory_writes += 1
            state.reputation.successful_signatures += 1 # A successful append implies a successful signature
        elif event.event_type == EventType.ArtifactUploaded:
            state.artifact_counter += 1
            state.reputation.artifact_uploads += 1
            state.reputation.successful_signatures += 1
        elif event.event_type == EventType.ValidationPassed:
            state.reputation.validation_approvals += 1
        elif event.event_type == EventType.ValidationFailed:
            state.reputation.validation_failures += 1
            # Note: We consider this a logical validation failure, or a tracked bad signature
            if event.payload.get("reason") == "bad_signature":
                state.reputation.failed_verifications += 1
        elif event.event_type == EventType.CapabilityGranted:
            cap = event.payload.get("capability")
            if cap and cap not in state.capabilities:
                state.capabilities.append(cap)
                state.reputation.capability_grants += 1
        elif event.event_type == EventType.CapabilityRevoked:
            cap = event.payload.get("capability")
            if cap and cap in state.capabilities:
                state.capabilities.remove(cap)
                state.reputation.capability_revocations += 1

        # Deterministically roll the trust root forward with the event ID
        state.roll_trust_root(event.event_id)

        return state

    @staticmethod
    def apply_workspace_event(state: Optional[Dict[str, Any]], event: ProtocolEvent) -> Dict[str, Any]:
        """
        Fold an event into a Workspace projection.
        """
        if event.event_type == EventType.WorkspaceCreated:
            if state is not None:
                raise ValueError(f"Workspace already exists: {event.workspace_id}")
            return {
                "workspace_id": event.workspace_id,
                "name": event.payload.get("name", ""),
                "owner_wallet": event.wallet,
                "created_at": event.timestamp,
                "status": "active"
            }
        
        if state is None:
            raise ValueError(f"Cannot apply {event.event_type} to missing workspace state.")

        if event.event_type == EventType.WorkspaceDeleted:
            state["status"] = "deleted"

        return state
