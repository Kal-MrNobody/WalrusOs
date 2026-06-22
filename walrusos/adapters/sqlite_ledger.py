"""
SQLite-backed persistent LedgerAdapter.

This is the production local ledger. It replaces InMemoryLedger for all
non-test use.

Design:
  - SQLite via SQLModel (same ORM used for domain models)
  - Six tables: MemoryStreamRecord, MemoryEventRecord,
                SuiStreamObjectRecord, BlobManifestRecord,
                AgentIdentityRecord, AgentKeyRecord
  - All writes are transactional and atomic
  - Reads are O(1) for head lookups, O(n) for full timelines
  - Epoch counter is stored alongside the stream record — survives restarts
  - Sui stream object mappings survive restart (P0 Fix)
  - Chunk manifest mappings survive restart (P0 Fix)
  - Agent identities are persistent and indexed (Phase 2)

Thread safety: asyncio-safe (single-process); no concurrent writers assumed.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from walrusos.engine.interfaces import LedgerAdapter
from walrusos.core.models.memory import MemoryEvent
from walrusos.core.models.events import ProtocolEvent, EventType


# ── SQLModel table definitions ────────────────────────────────────────────────

class MemoryStreamRecord(SQLModel, table=True):
    """Persisted metadata for a MemoryStream DAG."""
    __tablename__ = "memory_streams"

    stream_id:      str = Field(primary_key=True)   # UUID as hex string
    agent_id:       str = Field(index=True)
    head_event_id:  str = Field(default="genesis")
    epoch_counter:  int = Field(default=0)
    created_at:     str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProtocolEventRecord(SQLModel, table=True):
    """
    Immutable Event Sourced record replacing MemoryEventRecord.
    """
    __tablename__ = "protocol_events"

    event_id:           str = Field(primary_key=True)
    event_type:         str = Field(index=True)
    workspace_id:       str = Field(index=True)
    agent_id:           Optional[str] = Field(default=None, index=True)
    wallet:             str
    blob_id:            Optional[str] = Field(default=None)
    blob_hash:          Optional[str] = Field(default=None)
    parent_event:       Optional[str] = Field(default=None)
    previous_hash:      Optional[str] = Field(default=None)
    signature:          str
    timestamp:          str
    transaction_digest: Optional[str] = Field(default=None)
    payload_json:       str



class MemoryEventRecord(SQLModel, table=True):
    """Persisted MemoryEvent pointer (content lives in Walrus)."""
    __tablename__ = "memory_events"

    id:               str = Field(primary_key=True)
    stream_id:        str = Field(index=True)
    parent_id:        str
    epoch:            int = Field(index=True)
    memory_type:      str = Field(index=True, default="observation")
    tags:             Optional[str] = Field(default=None) # JSON array
    importance:       float = Field(default=0.5, index=True)
    summary:          Optional[str] = Field(default=None)
    embedding:        Optional[str] = Field(default=None) # JSON array
    project:          Optional[str] = Field(default=None, index=True)
    content_blob_id:  str
    # Phase 2: persistent agent attribution (nullable for backward compat)
    agent_id:         Optional[str] = Field(default=None, index=True)
    # Phase 3: Cryptographic verification fields
    event_hash:       Optional[str] = Field(default=None)
    signature:        Optional[str] = Field(default=None)
    public_key:       Optional[str] = Field(default=None)
    created_at:       str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TaskRecord(SQLModel, table=True):
    """Persisted task mapping (SQLite only)."""
    __tablename__ = "tasks"

    task_id:        str = Field(primary_key=True)
    workspace_id:   str = Field(index=True)
    title:          str
    description:    str = Field(default="")
    created_by:     str = Field(index=True)
    assigned_to:    Optional[str] = Field(default=None, index=True)
    status:         str = Field(default="pending", index=True)
    priority:       int = Field(default=3, index=True)
    parent_task_id: Optional[str] = Field(default=None)
    subtask_ids:    str = Field(default="[]") # JSON array
    memory_refs:    str = Field(default="[]") # JSON array
    artifact_refs:  str = Field(default="[]") # JSON array
    tags:           str = Field(default="[]") # JSON array
    created_at:     str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at:     str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at:   Optional[str] = Field(default=None)
    notes:          str = Field(default="")


class WorkspaceRecord(SQLModel, table=True):
    """Persisted mapping of a workspace UUID to its Sui Workspace object ID."""
    __tablename__ = "workspaces"

    workspace_id:  str = Field(primary_key=True)
    sui_object_id: str = Field(index=True)
    name:          str = Field(default="")
    owner_wallet:  str = Field(default="")
    created_at:    str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CapabilityRecord(SQLModel, table=True):
    """
    Phase 4: Persisted mapping of granted capabilities to Sui Capability object IDs.
    """
    __tablename__ = "capabilities"

    sui_object_id:     str = Field(primary_key=True)   # Sui Capability object ID (0x...)
    target_stream_id:  str = Field(index=True)         # Target stream UUID or Sui object ID
    verb_bitmask:      int = Field(default=15)
    valid_until_epoch: int = Field(default=0)
    created_at:        str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SuiStreamObjectRecord(SQLModel, table=True):
    """
    Maps a WalrusOS stream UUID to its on-chain Sui MemoryStream object ID.

    P0 Fix: Previously this mapping was held only in-process RAM inside
    SuiLedgerAdapter._stream_objects.  Any process restart silently broke
    all Sui anchoring for existing streams.  This table persists the mapping
    so it is recovered automatically on startup.
    """
    __tablename__ = "sui_stream_objects"

    stream_id:     str = Field(primary_key=True)   # UUID as hex string
    sui_object_id: str = Field(index=True)         # Sui MemoryStream object ID (0x…)
    created_at:    str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BlobManifestRecord(SQLModel, table=True):
    """
    Persists the manifest blob_id and chunk list for chunked Walrus uploads.

    P0 Fix: The WalrusAdapter._metadata_cache was the only record of which
    "manifest:<id>" strings referred to chunked blobs.  On restart the cache
    was empty and chunked blob_ids (stored in SQLite as content_blob_id values)
    would be unretrievable.  This table persists the mapping.
    """
    __tablename__ = "blob_manifests"

    manifest_blob_id: str = Field(primary_key=True)  # Full "manifest:<id>" string
    chunk_ids_json:   str = Field(...)                # JSON array of chunk blob_ids
    original_size:    int = Field(default=0)          # Uncompressed size in bytes
    mime_type:        str = Field(default="application/octet-stream")
    created_at:       str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentIdentityRecord(SQLModel, table=True):
    """
    Persistent, first-class identity record for a WalrusOS agent.

    Phase 2: Replaces the ephemeral UUID5 alias with a full identity that
    survives restarts, carries cryptographic material, tracks counters, and
    maps to an on-chain Sui AgentIdentity object.
    """
    __tablename__ = "agent_identities"

    agent_id:          str = Field(primary_key=True)   # UUID5 hex string
    workspace_id:      str = Field(index=True)         # Workspace UUID5 hex string
    agent_name:        str = Field(index=True)         # Human-readable name
    owner_wallet:      str = Field(index=True)         # Sui wallet address
    public_key:        str = Field(...)                # Ed25519 public key, hex
    trust_root:        str = Field(index=True)         # SHA-256 trust anchor
    status:            str = Field(default="active")   # active | paused | terminated
    capabilities_json: str = Field(default='["read","write","fork","merge"]')  # JSON
    execution_counter: int = Field(default=0)
    memory_counter:    int = Field(default=0)
    artifact_counter:  int = Field(default=0)
    reputation_json:   str = Field(default="{}")       # JSON representation of AgentReputation
    metadata_json:     str = Field(default="{}")       # JSON object
    sui_object_id:     Optional[str] = Field(default=None, index=True)
    created_at:        str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at:        str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentKeyRecord(SQLModel, table=True):
    """
    Stores the wrapped (encrypted) Ed25519 private key for each agent.

    The private key is wrapped with the same KEK used by the KeyStore,
    so the wallet implicitly protects each agent's signing key.
    """
    __tablename__ = "agent_keys"

    agent_id:    str = Field(primary_key=True)  # FK → agent_identities.agent_id
    wrapped_key: str = Field(...)               # base64(AESGCM(kek).encrypt(privkey))
    kek_salt:    str = Field(...)               # base64 salt for KEK derivation
    created_at:  str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── SQLite Ledger ─────────────────────────────────────────────────────────────

class SQLiteLedger(LedgerAdapter):
    """
    Production LedgerAdapter backed by a local SQLite database.

    The database file lives at ``~/.walrusos/walrusos.db`` by default.
    The path is configurable via ``WalrusOSConfig.db_path``.

    Why SQLite instead of pure InMemory?
    - Survives process restarts (epoch counter, head pointers)
    - Supports `walrusos memory timeline` in the CLI without a live Walrus call
    - Acts as a local read cache so Walrus is only hit for full blob retrieval
    - Persists Sui stream object IDs (P0 Fix)
    - Persists chunk manifest mappings (P0 Fix)
    """

    def __init__(self, db_path: str = "~/.walrusos/walrusos.db") -> None:
        import os
        resolved = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        self._engine = create_engine(
            f"sqlite:///{resolved}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        # WAL mode: better concurrent read performance and crash safety
        with self._engine.connect() as conn:
            conn.execute(  # type: ignore[call-overload]
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL;")
            )
        SQLModel.metadata.create_all(self._engine)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_stream(self, session: Session, stream_id: uuid.UUID) -> Optional[MemoryStreamRecord]:
        return session.get(MemoryStreamRecord, str(stream_id))

    async def append_protocol_event(self, event: ProtocolEvent) -> None:
        """
        Append an immutable ProtocolEvent to the store.
        """
        with Session(self._engine) as session:
            record = ProtocolEventRecord(
                event_id=event.event_id,
                event_type=event.event_type.value,
                workspace_id=event.workspace_id,
                agent_id=event.agent_id,
                wallet=event.wallet,
                blob_id=event.blob_id,
                blob_hash=event.blob_hash,
                parent_event=event.parent_event,
                previous_hash=event.previous_hash,
                signature=event.signature,
                timestamp=event.timestamp,
                transaction_digest=event.transaction_digest,
                payload_json=json.dumps(event.payload, default=str),
            )
            session.add(record)
            session.commit()

    async def get_latest_event_hash(self, workspace_id: str) -> Optional[str]:
        """
        Return the hash of the latest event in the workspace to link the hash chain.
        """
        with Session(self._engine) as session:
            stmt = select(ProtocolEventRecord).where(
                ProtocolEventRecord.workspace_id == workspace_id
            ).order_by(ProtocolEventRecord.timestamp.desc()).limit(1) # type: ignore
            record = session.exec(stmt).first()
            if record:
                return record.event_id
        return None

    async def get_events_for_agent(self, agent_id: str) -> List[ProtocolEvent]:
        """Retrieve all events related to an agent to replay state."""
        with Session(self._engine) as session:
            stmt = select(ProtocolEventRecord).where(
                ProtocolEventRecord.agent_id == agent_id
            ).order_by(ProtocolEventRecord.timestamp.asc()) # type: ignore
            records = session.exec(stmt).all()
            return [self._to_protocol_event(r) for r in records]

    async def get_events_for_workspace(self, workspace_id: str) -> List[ProtocolEvent]:
        """Retrieve all events related to a workspace to replay state."""
        with Session(self._engine) as session:
            stmt = select(ProtocolEventRecord).where(
                ProtocolEventRecord.workspace_id == workspace_id
            ).order_by(ProtocolEventRecord.timestamp.asc()) # type: ignore
            records = session.exec(stmt).all()
            return [self._to_protocol_event(r) for r in records]

    def _to_protocol_event(self, record: ProtocolEventRecord) -> ProtocolEvent:
        return ProtocolEvent(
            event_id=record.event_id,
            event_type=EventType(record.event_type),
            workspace_id=record.workspace_id,
            agent_id=record.agent_id,
            wallet=record.wallet,
            blob_id=record.blob_id,
            blob_hash=record.blob_hash,
            parent_event=record.parent_event,
            previous_hash=record.previous_hash,
            signature=record.signature,
            timestamp=record.timestamp,
            transaction_digest=record.transaction_digest,
            payload=json.loads(record.payload_json),
        )

    # ── LedgerAdapter interface (Legacy Memory Streams) ───────────────────────

    async def create_stream(self, agent_id: uuid.UUID) -> uuid.UUID:
        """
        Create a new MemoryStream record and return its UUID.

        The UUID is freshly generated — if you need a deterministic UUID
        (e.g., from StreamClient), register it via ``_register_stream``.
        """
        stream_id = uuid.uuid4()
        with Session(self._engine) as session:
            record = MemoryStreamRecord(
                stream_id=str(stream_id),
                agent_id=str(agent_id),
            )
            session.add(record)
            session.commit()
        return stream_id

    async def register_stream(self, stream_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        """
        Register a stream with a specific UUID.

        Used by StreamClient to register deterministic UUIDs
        (e.g., uuid5("workspace.stream.name")) without generating a new one.
        """
        with Session(self._engine) as session:
            existing = self._get_stream(session, stream_id)
            if existing is None:
                record = MemoryStreamRecord(
                    stream_id=str(stream_id),
                    agent_id=str(agent_id),
                )
                session.add(record)
                session.commit()

    async def delete_stream(self, stream_id: uuid.UUID) -> None:
        with Session(self._engine) as session:
            # Delete all events first
            events = session.exec(
                select(MemoryEventRecord).where(
                    MemoryEventRecord.stream_id == str(stream_id)
                )
            ).all()
            for ev in events:
                session.delete(ev)
            # Delete the stream record
            record = self._get_stream(session, stream_id)
            if record:
                session.delete(record)
            session.commit()

    async def append_event(self, stream_id: uuid.UUID, event: MemoryEvent) -> None:
        with Session(self._engine) as session:
            # Ensure stream exists
            record = self._get_stream(session, stream_id)
            if record is None:
                record = MemoryStreamRecord(
                    stream_id=str(stream_id),
                    agent_id="unknown",
                )
                session.add(record)

            # Write event
            ev_record = MemoryEventRecord(
                id=event.id,
                stream_id=str(stream_id),
                parent_id=event.parent_id,
                epoch=event.epoch,
                memory_type=event.memory_type,
                tags=json.dumps(event.tags) if event.tags else None,
                importance=event.importance,
                summary=event.summary,
                embedding=json.dumps(event.embedding) if event.embedding else None,
                project=event.project,
                content_blob_id=event.content_blob_id,
                # Phase 2: stamp agent_id if present
                agent_id=getattr(event, "agent_id", None),
                # Phase 3: crypto fields
                event_hash=getattr(event, "event_hash", None),
                signature=getattr(event, "signature", None),
                public_key=getattr(event, "public_key", None),
            )
            session.add(ev_record)

            # Update head + epoch counter
            record.head_event_id = event.id
            record.epoch_counter  = event.epoch

            session.commit()

    async def get_event(self, event_id: str) -> Optional[Any]:
        with Session(self._engine) as session:
            rec = session.get(MemoryEventRecord, event_id)
            if rec is not None:
                return MemoryEvent(
                    id=rec.id,
                    stream_id=uuid.UUID(rec.stream_id),
                    parent_id=rec.parent_id,
                    epoch=rec.epoch,
                    memory_type=rec.memory_type,
                    tags=json.loads(rec.tags) if rec.tags else [],
                    importance=rec.importance,
                    summary=rec.summary,
                    embedding=json.loads(rec.embedding) if rec.embedding else None,
                    project=rec.project,
                    content_blob_id=rec.content_blob_id,
                    agent_id=rec.agent_id,
                    event_hash=rec.event_hash,
                    signature=rec.signature,
                    public_key=rec.public_key,
                )
            # Fallback to ProtocolEventRecord
            p_rec = session.get(ProtocolEventRecord, event_id)
            if p_rec is not None:
                return self._to_protocol_event(p_rec)
            return None

    async def get_head(self, stream_id: uuid.UUID) -> Optional[str]:
        with Session(self._engine) as session:
            record = self._get_stream(session, stream_id)
            if record is None:
                return None
            head = record.head_event_id
            return None if head == "genesis" else head

    async def list_events(self, stream_id: uuid.UUID) -> List[MemoryEvent]:
        """Return all events in epoch order (chronological)."""
        with Session(self._engine) as session:
            records = session.exec(
                select(MemoryEventRecord)
                .where(MemoryEventRecord.stream_id == str(stream_id))
                .order_by(MemoryEventRecord.epoch)
            ).all()
            return [
                MemoryEvent(
                    id=r.id,
                    stream_id=uuid.UUID(r.stream_id),
                    parent_id=r.parent_id,
                    epoch=r.epoch,
                    memory_type=r.memory_type,
                    tags=json.loads(r.tags) if r.tags else [],
                    importance=r.importance,
                    summary=r.summary,
                    embedding=json.loads(r.embedding) if r.embedding else None,
                    project=r.project,
                    content_blob_id=r.content_blob_id,
                    agent_id=r.agent_id,
                    event_hash=r.event_hash,
                    signature=r.signature,
                    public_key=r.public_key,
                )
                for r in records
            ]

    async def get_epoch_counter(self, stream_id: uuid.UUID) -> int:
        """Return the persisted epoch counter for a stream."""
        with Session(self._engine) as session:
            record = self._get_stream(session, stream_id)
            return record.epoch_counter if record else 0

    # ── Sui stream object mapping (P0 Fix) ────────────────────────────────────

    def get_sui_stream_objects(self) -> Dict[str, str]:
        """
        Load all stream_id → sui_object_id mappings from SQLite.

        Called synchronously during SuiLedgerAdapter.__init__ to restore the
        in-process cache from the previous session.
        """
        with Session(self._engine) as session:
            records = session.exec(select(SuiStreamObjectRecord)).all()
            return {r.stream_id: r.sui_object_id for r in records}

    def save_sui_stream_object(self, stream_id: uuid.UUID, sui_object_id: str) -> None:
        """
        Persist a stream_id → sui_object_id mapping.

        Idempotent: if the mapping already exists it is updated in place.
        Called from SuiLedgerAdapter.create_stream() immediately after the
        Sui PTB completes.
        """
        with Session(self._engine) as session:
            existing = session.get(SuiStreamObjectRecord, str(stream_id))
            if existing is None:
                session.add(SuiStreamObjectRecord(
                    stream_id=str(stream_id),
                    sui_object_id=sui_object_id,
                ))
            else:
                existing.sui_object_id = sui_object_id
                session.add(existing)
            session.commit()

    def delete_sui_stream_object(self, stream_id: uuid.UUID) -> None:
        """Remove the Sui object mapping when a stream is deleted."""
        with Session(self._engine) as session:
            record = session.get(SuiStreamObjectRecord, str(stream_id))
            if record:
                session.delete(record)
                session.commit()

    # ── Blob manifest mapping (P0 Fix) ────────────────────────────────────────

    def save_blob_manifest(
        self,
        manifest_blob_id: str,
        chunk_ids: list[str],
        original_size: int,
        mime_type: str = "application/octet-stream",
    ) -> None:
        """
        Persist a chunked blob manifest mapping.

        ``manifest_blob_id`` is the full string returned by store_blob(),
        i.e. it includes the ``"manifest:"`` prefix.
        ``chunk_ids`` is the ordered list of individual chunk blob_ids.
        """
        with Session(self._engine) as session:
            existing = session.get(BlobManifestRecord, manifest_blob_id)
            if existing is None:
                session.add(BlobManifestRecord(
                    manifest_blob_id=manifest_blob_id,
                    chunk_ids_json=json.dumps(chunk_ids),
                    original_size=original_size,
                    mime_type=mime_type,
                ))
                session.commit()

    def get_blob_manifest(self, manifest_blob_id: str) -> Optional[list[str]]:
        """
        Return the ordered chunk blob_id list for a manifest, or None.

        Returns the list of chunk blob_ids so the caller can re-assemble
        the chunked blob without needing the manifest blob itself to be
        in the metadata cache.
        """
        with Session(self._engine) as session:
            record = session.get(BlobManifestRecord, manifest_blob_id)
            if record is None:
                return None
            return json.loads(record.chunk_ids_json)

    # ── AgentIdentity CRUD (Phase 2) ──────────────────────────────────────────

    def create_agent_identity(self, identity) -> None:
        """
        Persist a new AgentIdentity.

        ``identity`` is a ``walrusos.core.models.agent_identity.AgentIdentity``
        instance.  Idempotent: if an identity with the same agent_id already
        exists, it is left unchanged.
        """
        with Session(self._engine) as session:
            existing = session.get(AgentIdentityRecord, identity.agent_id)
            if existing is not None:
                return   # already registered
            record = AgentIdentityRecord(
                agent_id=identity.agent_id,
                workspace_id=identity.workspace_id,
                agent_name=identity.agent_name,
                owner_wallet=identity.owner_wallet,
                public_key=identity.public_key,
                trust_root=identity.trust_root,
                status=identity.status if isinstance(identity.status, str) else identity.status.value,
                capabilities_json=json.dumps(identity.capabilities),
                execution_counter=identity.execution_counter,
                memory_counter=identity.memory_counter,
                artifact_counter=identity.artifact_counter,
                metadata_json=json.dumps(identity.metadata),
                sui_object_id=identity.sui_object_id,
            )
            session.add(record)
            session.commit()

    def get_agent_identity(self, agent_id: str):
        """
        Return an ``AgentIdentity`` for the given agent_id, or None.
        """
        from walrusos.core.models.agent_identity import AgentIdentity
        with Session(self._engine) as session:
            record = session.get(AgentIdentityRecord, agent_id)
            if record is None:
                return None
            return self._record_to_identity(record)

    def get_agent_identity_by_name(self, workspace_id: str, agent_name: str):
        """
        Look up an AgentIdentity by workspace_id + agent_name.

        Returns None if not found.
        """
        with Session(self._engine) as session:
            record = session.exec(
                select(AgentIdentityRecord)
                .where(AgentIdentityRecord.workspace_id == workspace_id)
                .where(AgentIdentityRecord.agent_name == agent_name)
            ).first()
            if record is None:
                return None
            return self._record_to_identity(record)

    def list_agent_identities(self, workspace_id: Optional[str] = None):
        """Return all AgentIdentity objects, optionally filtered by workspace."""
        with Session(self._engine) as session:
            q = select(AgentIdentityRecord)
            if workspace_id is not None:
                q = q.where(AgentIdentityRecord.workspace_id == workspace_id)
            records = session.exec(q).all()
            return [self._record_to_identity(r) for r in records]

    def update_agent_status(self, agent_id: str, status: str) -> None:
        """Update an agent's status (active | paused | terminated)."""
        with Session(self._engine) as session:
            record = session.get(AgentIdentityRecord, agent_id)
            if record is None:
                raise KeyError(f"AgentIdentity '{agent_id}' not found")
            record.status = status
            record.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(record)
            session.commit()

    def increment_agent_counters(
        self,
        agent_id: str,
        *,
        execution: int = 0,
        memory: int = 0,
        artifact: int = 0,
    ) -> None:
        """
        Atomically increment one or more agent counters.

        Typically called by AgentClient.publish() to track activity.
        """
        with Session(self._engine) as session:
            record = session.get(AgentIdentityRecord, agent_id)
            if record is None:
                return   # graceful — don't crash on counter update
            record.execution_counter += execution
            record.memory_counter    += memory
            record.artifact_counter  += artifact
            record.updated_at         = datetime.now(timezone.utc).isoformat()
            session.add(record)
            session.commit()

    def set_agent_sui_object(self, agent_id: str, sui_object_id: str) -> None:
        """Persist the on-chain Sui AgentIdentity object ID."""
        with Session(self._engine) as session:
            record = session.get(AgentIdentityRecord, agent_id)
            if record is None:
                raise KeyError(f"AgentIdentity '{agent_id}' not found")
            record.sui_object_id = sui_object_id
            record.updated_at    = datetime.now(timezone.utc).isoformat()
            session.add(record)
            session.commit()

    @staticmethod
    def _record_to_identity(record: AgentIdentityRecord):
        """Convert a SQLModel record to an AgentIdentity domain model."""
        from walrusos.core.models.agent_identity import AgentIdentity
        return AgentIdentity(
            agent_id=record.agent_id,
            workspace_id=record.workspace_id,
            agent_name=record.agent_name,
            owner_wallet=record.owner_wallet,
            public_key=record.public_key,
            trust_root=record.trust_root,
            status=record.status,
            capabilities=json.loads(record.capabilities_json),
            execution_counter=record.execution_counter,
            memory_counter=record.memory_counter,
            artifact_counter=record.artifact_counter,
            metadata=json.loads(record.metadata_json),
            sui_object_id=record.sui_object_id,
        )

    # ── AgentKey store / load (Phase 2) ──────────────────────────────────────

    def store_agent_private_key(
        self,
        agent_id: str,
        private_key_bytes: bytes,
        password: bytes,
    ) -> None:
        """
        Wrap and persist an agent's Ed25519 private key.

        Uses the same PBKDF2 KDF as the KeyStore so the wallet password
        implicitly protects every agent's signing key.
        """
        import os as _os
        from base64 import b64encode
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        salt   = _os.urandom(32)
        kdf    = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
        kek    = kdf.derive(password)
        nonce  = _os.urandom(12)
        ct     = AESGCM(kek).encrypt(nonce, private_key_bytes, None)

        with Session(self._engine) as session:
            existing = session.get(AgentKeyRecord, agent_id)
            if existing is not None:
                return   # never overwrite a key
            session.add(AgentKeyRecord(
                agent_id=agent_id,
                wrapped_key=b64encode(nonce + ct).decode(),
                kek_salt=b64encode(salt).decode(),
            ))
            session.commit()

    def load_agent_private_key(self, agent_id: str, password: bytes) -> Optional[bytes]:
        """
        Load and unwrap an agent's Ed25519 private key.

        Returns None if no key exists for this agent.
        Raises ValueError if decryption fails (wrong password).
        """
        from base64 import b64decode
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        with Session(self._engine) as session:
            record = session.get(AgentKeyRecord, agent_id)
            if record is None:
                return None

        salt    = b64decode(record.kek_salt)
        kdf     = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
        kek     = kdf.derive(password)
        data    = b64decode(record.wrapped_key)
        nonce, ct = data[:12], data[12:]
        return AESGCM(kek).decrypt(nonce, ct, None)

    # ── Workspace & Capability store / load (Phase 4) ─────────────────────────

    def save_workspace(self, workspace_id: str, sui_object_id: str, name: str = "", owner_wallet: str = "") -> None:
        with Session(self._engine) as session:
            existing = session.get(WorkspaceRecord, workspace_id)
            if existing is None:
                session.add(WorkspaceRecord(
                    workspace_id=workspace_id,
                    sui_object_id=sui_object_id,
                    name=name,
                    owner_wallet=owner_wallet,
                ))
            else:
                existing.sui_object_id = sui_object_id
                session.add(existing)
            session.commit()

    def get_workspace_sui_object(self, workspace_id: str) -> Optional[str]:
        with Session(self._engine) as session:
            record = session.get(WorkspaceRecord, workspace_id)
            return record.sui_object_id if record else None

    def save_capability(
        self,
        sui_object_id: str,
        target_stream_id: str,
        verb_bitmask: int = 15,
        valid_until_epoch: int = 0
    ) -> None:
        with Session(self._engine) as session:
            existing = session.get(CapabilityRecord, sui_object_id)
            if existing is None:
                session.add(CapabilityRecord(
                    sui_object_id=sui_object_id,
                    target_stream_id=target_stream_id,
                    verb_bitmask=verb_bitmask,
                    valid_until_epoch=valid_until_epoch,
                ))
            else:
                existing.verb_bitmask = verb_bitmask
                session.add(existing)
            session.commit()

    def get_capabilities_for_stream(self, target_stream_id: str) -> list[CapabilityRecord]:
        with Session(self._engine) as session:
            records = session.exec(
                select(CapabilityRecord)
                .where(CapabilityRecord.target_stream_id == target_stream_id)
            ).all()
            return list(records)

    # ── Task Store (Phase 2) ──────────────────────────────────────────────────

    def save_task(self, task: "Task") -> None:
        """Persist a Task model into SQLite."""
        import json
        with Session(self._engine) as session:
            existing = session.get(TaskRecord, task.task_id)
            if existing is None:
                record = TaskRecord(
                    task_id=task.task_id,
                    workspace_id=task.workspace_id,
                    title=task.title,
                    description=task.description,
                    created_by=task.created_by,
                    assigned_to=task.assigned_to,
                    status=task.status,
                    priority=task.priority,
                    parent_task_id=task.parent_task_id,
                    subtask_ids=json.dumps(task.subtask_ids),
                    memory_refs=json.dumps(task.memory_refs),
                    artifact_refs=json.dumps(task.artifact_refs),
                    tags=json.dumps(task.tags),
                    created_at=task.created_at.isoformat(),
                    updated_at=task.updated_at.isoformat(),
                    completed_at=task.completed_at.isoformat() if task.completed_at else None,
                    notes=task.notes,
                )
                session.add(record)
            else:
                existing.title = task.title
                existing.description = task.description
                existing.assigned_to = task.assigned_to
                existing.status = task.status
                existing.priority = task.priority
                existing.subtask_ids = json.dumps(task.subtask_ids)
                existing.memory_refs = json.dumps(task.memory_refs)
                existing.artifact_refs = json.dumps(task.artifact_refs)
                existing.tags = json.dumps(task.tags)
                existing.updated_at = task.updated_at.isoformat()
                existing.completed_at = task.completed_at.isoformat() if task.completed_at else None
                existing.notes = task.notes
                session.add(existing)
            session.commit()

    def get_task(self, task_id: str) -> Optional["Task"]:
        from walrusos.core.models.task import Task
        import json
        from datetime import datetime
        with Session(self._engine) as session:
            record = session.get(TaskRecord, task_id)
            if not record:
                return None
            return Task(
                task_id=record.task_id,
                workspace_id=record.workspace_id,
                title=record.title,
                description=record.description,
                created_by=record.created_by,
                assigned_to=record.assigned_to,
                status=record.status,  # type: ignore
                priority=record.priority,
                parent_task_id=record.parent_task_id,
                subtask_ids=json.loads(record.subtask_ids),
                memory_refs=json.loads(record.memory_refs),
                artifact_refs=json.loads(record.artifact_refs),
                tags=json.loads(record.tags),
                created_at=datetime.fromisoformat(record.created_at),
                updated_at=datetime.fromisoformat(record.updated_at),
                completed_at=datetime.fromisoformat(record.completed_at) if record.completed_at else None,
                notes=record.notes,
            )

    def list_tasks(self, workspace_id: str, status: Optional[str] = None, assigned_to: Optional[str] = None, tag: Optional[str] = None) -> List["Task"]:
        from sqlmodel import select
        with Session(self._engine) as session:
            stmt = select(TaskRecord).where(TaskRecord.workspace_id == workspace_id)
            if status:
                stmt = stmt.where(TaskRecord.status == status)
            if assigned_to:
                stmt = stmt.where(TaskRecord.assigned_to == assigned_to)
            if tag:
                stmt = stmt.where(TaskRecord.tags.like(f'%"{tag}"%')) # type: ignore
            
            records = session.exec(stmt).all()
            
        tasks = []
        for r in records:
            t = self.get_task(r.task_id)
            if t:
                tasks.append(t)
        return tasks
