from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import TracebackType
from uuid import UUID

import pytest

import muse.experimentation.store as store_module
from muse.experimentation.events import (
    EventKind,
    PendingEvent,
    SessionStatusChange,
)
from muse.experimentation.sessions import (
    AuthorizationPolicy,
    CreativeSession,
    Objective,
    PrivacyPolicy,
    SessionBudgets,
    SessionStatus,
)
from muse.experimentation.store import (
    SequenceConflict,
    SessionNotFound,
    SQLiteEventStore,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")


class _TrackedConnection(sqlite3.Connection):
    fail_configuration = False
    lifecycle: list[str]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.lifecycle = []

    def commit(self) -> None:
        self.lifecycle.append("commit")
        super().commit()

    def rollback(self) -> None:
        self.lifecycle.append("rollback")
        super().rollback()

    def execute(self, sql: str, parameters: object = (), /) -> sqlite3.Cursor:
        if self.fail_configuration and "journal_mode" in sql:
            raise sqlite3.OperationalError("simulated connection configuration failure")
        return super().execute(sql, parameters)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        result = super().__exit__(exc_type, exc_value, traceback)
        self.lifecycle.append("rollback" if exc_type is not None else "commit")
        return result

    def close(self) -> None:
        self.lifecycle.append("close")
        super().close()


def _track_connections(monkeypatch: pytest.MonkeyPatch) -> list[_TrackedConnection]:
    original_connect = sqlite3.connect
    tracked: list[_TrackedConnection] = []

    def connect(*args: object, **kwargs: object) -> _TrackedConnection:
        kwargs["factory"] = _TrackedConnection
        connection = original_connect(*args, **kwargs)
        assert isinstance(connection, _TrackedConnection)
        tracked.append(connection)
        return connection

    monkeypatch.setattr(store_module.sqlite3, "connect", connect)
    return tracked


def _session() -> CreativeSession:
    return CreativeSession(
        id=SESSION_ID,
        goal="Design a safer coordination mechanism",
        objectives=(Objective(name="usefulness", direction="maximize", priority=1),),
        privacy=PrivacyPolicy(mode="private", retention_days=30),
        authorization=AuthorizationPolicy(),
        budgets=SessionBudgets(
            max_cost_usd=1.0,
            max_provider_calls=10,
            max_latency_ms=60_000,
            max_human_minutes=5,
        ),
        schema_version=1,
        policy_version="evidence-v1",
    )


def _started(*, key: str = "start") -> PendingEvent:
    return PendingEvent(
        kind=EventKind.SESSION_STARTED,
        payload=_session(),
        idempotency_key=key,
    )


def _status_changed(*, key: str = "status") -> PendingEvent:
    return PendingEvent(
        kind=EventKind.SESSION_STATUS_CHANGED,
        payload=SessionStatusChange(
            session_id=SESSION_ID,
            status=SessionStatus.CONCLUDED,
            reason="The decision rule resolved the uncertainty",
        ),
        idempotency_key=key,
    )


def test_constructor_closes_its_schema_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracked = _track_connections(monkeypatch)

    SQLiteEventStore(tmp_path / "muse.db")

    assert len(tracked) == 1
    assert tracked[0].lifecycle[-2:] == ["commit", "close"]


def test_connection_configuration_error_closes_without_changing_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracked = _track_connections(monkeypatch)
    monkeypatch.setattr(_TrackedConnection, "fail_configuration", True)

    with pytest.raises(sqlite3.OperationalError, match="configuration failure"):
        SQLiteEventStore(tmp_path / "muse.db")

    assert tracked[0].lifecycle == ["close"]


def test_load_success_closes_its_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    store.append(SESSION_ID, 0, (_started(),))
    tracked = _track_connections(monkeypatch)

    assert store.load(SESSION_ID)[0].sequence == 1

    assert len(tracked) == 1
    assert tracked[0].lifecycle[-2:] == ["commit", "close"]


def test_load_session_not_found_rolls_back_then_closes_without_changing_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    tracked = _track_connections(monkeypatch)

    with pytest.raises(SessionNotFound, match=str(SESSION_ID)):
        store.load(SESSION_ID)

    assert tracked[0].lifecycle[-2:] == ["rollback", "close"]


def test_load_validation_error_rolls_back_then_closes_without_changing_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "muse.db"
    store = SQLiteEventStore(database)
    store.append(SESSION_ID, 0, (_started(),))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE session_events SET event_hash = ? WHERE session_id = ?",
            ("f" * 64, str(SESSION_ID)),
        )
    tracked = _track_connections(monkeypatch)

    with pytest.raises(ValueError, match="event hash"):
        store.load(SESSION_ID)

    assert tracked[0].lifecycle[-2:] == ["rollback", "close"]


