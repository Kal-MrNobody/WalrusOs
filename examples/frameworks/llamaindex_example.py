"""
Example: Using WalrusOS with LlamaIndex
"""
import asyncio
from walrusos import WalrusOS
from walrusos.integrations.llamaindex import WalrusChatStore

async def main():
    runtime = WalrusOS(use_mocks=True)
    store = WalrusChatStore(runtime.workspace("app").agent("llamaindex").stream("chat"))
    
    class MockMessage:
        role = "user"
        content = "Hello, knowledge base!"
        additional_kwargs = {}

    await store.add_message("session-1", MockMessage())
    messages = await store.get_messages("session-1")
    print(f"Recovered message: {messages[0]['content']}")

if __name__ == "__main__":
    asyncio.run(main())
