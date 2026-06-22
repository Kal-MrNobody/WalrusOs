"""
Example: Using WalrusOS with PydanticAI
"""
import asyncio
from walrusos import WalrusOS
from walrusos.integrations.pydantic_ai import WalrusMessageHistory

async def main():
    runtime = WalrusOS(use_mocks=True)
    history = WalrusMessageHistory(runtime.workspace("app").agent("pydantic").stream("history"))
    
    await history.sync_messages([{"role": "user", "content": "Analyze this data."}])
    msgs = await history.get_messages()
    print(f"Synced and retrieved {len(msgs)} messages from history.")

if __name__ == "__main__":
    asyncio.run(main())