def test_append_success_commits_then_closes_its_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    tracked = _track_connections(monkeypatch)

    store.append(SESSION_ID, 0, (_started(),))

    assert tracked[0].lifecycle[-2:] == ["commit", "close"]


def test_append_conflict_rolls_back_then_closes_without_changing_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    store.append(SESSION_ID, 0, (_started(),))
    tracked = _track_connections(monkeypatch)

    with pytest.raises(SequenceConflict, match="expected sequence 0"):
        store.append(SESSION_ID, 0, (_status_changed(),))

    assert tracked[0].lifecycle[-2:] == ["rollback", "close"]


def test_append_validation_error_rolls_back_then_closes_without_changing_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    tracked = _track_connections(monkeypatch)

    with pytest.raises(ValueError, match="only be started once"):
        store.append(SESSION_ID, 0, (_started(key="first"), _started(key="second")))

    assert tracked[0].lifecycle[-2:] == ["rollback", "close"]


def test_database_can_be_removed_and_reopened_immediately_after_use(tmp_path: Path) -> None:
    database = tmp_path / "muse.db"
    store = SQLiteEventStore(database)
    store.append(SESSION_ID, 0, (_started(),))
    store.load(SESSION_ID)

    database.unlink()
    SQLiteEventStore(database)

    assert database.exists()


def test_sqlite_store_creates_durable_schema_and_pragmas(tmp_path: Path) -> None:
    database = tmp_path / "muse.db"
    SQLiteEventStore(database)

    with sqlite3.connect(database) as connection:
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        event_columns = {
            row[1]: row[3] for row in connection.execute("PRAGMA table_info(session_events)")
        }

    assert {"sessions", "session_events"} <= table_names
    assert journal_mode == "wal"
    assert event_columns["previous_hash"] == 1


