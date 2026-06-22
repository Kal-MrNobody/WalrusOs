# Examples

Working code examples for common scenarios. All examples support `use_mocks=True` for offline testing.

---

## 01 — Research team with shared memory

Three agents collaborate on a research project. The Researcher discovers papers, the Reviewer critiques them, and the Writer synthesizes results.

**What this demonstrates:** multi-agent shared streams, pub/sub, semantic search

```python
import asyncio
from walrusos import WalrusOS

async def main():
    runtime   = WalrusOS(use_mocks=True)
    workspace = runtime.workspace("research-team")
    stream    = workspace.stream("papers")

    researcher = workspace.agent("Researcher")
    reviewer   = workspace.agent("Reviewer")
    writer     = workspace.agent("Writer")

    # Researcher finds a paper
    await researcher.publish(stream, {
        "title":  "Attention Is All You Need",
        "year":   2017,
        "claims": ["Transformers eliminate recurrence", "Self-attention enables parallelism"],
    })

    await researcher.publish(stream, {
        "title":  "BERT: Pre-training of Deep Bidirectional Transformers",
        "year":   2018,
        "claims": ["Bidirectional context improves NLU", "Fine-tuning beats feature extraction"],
    })

    # Reviewer reacts to each paper in real-time
    async def review(payload):
        print(f"Reviewer reads: {payload['title']}")
        await reviewer.publish(stream, {
            "reviewing": payload["title"],
            "verdict":   "accepted",
            "notes":     "Strong empirical results.",
        })

    sub = await reviewer.subscribe(stream, review)
    await asyncio.sleep(0.1)  # let events propagate
    sub.cancel()

    # Writer synthesizes
    results = await stream.search("attention transformer")
    print(f"Writer found {len(results)} relevant papers")

    # Full timeline
    timeline = await stream.timeline()
    print(f"Stream has {len(timeline)} total events")

asyncio.run(main())
```

[→ Full example](../examples/01_research_team/)

---

## 02 — Fork/merge for agent experimentation

An agent tries two different approaches in parallel branches, then merges the winner.

**What this demonstrates:** fork, merge, branch comparison

```python
import asyncio
from walrusos import WalrusOS

async def main():
    runtime = WalrusOS(use_mocks=True)
    agent   = runtime.workspace("engineering").agent("Optimizer")
    main_stream = agent.stream("training-runs")

    # Record baseline
    await main_stream.append({
        "run": "baseline",
        "accuracy": 0.82,
        "params": {"lr": 0.001, "batch_size": 32},
    })

    # Fork for experiment A
    fork_a_id = await main_stream.fork()
    fork_a    = runtime.workspace("engineering").stream_by_id(fork_a_id)
    await fork_a.append({
        "run": "experiment-A",
        "accuracy": 0.87,
        "params": {"lr": 0.0005, "batch_size": 64},
    })

    # Fork for experiment B (from main, not from A)
    fork_b_id = await main_stream.fork()
    fork_b    = runtime.workspace("engineering").stream_by_id(fork_b_id)
    await fork_b.append({
        "run": "experiment-B",
        "accuracy": 0.91,
        "params": {"lr": 0.0001, "batch_size": 128},
    })

    # Experiment B wins — merge it
    await main_stream.merge(fork_b_id)

    # Discard experiment A
    # (fork_a events remain accessible but are not merged)

    timeline = await main_stream.timeline()
    print(f"Main stream: {len(timeline)} events (baseline + B's results)")

asyncio.run(main())
```

[→ Full example](../examples/02_software_engineering/)

---

## 03 — Real-time market intelligence

A trading team of agents communicates through streams with real-time subscriptions.

**What this demonstrates:** pub/sub, multiple subscribers, high-frequency writes

```python
import asyncio
from walrusos import WalrusOS

async def main():
    runtime    = WalrusOS(use_mocks=True)
    workspace  = runtime.workspace("trading-desk")
    market_stream = workspace.stream("signals")

    analyst   = workspace.agent("Analyst")
    risk_mgr  = workspace.agent("RiskManager")
    executor  = workspace.agent("Executor")

    received = []

    async def risk_check(payload):
        if payload.get("signal") == "BUY" and payload.get("confidence", 0) > 0.9:
            received.append(("risk", payload["ticker"]))

    async def execute_order(payload):
        if payload.get("signal") == "BUY":
            received.append(("execute", payload["ticker"]))

    sub_risk = await risk_mgr.subscribe(market_stream, risk_check)
    sub_exec = await executor.subscribe(market_stream, execute_order)

    # Analyst publishes signals
    signals = [
        {"ticker": "AAPL", "signal": "BUY", "confidence": 0.95},
        {"ticker": "TSLA", "signal": "SELL", "confidence": 0.80},
        {"ticker": "NVDA", "signal": "BUY", "confidence": 0.92},
    ]
    for s in signals:
        await analyst.publish(market_stream, s)

    await asyncio.sleep(0.1)
    sub_risk.cancel()
    sub_exec.cancel()

    print(f"Risk checks: {[r for t, r in received if t == 'risk']}")
    print(f"Executed: {[r for t, r in received if t == 'execute']}")

asyncio.run(main())
```

