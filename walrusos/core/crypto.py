"""
Cryptographic utilities for WalrusOS Protocol Hardening Phase 3.

Provides functions for canonical JSON serialization, hashing, and 
Ed25519 signing/verification.
"""
import hashlib
import json
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonicalize_payload(payload: Dict[str, Any]) -> bytes:
    """
    Serialize a dictionary to a canonical, deterministic JSON byte string.
    Ensures that identical payloads always hash to the same value regardless
    of key insertion order or formatting.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def hash_payload(canonical_bytes: bytes) -> str:
    """
    Compute the SHA-256 hash of canonical payload bytes.
    Returns the hex-encoded digest.
    """
    return hashlib.sha256(canonical_bytes).hexdigest()


def sign_payload(private_key_bytes: bytes, event_hash_hex: str) -> str:
    """
    Sign a hex-encoded event hash using an Ed25519 private key.
    Returns the base64-encoded signature.
    """
    from base64 import b64encode
    priv = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    # We sign the raw bytes of the hash
    sig_bytes = priv.sign(bytes.fromhex(event_hash_hex))
    return b64encode(sig_bytes).decode("utf-8")


def verify_signature(public_key_hex: str, event_hash_hex: str, signature_b64: str) -> bool:
    """
    Verify an Ed25519 signature against an event hash.
    Returns True if valid, False otherwise.
    """
    from base64 import b64decode
    from cryptography.exceptions import InvalidSignature
    
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        sig_bytes = b64decode(signature_b64)
        hash_bytes = bytes.fromhex(event_hash_hex)
        pub.verify(sig_bytes, hash_bytes)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
