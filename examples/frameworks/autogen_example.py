"""
Example: Using WalrusOS with AutoGen
"""
import asyncio
from walrusos import WalrusOS
from walrusos.integrations.autogen import WalrusMessageStore

async def main():
    runtime = WalrusOS(use_mocks=True)
    store = WalrusMessageStore(runtime.workspace("app").agent("autogen").stream("messages"))
    
    await store.on_message("user", "assistant", "Tell me a joke", role="user")
    history = await store.get_history()
    print(f"Retrieved {len(history)} messages from the store.")

if __name__ == "__main__":
    asyncio.run(main())
