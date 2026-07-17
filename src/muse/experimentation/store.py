from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from muse.experimentation.events import PendingEvent, SessionEvent, reduce_events
from muse.models import FrozenModel


class SequenceConflict(RuntimeError):
    """Raised when an append does not extend the expected event sequence."""


class SessionNotFound(LookupError):
    """Raised when an event stream does not exist for a session."""


class EventStore(Protocol):
    def append(
        self,
        session_id: UUID,
        expected_sequence: int,
        pending: tuple[PendingEvent, ...],
    ) -> tuple[SessionEvent, ...]: ...

    def load(
        self,
        session_id: UUID,
        after_sequence: int = 0,
    ) -> tuple[SessionEvent, ...]: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  current_sequence INTEGER NOT NULL,
  current_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_events (
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  sequence INTEGER NOT NULL,
  kind TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  occurred_at TEXT NOT NULL,
  previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  UNIQUE(session_id, sequence),
  UNIQUE(session_id, idempotency_key)
);
"""


class SQLiteEventStore:
    """Transactional SQLite persistence for validated creative-session streams.

    SQLite stores the first event's ``None`` previous hash as the empty string so
    the durable column can remain ``NOT NULL``. It is converted back to ``None``
    before ``SessionEvent`` validation.
    """

    def __init__(self, database: str | Path) -> None:
        self._database = Path(database)
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def append(
        self,
        session_id: UUID,
        expected_sequence: int,
        pending: tuple[PendingEvent, ...],
    ) -> tuple[SessionEvent, ...]:
        _require_sequence(expected_sequence, name="expected_sequence")
        if not pending:
            raise ValueError("pending events must not be empty")
        keys = tuple(event.idempotency_key for event in pending)
        if len(set(keys)) != len(keys):
            raise SequenceConflict("pending events contain a duplicate idempotency key")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            session_row = connection.execute(
                """
                SELECT current_sequence, current_hash
                FROM sessions
                WHERE session_id = ?
                """,
                (str(session_id),),
            ).fetchone()
            existing = self._load_rows(connection, session_id)
            current_sequence = 0 if session_row is None else int(session_row["current_sequence"])
            current_hash = None if session_row is None else str(session_row["current_hash"])
            self._validate_existing_stream(
                session_id,
                existing,
                current_sequence=current_sequence,
                current_hash=current_hash,
            )

            by_key = {event.idempotency_key: event for event in existing}
            reused = tuple(by_key.get(key) for key in keys)
            if any(event is not None for event in reused):
                if self._is_exact_retry(expected_sequence, pending, reused):
                    connection.commit()
                    return tuple(event for event in reused if event is not None)
                raise SequenceConflict("idempotency key reuse conflicts with persisted events")

            if current_sequence != expected_sequence:
                raise SequenceConflict(
                    f"expected sequence {expected_sequence}, found {current_sequence}"
                )

            created = self._build_events(
                session_id,
                expected_sequence,
                pending,
                previous_hash=current_hash,
            )
            reduce_events((*existing, *created))

            now = _canonical_timestamp(datetime.now(UTC))
            if session_row is None:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, current_sequence, current_hash, created_at, updated_at
                    ) VALUES (?, 0, '', ?, ?)
                    """,
                    (str(session_id), now, now),
                )
            connection.executemany(
                """
                INSERT INTO session_events (
                    event_id,
                    session_id,
                    sequence,
                    kind,
                    schema_version,
                    occurred_at,
                    previous_hash,
                    event_hash,
                    payload_json,
                    idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(_event_record(event) for event in created),
            )
            last = created[-1]
            connection.execute(
                """
                UPDATE sessions
                SET current_sequence = ?, current_hash = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (last.sequence, last.event_hash, now, str(session_id)),
            )
            connection.commit()
            return created
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load(
        self,
        session_id: UUID,
        after_sequence: int = 0,
    ) -> tuple[SessionEvent, ...]:
        _require_sequence(after_sequence, name="after_sequence")
        with self._connect() as connection:
            session_row = connection.execute(
                """
                SELECT current_sequence, current_hash
                FROM sessions
                WHERE session_id = ?
                """,
                (str(session_id),),
            ).fetchone()
            if session_row is None:
                raise SessionNotFound(f"session not found: {session_id}")
            events = self._load_rows(connection, session_id)
            self._validate_existing_stream(
                session_id,
                events,
                current_sequence=int(session_row["current_sequence"]),
                current_hash=str(session_row["current_hash"]),
            )
        return tuple(event for event in events if event.sequence > after_sequence)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _load_rows(
        connection: sqlite3.Connection,
        session_id: UUID,
    ) -> tuple[SessionEvent, ...]:
        rows = connection.execute(
            """
            SELECT
                event_id,
                session_id,
                sequence,
                kind,
                schema_version,
                occurred_at,
                previous_hash,
                event_hash,
                payload_json,
                idempotency_key
            FROM session_events
            WHERE session_id = ?
            ORDER BY sequence ASC
            """,
            (str(session_id),),
        ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    @staticmethod
    def _validate_existing_stream(
        session_id: UUID,
        events: tuple[SessionEvent, ...],
        *,
        current_sequence: int,
        current_hash: str | None,
    ) -> None:
        if not events:
            if current_sequence != 0 or current_hash not in {None, ""}:
                raise ValueError("session metadata does not match its event stream")
            return
        reduce_events(events)
        last = events[-1]
        if last.session_id != session_id:
            raise ValueError("loaded event stream contains a different session ID")
        if current_sequence != last.sequence or current_hash != last.event_hash:
            raise ValueError("session metadata does not match its event stream")

    @staticmethod
    def _is_exact_retry(
        expected_sequence: int,
        pending: tuple[PendingEvent, ...],
        reused: tuple[SessionEvent | None, ...],
    ) -> bool:
        if any(event is None for event in reused):
            return False
        for offset, (requested, persisted) in enumerate(zip(pending, reused, strict=True), 1):
            if persisted is None:
                return False
            if persisted.sequence != expected_sequence + offset:
                return False
            if persisted.kind is not requested.kind:
                return False
            if _canonical_payload(persisted.payload) != _canonical_payload(requested.payload):
                return False
        return True

    @staticmethod
    def _build_events(
        session_id: UUID,
        expected_sequence: int,
        pending: Sequence[PendingEvent],
        *,
        previous_hash: str | None,
    ) -> tuple[SessionEvent, ...]:
        created: list[SessionEvent] = []
        next_previous_hash = previous_hash
        for offset, event in enumerate(pending, 1):
            persisted = SessionEvent.create(
                session_id,
                expected_sequence + offset,
                event.kind,
                event.payload,
                idempotency_key=event.idempotency_key,
                previous_event_hash=next_previous_hash,
            )
            created.append(persisted)
            next_previous_hash = persisted.event_hash
        return tuple(created)


def _require_sequence(value: int, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _canonical_payload(payload: FrozenModel) -> str:
    return json.dumps(
        payload.model_dump(mode="json"),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _event_record(event: SessionEvent) -> tuple[object, ...]:
    return (
        str(event.event_id),
        str(event.session_id),
        event.sequence,
        event.kind.value,
        event.schema_version,
        _canonical_timestamp(event.timestamp),
        "" if event.previous_event_hash is None else event.previous_event_hash,
        event.event_hash,
        _canonical_payload(event.payload),
        event.idempotency_key,
    )


def _event_from_row(row: sqlite3.Row) -> SessionEvent:
    previous_hash = str(row["previous_hash"])
    return SessionEvent.model_validate(
        {
            "event_id": row["event_id"],
            "session_id": row["session_id"],
            "sequence": row["sequence"],
            "kind": row["kind"],
            "schema_version": row["schema_version"],
            "timestamp": row["occurred_at"],
            "previous_event_hash": None if previous_hash == "" else previous_hash,
            "event_hash": row["event_hash"],
            "payload": json.loads(row["payload_json"]),
            "idempotency_key": row["idempotency_key"],
        }
    )
