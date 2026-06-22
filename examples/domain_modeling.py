from walrusos.core.models import Workspace, Agent, MemoryEvent
import json

def main():
    print("--- WalrusOS Domain Modeling Example ---")
    
    # 1. Instantiate a SQLModel (Local Index)
    workspace = Workspace(name="ResearchOrg", treasury_balance=100.50)
    print(f"Created Workspace ID: {workspace.id}")
    
    # 2. Instantiate an Agent
    agent = Agent(
        workspace_id=workspace.id,
        name="Data Scientist",
        system_prompt="You analyze datasets."
    )
    print(f"Created Agent ID: {agent.id} (Status: {agent.status})")
    
    # 3. Instantiate an Immutable Pydantic Model (Sui Event Mapping)
    event = MemoryEvent(
        id="0x_tx_hash_123",
        stream_id=agent.id, # In reality, points to a Stream ID
        parent_id="0x_parent_hash",
        epoch=50,
        memory_type="working",
        content_blob_id="blob_xyz_789"
    )
    
    # 4. JSON Serialization
    print("\nSerialized MemoryEvent:")
    print(event.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
