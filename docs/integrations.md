# Framework Integrations

WalrusOS replaces the memory and checkpointing layer in every major AI framework. You keep your existing code; WalrusOS handles the rest.

---

## Overview

| Framework | What WalrusOS replaces | Lines of code |
|-----------|----------------------|---------------|
| [LangGraph](#langgraph) | `MemorySaver`, `SqliteSaver`, `PostgresSaver` | 3 |
| [CrewAI](#crewai) | `memory=True` embedder | 2 |
| [OpenAI Agents SDK](#openai-agents-sdk) | `ConversationStore` | 2 |
| [AutoGen](#autogen) | Message history | 3 |
| [LlamaIndex](#llamaindex) | `ChatMemoryBuffer` | 3 |
| [PydanticAI](#pydantic-ai) | Custom memory tools | 4 |

---

## LangGraph

WalrusOS provides `AsyncWalrusSaver`, a drop-in replacement for LangGraph's `MemorySaver`.

**Install:**

```bash
pip install walrusos langgraph
```

**Use:**

```python
from langgraph.graph import StateGraph, START, END
from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver

# Set up WalrusOS
runtime = WalrusOS()
memory  = AsyncWalrusSaver(runtime.workspace("my-app").stream("checkpoints"))

# Build your graph exactly as before
builder = StateGraph(YourState)
builder.add_node("agent", agent_node)
builder.add_edge(START, "agent")
builder.add_edge("agent", END)

# The only change: swap the checkpointer
app = builder.compile(checkpointer=memory)   # ← this line
```

**What changes:**

- Graph checkpoints are written to Walrus instead of local SQLite/Postgres
- Checkpoints survive process crashes, machine restarts, and deployments
- Every checkpoint is cryptographically signed and replay-able
- Multiple graph instances can share a stream (useful for distributed agents)

**Read checkpoints directly:**

```python
# Inspect your graph's memory without running the graph
timeline = await runtime.workspace("my-app").stream("checkpoints").timeline()
for event, payload in timeline:
    print(f"Checkpoint {payload['checkpoint_id']} at {event.timestamp}")
```

**Full example:**

```python
import asyncio
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END
from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]

async def agent_node(state: AgentState):
    # Your agent logic here
    return {"messages": ["I processed your request."]}

async def main():
    runtime = WalrusOS(use_mocks=True)    # remove use_mocks for production
    memory  = AsyncWalrusSaver(runtime.workspace("app").stream("session-1"))

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    app = graph.compile(checkpointer=memory)

    config = {"configurable": {"thread_id": "thread-1"}}
    result = await app.ainvoke({"messages": ["Hello"]}, config=config)
    print(result)

    # Crash and restart — the state is recovered automatically on next invoke

asyncio.run(main())
```

---

## CrewAI

WalrusOS provides `WalrusMemory`, which implements CrewAI's embedder interface.

**Install:**

```bash
pip install walrusos crewai
```

**Use:**

```python
from crewai import Crew, Agent, Task
from walrusos import WalrusOS
from walrusos.integrations.crewai import WalrusMemory

runtime = WalrusOS()
memory  = WalrusMemory(runtime.workspace("crew").stream("episodes"))

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    memory=True,
    embedder=memory,     # ← this line
)
```

**Save and search manually:**

```python
await memory.save({
    "task":   "Research quantum computing",
    "output": "Qubits use superposition to represent 0 and 1 simultaneously.",
})

results = await memory.search("superposition")
# → [{"task": "Research quantum computing", "output": "..."}]
```

---

## OpenAI Agents SDK

WalrusOS provides `WalrusConversationStore`, implementing the Agents SDK's `ConversationStore` protocol.

**Install:**

```bash
pip install walrusos openai-agents
```

**Use:**

```python
from agents import Agent, Runner
from walrusos import WalrusOS
from walrusos.integrations.openai import WalrusConversationStore

runtime = WalrusOS()
store   = WalrusConversationStore(runtime.workspace("app").stream("conversations"))

runner = Runner(agent=my_agent, conversation_store=store)
```

Every conversation turn is persisted as a WalrusOS memory event. Conversations survive process restarts and can be replayed exactly.

---

## AutoGen

WalrusOS provides `WalrusGroupChatManager`, which replaces AutoGen's default in-memory message history.

**Install:**

```bash
pip install walrusos pyautogen
```

**Use:**

```python
from autogen import AssistantAgent, UserProxyAgent
from walrusos import WalrusOS
from walrusos.integrations.autogen import WalrusGroupChatManager

runtime = WalrusOS()
manager = WalrusGroupChatManager(runtime.workspace("group").stream("chat"))

assistant = AssistantAgent("assistant", llm_config={...})
user      = UserProxyAgent("user", human_input_mode="NEVER")

# Initiate chat — messages go to WalrusOS
user.initiate_chat(
    assistant,
    message="Write a haiku about memory.",
    chat_manager=manager,
)
```

---

## LlamaIndex

WalrusOS provides `WalrusChatMemoryBuffer`, replacing LlamaIndex's default `ChatMemoryBuffer`.

**Install:**

```bash
pip install walrusos llama-index
```

**Use:**

```python
from llama_index.core.chat_engine import SimpleChatEngine
from walrusos import WalrusOS
from walrusos.integrations.llamaindex import WalrusChatMemoryBuffer

runtime = WalrusOS()
memory  = WalrusChatMemoryBuffer(runtime.workspace("chat").stream("history"))

engine = SimpleChatEngine.from_defaults(memory=memory)
response = engine.chat("What did we discuss last time?")
```

Chat history is persisted and searchable. `engine.chat()` loads the full conversation context from Walrus automatically.

---

## PydanticAI

WalrusOS provides a memory tool and result processor for PydanticAI agents.

**Install:**

```bash
pip install walrusos pydantic-ai
```

**Use:**

```python
from pydantic_ai import Agent
from walrusos import WalrusOS
from walrusos.integrations.pydanticai import WalrusMemoryTool, WalrusResultProcessor

runtime   = WalrusOS()
stream    = runtime.workspace("app").stream("agent-memory")

memory_tool = WalrusMemoryTool(stream)
processor   = WalrusResultProcessor(stream)

agent = Agent(
    "openai:gpt-4o",
    tools=[memory_tool],
    result_processor=processor,
)

result = await agent.run("What do you remember about me?")
```

The memory tool lets the agent explicitly read and write to its WalrusOS stream. The result processor automatically saves every agent output.

---

## Using multiple frameworks together

WalrusOS is framework-agnostic. A LangGraph agent and a CrewAI agent can share the same stream:

```python
runtime   = WalrusOS()
workspace = runtime.workspace("multi-agent")

# LangGraph agent writes to "shared-context"
lg_memory = AsyncWalrusSaver(workspace.stream("shared-context"))
lg_app    = lg_graph.compile(checkpointer=lg_memory)

# CrewAI agent reads from the same "shared-context"
crew_memory = WalrusMemory(workspace.stream("shared-context"))
crew        = Crew(..., embedder=crew_memory)
```

Both agents see the same events. Each event is signed with the writing agent's key, so you always know who wrote what.

---

## Testing integrations

All integrations work with `use_mocks=True` — no network required:

```python
runtime = WalrusOS(use_mocks=True)
memory  = AsyncWalrusSaver(runtime.workspace("test").stream("checkpoints"))
# Runs entirely in-process — no Walrus, no Sui, no network
```

Use this in your test suite. Switch to `WalrusOS()` for production.
