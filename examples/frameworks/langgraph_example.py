"""
Example: Using WalrusOS with LangGraph
"""
import asyncio
from walrusos import WalrusOS
from walrusos.integrations.langgraph import AsyncWalrusSaver

async def main():
    runtime = WalrusOS(use_mocks=True)
    memory = AsyncWalrusSaver(runtime.workspace("app").agent("lg-agent").stream("checkpoints"))
    
    # Example mock usage:
    await memory.aput({"configurable": {"thread_id": "1"}}, {"id": "c1", "ts": "2026", "channel_values": {}}, {})
    checkpoint = await memory.aget_tuple({"configurable": {"thread_id": "1"}})
    print(f"Recovered checkpoint: {checkpoint.checkpoint['id']}")

if __name__ == "__main__":
    asyncio.run(main())
