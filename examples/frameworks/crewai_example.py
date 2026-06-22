"""
Example: Using WalrusOS with CrewAI
"""
import asyncio
from walrusos import WalrusOS
from walrusos.integrations.crewai import WalrusMemory

async def main():
    runtime = WalrusOS(use_mocks=True)
    memory = WalrusMemory(runtime.workspace("app").agent("crew-agent").stream("episodes"))
    
    await memory.save({"task": "Research WalrusOS", "output": "It's event sourced!"})
    results = await memory.search("event sourced")
    print(f"Found {len(results)} memories.")

if __name__ == "__main__":
    asyncio.run(main())
