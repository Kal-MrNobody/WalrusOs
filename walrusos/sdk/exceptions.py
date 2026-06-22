"""
WalrusOS SDK Exceptions.

Import these from the top-level package:

    from walrusos import WalrusOSError
"""


class WalrusOSError(Exception):
    """
    Base exception for all WalrusOS SDK errors.

    All WalrusOS exceptions are subclasses of this.  Catch it to handle
    any WalrusOS error in a single ``except`` clause:

        try:
            await stream.append(payload)
        except WalrusOSError as e:
            print(f"WalrusOS error: {e}")
    """
    pass


class AgentNotFoundError(WalrusOSError):
    """
    Raised when an agent cannot be resolved from the ledger.

    This usually means the agent name is wrong or the database was reset.
    Check that the agent name matches exactly what was used to create it.
    """
    pass


class StreamNotFoundError(WalrusOSError):
    """
    Raised when a stream ID does not exist in the ledger.

    This can happen after a database reset.  Run ``walrusos recover``
    to rebuild the local database from the network.
    """
    pass


class CryptographicVerificationError(WalrusOSError):
    """
    Raised when an event fails signature or hash verification.

    This means the event was tampered with or written by a different key.
    The event is dropped during replay.

    If you see this unexpectedly, check that ``WALRUSOS_KEY_PASSWORD``
    is set consistently across process restarts.
    """
    pass


class CapabilityRevokedError(WalrusOSError):
    """
    Raised when an agent uses a revoked or expired capability.

    The capability was valid when granted but has since been revoked or
    its ``valid_until_epoch`` has passed.  Ask the stream owner to re-grant:

        await workspace.grant(owner, agent, "write", stream)
    """
    pass


class CapabilityDeniedError(WalrusOSError):
    """
    Raised when an agent lacks a required capability.

    Grant the capability from the stream owner:

        await workspace.grant(owner_agent, this_agent, "write", stream)
    """
    pass


class WorkspaceNotFoundError(WalrusOSError):
    """
    Raised when attempting to access a workspace that does not exist.

    Workspaces are created lazily — this is only raised when accessing
    a workspace by ID that was never initialised.
    """
    pass


class WalrusConnectionError(WalrusOSError):
    """
    Raised when the Walrus network cannot be reached.

    The SDK writes to local SQLite first and retries network operations
    asynchronously.  You can usually continue working while the network
    is temporarily unavailable.

    Check the Walrus testnet status at https://walrus.xyz/status
    or use ``WalrusOS(use_mocks=True)`` for offline development.
    """
    pass


class WalrusKeyDestroyedError(WalrusOSError):
    """
    Raised when attempting to decrypt data after ``shred_key()`` was called.

    The Data Encryption Key (DEK) has been permanently destroyed.
    Blobs encrypted with that key are unreadable.  This is intentional
    and irreversible — do not call ``shred_key()`` unless you intend to
    permanently destroy the data.
    """
    pass