[→ Full example](../examples/03_trading_team/)

---

## 04 — Customer support with semantic memory

A support agent remembers past interactions and retrieves relevant context by meaning.

**What this demonstrates:** semantic search, episodic memory, context retrieval

```python
import asyncio
from walrusos import WalrusOS

async def main():
    runtime = WalrusOS(use_mocks=True)
    agent   = runtime.workspace("support").agent("SupportBot")
    stream  = agent.stream("interactions")

    # Record past interactions
    interactions = [
        {"customer": "alice", "issue": "Can't log in — password reset not working"},
        {"customer": "bob",   "issue": "Billing charge appears twice this month"},
        {"customer": "carol", "issue": "API rate limit error on the /v2/search endpoint"},
        {"customer": "alice", "issue": "Login still broken after reset — getting 401"},
    ]
    for interaction in interactions:
        await stream.append(interaction, memory_type="episodic")

    # New support ticket: "Alice can't authenticate"
    # Retrieve relevant context by meaning
    context = await stream.search("authentication login password", limit=3)

    print("Relevant past interactions:")
    for payload, score in context:
        print(f"  [{score:.2f}] {payload['customer']}: {payload['issue']}")

asyncio.run(main())
```

---

## 05 — Crash recovery

An agent checkpoints its progress. After a simulated crash, it recovers exactly where it left off.

**What this demonstrates:** checkpoints, crash recovery, stream replay

```python
import asyncio
from walrusos import WalrusOS

async def simulate_agent_run(runtime, resume_from=None):
    agent  = runtime.workspace("research").agent("LongRunningAgent")
    stream = agent.stream("progress")

    if resume_from:
        # Replay from checkpoint to restore state
        past = await stream.replay(until_event=resume_from)
        last_step = max(p.get("step", 0) for _, p in past) if past else 0
        print(f"Resuming from step {last_step + 1}")
        start = last_step + 1
    else:
        start = 1

    last_checkpoint = None
    for step in range(start, start + 5):
        await stream.append({"step": step, "status": "processing", "data": f"result_{step}"})

        # Checkpoint every 2 steps
        if step % 2 == 0:
            last_checkpoint = (await stream.timeline())[-1][0].event_id
            await stream.append({"type": "checkpoint", "at_step": step, "event_id": last_checkpoint})
            print(f"Checkpoint at step {step}: {last_checkpoint[:16]}...")

    return last_checkpoint

async def main():
    runtime = WalrusOS(use_mocks=True)

    # First run
    print("=== First run ===")
    checkpoint = await simulate_agent_run(runtime)

    # Simulated crash — restart from checkpoint
    print("\n=== Crash! Restarting from checkpoint ===")
    runtime2 = WalrusOS(use_mocks=True)
    await simulate_agent_run(runtime2, resume_from=checkpoint)

asyncio.run(main())
```

---

## 06 — LangGraph with persistent checkpoints

A LangGraph graph that survives process restarts.

```python
import asyncio
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, START, END
from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver

class State(TypedDict):
    messages: Annotated[list, operator.add]
    step: int

async def agent_node(state: State):
    step = state.get("step", 0) + 1
    print(f"Running step {step}")
    return {
        "messages": [f"Completed step {step}"],
        "step": step,
    }

async def main():
    runtime = WalrusOS(use_mocks=True)
    memory  = AsyncWalrusSaver(runtime.workspace("app").stream("graph-state"))

    builder = StateGraph(State)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    app = builder.compile(checkpointer=memory)

    config = {"configurable": {"thread_id": "session-1"}}

    # First run
    result = await app.ainvoke({"messages": ["Start"], "step": 0}, config=config)
    print(f"After first run: step={result['step']}")

    # Second run — picks up from where it left off
    result = await app.ainvoke({"messages": ["Continue"], "step": result["step"]}, config=config)
    print(f"After second run: step={result['step']}")

    # Inspect the checkpoint stream directly
    stream = runtime.workspace("app").stream("graph-state")
    timeline = await stream.timeline()
    print(f"Checkpoints stored: {len(timeline)}")

asyncio.run(main())
```

---

## Running all examples

```bash
# Clone the repo
git clone https://github.com/walrusos/walrusos
cd walrusos
pip install -e ".[dev]"

# Run any example
python examples/v0.1_hello_world.py
python examples/shared_memory.py
python examples/integration_langgraph.py

# Run framework-specific examples
python examples/frameworks/langgraph_example.py
python examples/frameworks/crewai_example.py
python examples/frameworks/autogen_example.py
```

All examples use `use_mocks=True` by default. Remove it and set `WALRUSOS_KEY_PASSWORD` for production.
