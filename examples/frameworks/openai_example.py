"""
Example: Using WalrusOS with OpenAI Agents SDK
"""
import asyncio
from walrusos import WalrusOS
from walrusos.integrations.openai import WalrusConversationStore

async def main():
    runtime = WalrusOS(use_mocks=True)
    store = WalrusConversationStore(runtime.workspace("app").agent("openai").stream("conversations"))
    
    await store.append_turn("t-123", "user", "What is the capital of France?")
    turns = await store.get_thread("t-123")
    print(f"Retrieved {len(turns)} turns from conversation thread.")

if __name__ == "__main__":
    asyncio.run(main())
