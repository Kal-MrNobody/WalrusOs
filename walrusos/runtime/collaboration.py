import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from walrusos.core.models.memory import MemoryEvent

@dataclass
class ConsensusResult:
    question: str
    votes: List[Dict[str, Any]]
    result: bool
    confidence: float
    reasoning: List[str]

class Pipeline:
    def __init__(self, agents: List["AgentClient"], stream: "StreamClient"):
        self.agents = agents
        self.stream = stream

    async def run(self, initial_input: str) -> List[MemoryEvent]:
        events_produced = []
        queues = [asyncio.Queue() for _ in range(len(self.agents))]
        
        # Setup all subscriptions first
        def make_cb(q, prev_agent_id):
            async def _cb(ev: MemoryEvent):
                if getattr(ev, "agent_id", None) == prev_agent_id:
                    await q.put(ev)
            return _cb
            
        for i in range(1, len(self.agents)):
            prev_agent_id = self.agents[i-1]._agent_id_str
            await self.agents[i].subscribe(self.stream, make_cb(queues[i], prev_agent_id))

        # Give EventBus a moment to register callbacks
        await asyncio.sleep(0.01)

        try:
            # Step 1: The first agent publishes the initial input
            ev = await self.agents[0].publish(self.stream, {"msg": initial_input}, memory_type="working")
            mem_ev = await self.agents[0]._engine.ledger.get_event(ev.event_id)
            if mem_ev:
                events_produced.append(mem_ev)
                
            # Step 2 to N: Each subsequent agent reads the output of the previous agent and publishes
            for i in range(1, len(self.agents)):
                agent = self.agents[i]
                
                # Wait for the event from the previous agent (timeout: 60s)
                prev_event = await asyncio.wait_for(queues[i].get(), timeout=60.0)
                
                response_msg = f"Processed by {agent.agent_name}"
                new_ev = await agent.publish(self.stream, {"msg": response_msg}, memory_type="working")
                new_mem_ev = await agent._engine.ledger.get_event(new_ev.event_id)
                if new_mem_ev:
                    events_produced.append(new_mem_ev)
        finally:
            for i in range(1, len(self.agents)):
                await self.agents[i].unsubscribe(self.stream)

        return events_produced

class Broadcast:
    def __init__(self, source: "AgentClient", recipients: List["AgentClient"], stream: "StreamClient"):
        self.source = source
        self.recipients = recipients
        self.stream = stream

    async def send(self, content: str) -> List[MemoryEvent]:
        responses = []
        queue = asyncio.Queue()
        recipient_ids = {a._agent_id_str for a in self.recipients}
        
        async def _callback(event: MemoryEvent):
            if getattr(event, "agent_id", None) in recipient_ids:
                await queue.put(event)
                
        await self.source.subscribe(self.stream, _callback)

        try:
            # Source publishes
            await self.source.publish(self.stream, {"msg": content}, memory_type="working")
            
            # Since the agents are not actually hooked up to LLMs in this minimal runtime test,
            # we must simulate their responses if we want to test broadcast realistically, 
            # or expect the caller to trigger their responses externally.
            # The pattern says "Returns all response events (one per recipient that responds)".
            
            # Wait for responses
            while len(responses) < len(self.recipients):
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=30.0)
                    responses.append(ev)
                except asyncio.TimeoutError:
                    break
        finally:
            await self.source.unsubscribe(self.stream)
            
        return responses

class Consensus:
    def __init__(self, agents: List["AgentClient"], stream: "StreamClient"):
        self.agents = agents
        self.stream = stream

    async def vote(self, question: str) -> ConsensusResult:
        queue = asyncio.Queue()
        agent_ids = {a._agent_id_str for a in self.agents}
        
        async def _callback(event: MemoryEvent):
            if getattr(event, "agent_id", None) in agent_ids:
                await queue.put(event)
                
        # Subscribe to collect responses
        await self.agents[0].subscribe(self.stream, _callback)

        try:
            # We assume the caller or the agents themselves will publish responses.
            # Wait for all agents to vote.
            responses = []
            while len(responses) < len(self.agents):
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=45.0)
                    responses.append(ev)
                except asyncio.TimeoutError:
                    break
        finally:
            await self.agents[0].unsubscribe(self.stream)
            
        votes = []
        yes_count = 0
        reasoning = []
        
        for ev in responses:
            try:
                payload = await self.agents[0]._engine.read(ev.id)
                msg = str(payload.get("msg", "")).lower()
                is_yes = any(word in msg for word in ["yes", "approve", "agree"])
                votes.append({
                    "agent_id": ev.agent_id,
                    "response": msg,
                    "vote": is_yes
                })
                if is_yes:
                    yes_count += 1
                reasoning.append(msg)
            except Exception:
                pass
                
        total = len(responses) or 1
        confidence = yes_count / total
        result = yes_count > (total / 2)
        
        return ConsensusResult(
            question=question,
            votes=votes,
            result=result,
            confidence=confidence,
            reasoning=reasoning
        )
