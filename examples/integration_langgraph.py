import asyncio
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END # type: ignore
from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver

# Define LangGraph State
class AgentState(TypedDict):
    messages: Annotated[list, operator.add]

async def mock_agent_node(state: AgentState):
    print(f"[Agent Node] Received messages: {state['messages']}")
    return {"messages": ["Hello from LangGraph executing on WalrusOS Memory!"]}

async def main():
    print("--- WalrusOS: LangGraph Integration Example ---")
    
    # 1. Initialize WalrusOS
    runtime = WalrusOS()  # Production: reads ~/.walrusos/config.json
# Dev/offline: WALRUSOS_USE_MOCKS=1 python integration_langgraph.py
    stream = runtime.workspace("langgraph_demo").stream("session_1")
    
    # 2. Inject Stream into LangGraph Checkpointer
    saver = AsyncWalrusSaver(stream)
    
    # 3. Build Graph
    graph = StateGraph(AgentState)
    graph.add_node("agent", mock_agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    
    # 4. Compile with WalrusOS Memory
    app = graph.compile(checkpointer=saver)
    
    # 5. Execute Graph asynchronously
    config = {"configurable": {"thread_id": "thread-1"}}
    inputs = {"messages": ["Start the graph"]}
    
    print("\nExecuting graph (First Run)...")
    async for event in app.astream(inputs, config=config):
        for k, v in event.items():
            print(f"Step output: {k}")
            
    # 6. Retrieve state directly from Walrus DAG
    print("\nRetrieving state directly from Walrus StreamClient...")
    timeline = await stream.timeline()
    for _, payload in timeline:
        print(f"Saved Checkpoint ID: {payload['checkpoint_id']}")

if __name__ == "__main__":
    asyncio.run(main())
