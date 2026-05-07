"""Append-only event store for Nexusctl mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Iterable
from uuid import uuid4

GENESIS_EVENT_HASH = "0" * 64


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _row_value(row: sqlite3.Row, key: str, default: str | None = None) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


@dataclass(frozen=True, slots=True)
class EventIntegrityReport:
    """Result of verifying the persisted event hash chain."""

    valid: bool
    checked_events: int
    first_error: str | None = None
    last_event_hash: str | None = None


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    actor_id: str | None
    payload: dict[str, Any]
    metadata: dict[str, Any]
    occurred_at: str
    prev_hash: str
    event_hash: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "EventRecord":
        return cls(
            event_id=row["event_id"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            payload=json.loads(row["payload_json"] or "{}"),
            metadata=json.loads(row["metadata_json"] or "{}"),
            occurred_at=row["occurred_at"],
            prev_hash=_row_value(row, "prev_hash", GENESIS_EVENT_HASH) or GENESIS_EVENT_HASH,
            event_hash=_row_value(row, "event_hash", "") or "",
        )


def canonical_event_content(
    *,
    event_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    actor_id: str | None,
    payload_json: str,
    metadata_json: str,
    occurred_at: str,
) -> str:
    """Return the deterministic content representation protected by the chain."""

    return _json_dumps(
        {
            "event_id": event_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "payload": json.loads(payload_json or "{}"),
            "metadata": json.loads(metadata_json or "{}"),
            "occurred_at": occurred_at,
        }
    )


def compute_event_hash(*, prev_hash: str, canonical_content: str) -> str:
    """Hash one event from the previous chain hash and canonical content."""

    material = _json_dumps({"prev_hash": prev_hash, "event": json.loads(canonical_content)})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def compute_hash_for_row(row: sqlite3.Row | dict[str, Any], *, prev_hash: str) -> str:
    """Compute the expected event hash for a database row-like mapping."""

    canonical = canonical_event_content(
        event_id=row["event_id"],
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        event_type=row["event_type"],
        actor_id=row["actor_id"],
        payload_json=row["payload_json"],
        metadata_json=row["metadata_json"],
        occurred_at=row["occurred_at"],
    )
    return compute_event_hash(prev_hash=prev_hash, canonical_content=canonical)


class EventStore:
    """Small append-only facade over the ``events`` table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def append(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        actor_id: str | None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
    ) -> EventRecord:
        """Append a single event and return the persisted record."""

        payload_value = dict(payload or {})
        metadata_value = dict(metadata or {})
        payload_json = _json_dumps(payload_value)
        metadata_json = _json_dumps(metadata_value)
        prev_hash = self._last_event_hash()
        record_id = event_id or f"evt-{uuid4().hex}"
        record_occurred_at = occurred_at or _utcnow_iso()
        event_hash = compute_event_hash(
            prev_hash=prev_hash,
            canonical_content=canonical_event_content(
                event_id=record_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                actor_id=actor_id,
                payload_json=payload_json,
                metadata_json=metadata_json,
                occurred_at=record_occurred_at,
            ),
        )
        record = EventRecord(
            event_id=record_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload_value,
            metadata=metadata_value,
            occurred_at=record_occurred_at,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )
        self.connection.execute(
            """
            INSERT INTO events(
              event_id, aggregate_type, aggregate_id, event_type, actor_id,
              payload_json, metadata_json, occurred_at, prev_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.event_id,
                record.aggregate_type,
                record.aggregate_id,
                record.event_type,
                record.actor_id,
                payload_json,
                metadata_json,
                record.occurred_at,
                record.prev_hash,
                record.event_hash,
            ),
        )
        return record

    def list_for_aggregate(self, aggregate_type: str, aggregate_id: str) -> list[EventRecord]:
        rows = self.connection.execute(
            """
            SELECT * FROM events
            WHERE aggregate_type = ? AND aggregate_id = ?
            ORDER BY id ASC
            """,
            (aggregate_type, aggregate_id),
        ).fetchall()
        return [EventRecord.from_row(row) for row in rows]

    def list_recent(self, *, limit: int = 50) -> list[EventRecord]:
        rows = self.connection.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [EventRecord.from_row(row) for row in rows]

    def append_many(self, events: Iterable[dict[str, Any]]) -> list[EventRecord]:
        """Append several events in call order."""

        return [self.append(**event) for event in events]

    def verify_integrity(self) -> EventIntegrityReport:
        """Verify that every persisted event matches the deterministic hash chain."""

        rows = self.connection.execute("SELECT * FROM events ORDER BY id ASC").fetchall()
        previous = GENESIS_EVENT_HASH
        checked = 0
        for row in rows:
            checked += 1
            stored_prev = row["prev_hash"]
            stored_hash = row["event_hash"]
            if stored_prev != previous:
                return EventIntegrityReport(
                    valid=False,
                    checked_events=checked,
                    first_error=f"event {row['event_id']} prev_hash mismatch",
                    last_event_hash=previous,
                )
            expected_hash = compute_hash_for_row(row, prev_hash=previous)
            if stored_hash != expected_hash:
                return EventIntegrityReport(
                    valid=False,
                    checked_events=checked,
                    first_error=f"event {row['event_id']} event_hash mismatch",
                    last_event_hash=previous,
                )
            previous = stored_hash
        return EventIntegrityReport(valid=True, checked_events=checked, last_event_hash=previous)

    def _last_event_hash(self) -> str:
        row = self.connection.execute("SELECT event_hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
        return (row["event_hash"] if row is not None else None) or GENESIS_EVENT_HASH