def test_sqlite_store_reopens_and_loads_canonical_events_in_order(
    tmp_path: Path,
) -> None:
    database = tmp_path / "muse.db"
    store = SQLiteEventStore(database)
    written = store.append(SESSION_ID, 0, (_started(), _status_changed()))

    restored = SQLiteEventStore(database).load(SESSION_ID)

    assert restored == written
    assert tuple(event.sequence for event in restored) == (1, 2)
    assert restored[0].previous_event_hash is None
    assert restored[1].previous_event_hash == restored[0].event_hash
    with sqlite3.connect(database) as connection:
        first_previous_hash = connection.execute(
            "SELECT previous_hash FROM session_events WHERE sequence = 1"
        ).fetchone()[0]
        payload_json = connection.execute(
            "SELECT payload_json FROM session_events WHERE sequence = 1"
        ).fetchone()[0]
    assert first_previous_hash == ""
    assert payload_json == json.dumps(
        _session().model_dump(mode="json"),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def test_sqlite_store_rejects_reducer_invalid_batch_without_partial_write(
    tmp_path: Path,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")

    with pytest.raises(ValueError, match="only be started once"):
        store.append(SESSION_ID, 0, (_started(key="first"), _started(key="second")))

    with pytest.raises(SessionNotFound):
        store.load(SESSION_ID)


def test_sqlite_store_rolls_back_the_whole_batch_on_insert_failure(tmp_path: Path) -> None:
    database = tmp_path / "muse.db"
    store = SQLiteEventStore(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_second_event
            BEFORE INSERT ON session_events
            WHEN NEW.sequence = 2
            BEGIN
                SELECT RAISE(ABORT, 'simulated crash');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="simulated crash"):
        store.append(SESSION_ID, 0, (_started(), _status_changed()))

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM session_events").fetchone()[0] == 0


def test_sqlite_store_rejects_stale_sequence_without_partial_write(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    store.append(SESSION_ID, 0, (_started(),))

    with pytest.raises(SequenceConflict, match="expected sequence 0"):
        store.append(SESSION_ID, 0, (_status_changed(),))

    assert len(store.load(SESSION_ID)) == 1


def test_sqlite_store_returns_original_events_for_an_exact_batch_retry(
    tmp_path: Path,
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    pending = (_started(), _status_changed())
    original = store.append(SESSION_ID, 0, pending)

    retried = store.append(SESSION_ID, 0, pending)

    assert retried == original
    assert store.load(SESSION_ID) == original


def test_sqlite_store_returns_sequence_aligned_exact_partial_retry(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    original = store.append(SESSION_ID, 0, (_started(), _status_changed()))

    assert store.append(SESSION_ID, 0, (_started(),)) == (original[0],)
    assert store.load(SESSION_ID) == original


@pytest.mark.parametrize(
    "retry",
    [
        (_started(), _status_changed(key="replacement-key")),
        (
            _started(),
            PendingEvent(
                kind=EventKind.SESSION_STATUS_CHANGED,
                payload=SessionStatusChange(
                    session_id=SESSION_ID,
                    status=SessionStatus.CONCLUDED,
                    reason="Conflicting logical payload",
                ),
                idempotency_key="status",
            ),
        ),
    ],
    ids=("mixed-existing-and-new", "conflicting-payload"),
)
def test_sqlite_store_rejects_non_pure_idempotency_reuse_atomically(
    tmp_path: Path,
    retry: tuple[PendingEvent, ...],
) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    original = store.append(SESSION_ID, 0, (_started(), _status_changed()))

    with pytest.raises(SequenceConflict):
        store.append(SESSION_ID, 0, retry)

    assert store.load(SESSION_ID) == original


def test_independent_connections_allow_only_one_stale_writer_to_commit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "muse.db"
    first = SQLiteEventStore(database)
    second = SQLiteEventStore(database)
    barrier = Barrier(2)

    def append(store: SQLiteEventStore, key: str) -> object:
        barrier.wait()
        try:
            return store.append(SESSION_ID, 0, (_started(key=key),))
        except SequenceConflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            future.result()
            for future in (
                executor.submit(append, first, "writer-one"),
                executor.submit(append, second, "writer-two"),
            )
        )

    assert sum(isinstance(result, tuple) for result in results) == 1
    assert sum(isinstance(result, SequenceConflict) for result in results) == 1
    assert len(SQLiteEventStore(database).load(SESSION_ID)) == 1


def test_load_filters_after_sequence_and_validates_its_boundary(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")
    written = store.append(SESSION_ID, 0, (_started(), _status_changed()))

    assert store.load(SESSION_ID, after_sequence=1) == (written[1],)
    assert store.load(SESSION_ID, after_sequence=2) == ()
    with pytest.raises(ValueError, match="non-negative integer"):
        store.load(SESSION_ID, after_sequence=-1)
    with pytest.raises(ValueError, match="non-negative integer"):
        store.load(SESSION_ID, after_sequence=True)


def test_load_raises_for_an_unknown_session(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "muse.db")

    with pytest.raises(SessionNotFound, match=str(SESSION_ID)):
        store.load(SESSION_ID)


def test_load_detects_corrupted_payload_json(tmp_path: Path) -> None:
    database = tmp_path / "muse.db"
    store = SQLiteEventStore(database)
    store.append(SESSION_ID, 0, (_started(),))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE session_events SET payload_json = ? WHERE session_id = ?",
            ('{"goal":"tampered"}', str(SESSION_ID)),
        )

    with pytest.raises(ValueError):
        SQLiteEventStore(database).load(SESSION_ID)


def test_append_replays_existing_stream_before_committing(tmp_path: Path) -> None:
    database = tmp_path / "muse.db"
    store = SQLiteEventStore(database)
    store.append(SESSION_ID, 0, (_started(),))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE session_events SET event_hash = ? WHERE session_id = ?",
            ("f" * 64, str(SESSION_ID)),
        )

    with pytest.raises(ValueError, match="event hash"):
        store.append(SESSION_ID, 1, (_status_changed(),))

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM session_events").fetchone()[0] == 1
