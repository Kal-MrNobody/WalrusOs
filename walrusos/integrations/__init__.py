"""
WalrusOS framework integrations.

All imports are guarded — missing optional dependencies (langgraph, crewai,
etc.) do not prevent the core SDK from loading.

Import directly:

    from walrusos.integrations.langgraph import AsyncWalrusSaver
    from walrusos.integrations.crewai    import WalrusMemory
    from walrusos.integrations.openai    import WalrusConversationStore
    from walrusos.integrations.autogen   import WalrusMessageStore
    from walrusos.integrations.llamaindex import WalrusChatStore
    from walrusos.integrations.pydantic_ai import WalrusMemoryTool
"""

__all__: list = []

try:
    from .langgraph import AsyncWalrusSaver
    __all__.append("AsyncWalrusSaver")
except ImportError:
    pass

try:
    from .crewai import WalrusMemory
    __all__.append("WalrusMemory")
except ImportError:
    pass

try:
    from .openai import WalrusConversationStore
    __all__.append("WalrusConversationStore")
except ImportError:
    pass

try:
    from .autogen import WalrusMessageStore
    __all__.append("WalrusMessageStore")
except ImportError:
    pass

try:
    from .llamaindex import WalrusChatStore, WalrusDocumentStore
    __all__ += ["WalrusChatStore", "WalrusDocumentStore"]
except ImportError:
    pass

try:
    from .pydantic_ai import WalrusMemoryTool, WalrusResultProcessor
    __all__ += ["WalrusMemoryTool", "WalrusResultProcessor"]
except ImportError:
    pass
