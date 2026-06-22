"""
WalrusOS — Git for AI Memory.

Quickstart::

    from walrusos import WalrusOS

    runtime = WalrusOS(use_mocks=True)   # no network needed
    stream  = runtime.workspace("myapp").agent("Alice").stream("memory")

    event = await stream.append({"thought": "Hello WalrusOS!"})

    for event, payload in await stream.timeline():
        print(payload["thought"])

Set ``WALRUSOS_USE_MOCKS=1`` to default all runtimes to mock mode
(useful in tests — no code changes needed).
"""
from walrusos.client import WalrusOS
from walrusos.types import MemoryType, MT
from walrusos.sdk.exceptions import (
    WalrusOSError,
    AgentNotFoundError,
    StreamNotFoundError,
    CryptographicVerificationError,
    CapabilityRevokedError,
    CapabilityDeniedError,
    WorkspaceNotFoundError,
    WalrusConnectionError,
    WalrusKeyDestroyedError,
)

__version__ = "0.1.0"

__all__ = [
    # Core runtime
    "WalrusOS",

    # Types
    "MemoryType",
    "MT",

    # Exceptions
    "WalrusOSError",
    "AgentNotFoundError",
    "StreamNotFoundError",
    "CryptographicVerificationError",
    "CapabilityRevokedError",
    "CapabilityDeniedError",
    "WorkspaceNotFoundError",
    "WalrusConnectionError",
    "WalrusKeyDestroyedError",
]
