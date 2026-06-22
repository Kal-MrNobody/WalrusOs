"""
AgentIdentity — first-class protocol domain model.

An AgentIdentity is the persistent, cryptographically-anchored representation
of a WalrusOS agent.  A wallet may own many agents; each agent has its own:

  - Ed25519 key-pair (public key anchored on-chain, private key in KeyStore)
  - Independent execution / memory / artifact counters
  - Trust root (deterministic, globally-unique SHA-256 fingerprint)
  - On-chain Sui AgentIdentity object (when wallet is connected)
  - Status lifecycle: active → paused → terminated

Every MemoryEvent produced by an agent is stamped with its agent_id.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class AgentReputation(BaseModel):
    """
    Deterministic trust graph counters for the agent.
    Forms the basis of the zero-knowledge TrustRoot accumulator.
    """
    successful_signatures:  int = Field(default=0)
    failed_verifications:   int = Field(default=0)
    memory_writes:          int = Field(default=0)
    artifact_uploads:       int = Field(default=0)
    validation_approvals:   int = Field(default=0)
    validation_failures:    int = Field(default=0)
    capability_grants:      int = Field(default=0)
    capability_revocations: int = Field(default=0)


class AgentStatus(str, Enum):
    """Lifecycle state of an agent."""
    ACTIVE     = "active"
    PAUSED     = "paused"
    TERMINATED = "terminated"


class AgentCapability(str, Enum):
    """Fine-grained permission flags an agent may hold."""
    READ  = "read"
    WRITE = "write"
    FORK  = "fork"
    MERGE = "merge"


def _compute_trust_root(
    owner_wallet: str,
    workspace_id: str,
    agent_name: str,
) -> str:
    """
    Compute the agent's trust root.

    A trust root is a deterministic SHA-256 fingerprint derived from the
    three attributes that uniquely identify an agent in the protocol:
      - The wallet that owns it
      - The workspace it belongs to
      - Its name within that workspace

    This value is globally unique (assuming unique agent names per workspace)
    and does not require a network call to compute.
    """
    material = f"{owner_wallet}:{workspace_id}:{agent_name}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class AgentIdentity(BaseModel):
    """
    Persistent, cryptographically-anchored identity for a WalrusOS agent.

    Persisted in:
      - SQLite (local ledger) — primary source of truth
      - Sui blockchain — on-chain AgentIdentity object (when wallet connected)

    Counters:
      execution_counter — number of publish() calls
      memory_counter    — number of MemoryEvents appended to streams
      artifact_counter  — number of Walrus blobs stored by this agent
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    agent_id:     str = Field(..., description="Deterministic UUID5 hex string")
    workspace_id: str = Field(..., description="Workspace UUID hex string")
    agent_name:   str = Field(..., description="Human-readable name within workspace")
    owner_wallet: str = Field(..., description="Sui wallet address (0x…)")

    # ── Cryptography ──────────────────────────────────────────────────────────
    public_key:  str = Field(..., description="Ed25519 public key, hex-encoded")
    trust_root:  str = Field(..., description="SHA-256(owner_wallet:workspace_id:agent_name)")

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    created_at:  str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status:      AgentStatus = Field(default=AgentStatus.ACTIVE)

    # ── Permissions ───────────────────────────────────────────────────────────
    capabilities: List[str] = Field(
        default_factory=lambda: [
            AgentCapability.READ, AgentCapability.WRITE,
            AgentCapability.FORK, AgentCapability.MERGE,
        ]
    )

    # ── Counters & Trust Graph ────────────────────────────────────────────────
    execution_counter: int = Field(default=0, description="Number of publish() calls")
    memory_counter:    int = Field(default=0, description="Number of MemoryEvents appended")
    artifact_counter:  int = Field(default=0, description="Number of Walrus blobs stored")
    reputation: AgentReputation = Field(default_factory=AgentReputation, description="Trust Graph metrics")

    # ── Metadata ──────────────────────────────────────────────────────────────
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value tags (model name, version, etc.)",
    )

    # ── On-chain ──────────────────────────────────────────────────────────────
    sui_object_id: Optional[str] = Field(
        default=None,
        description="Sui AgentIdentity object ID (0x…). Populated after on-chain registration.",
    )

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        workspace_name: str,
        agent_name:     str,
        owner_wallet:   str,
        public_key_hex: str,
        metadata:       Optional[Dict[str, Any]] = None,
    ) -> "AgentIdentity":
        """
        Create a new AgentIdentity with deterministic IDs.

        The ``agent_id`` and ``workspace_id`` are derived deterministically from
        the names, so the same agent always has the same UUID across restarts.
        """
        workspace_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, workspace_name))
        agent_id     = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{workspace_name}.agent.{agent_name}"))
        trust_root   = _compute_trust_root(owner_wallet, workspace_id, agent_name)
        return cls(
            agent_id=agent_id,
            workspace_id=workspace_id,
            agent_name=agent_name,
            owner_wallet=owner_wallet,
            public_key=public_key_hex,
            trust_root=trust_root,
            metadata=metadata or {},
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def capability_bitmask(self) -> int:
        """Return the integer bitmask for the current capability set."""
        mask = 0
        cap_bits = {
            AgentCapability.READ: 1, AgentCapability.WRITE: 2,
            AgentCapability.FORK: 4, AgentCapability.MERGE: 8,
        }
        for cap in self.capabilities:
            mask |= cap_bits.get(AgentCapability(cap), 0)
        return mask

    def to_envelope(self) -> Dict[str, Any]:
        """
        Return a compact dict that is embedded in every MemoryEvent envelope.

        This is stored in the Walrus blob alongside the payload so that the
        authorship is self-contained in the blob content.
        """
        return {
            "agent_id":    self.agent_id,
            "agent_name":  self.agent_name,
            "trust_root":  self.trust_root,
            "public_key":  self.public_key,
            "workspace_id": self.workspace_id,
        }

    def roll_trust_root(self, event_id: str) -> None:
        """
        Deterministically advance the trust root.
        New_TrustRoot = SHA-256(Previous_TrustRoot : Event_ID)
        """
        material = f"{self.trust_root}:{event_id}".encode("utf-8")
        self.trust_root = hashlib.sha256(material).hexdigest()
