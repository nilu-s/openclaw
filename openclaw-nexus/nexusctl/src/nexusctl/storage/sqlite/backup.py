"""SQLite backup and restore helpers for internal Nexus operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from uuid import uuid4

from nexusctl.domain.errors import ValidationError
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import MIGRATIONS, applied_versions, apply_migrations


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _default_backup_path(source: Path) -> Path:
    base = source.name
    if source.suffix:
        base = source.name[: -len(source.suffix)]
    return source.with_name(f"{base}.{_utc_stamp()}.backup.sqlite3")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class BackupResult:
    ok: bool
    source_db: str
    backup_path: str
    size_bytes: int
    checksum: str
    checked_events: int
    schema_version: int

    def to_json(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "source_db": self.source_db,
            "backup_path": self.backup_path,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "checked_events": self.checked_events,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class RestoreCheckResult:
    ok: bool
    backup_path: str
    size_bytes: int
    checksum: str
    checked_events: int
    schema_version: int
    latest_schema_version: int
    counts: dict[str, int]

    def to_json(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "backup_path": self.backup_path,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "checked_events": self.checked_events,
            "schema_version": self.schema_version,
            "latest_schema_version": self.latest_schema_version,
            "counts": self.counts,
        }


@dataclass(frozen=True, slots=True)
class RestoreResult:
    ok: bool
    backup_path: str
    restored_db: str
    checked_events: int
    schema_version: int
    counts: dict[str, int]

    def to_json(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "backup_path": self.backup_path,
            "restored_db": self.restored_db,
            "checked_events": self.checked_events,
            "schema_version": self.schema_version,
            "counts": self.counts,
        }


def create_sqlite_backup(
    connection: sqlite3.Connection,
    *,
    source_db_path: str | Path,
    backup_path: str | Path | None = None,
    actor_id: str | None = None,
) -> BackupResult:
    """Create an online SQLite backup from an open source connection.

    The SQLite backup API is used instead of a raw file copy so callers can run
    it while the source database is open. The resulting snapshot is immediately
    opened and verified, including the Nexus event hash chain.
    """

    source = Path(source_db_path)
    target = Path(backup_path) if backup_path is not None else _default_backup_path(source)
    if target.exists():
        raise ValidationError(f"backup target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target) as destination:
        connection.backup(destination)

    try:
        check = check_sqlite_backup(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    checksum = check.checksum
    size_bytes = check.size_bytes
    backup_id = f"backup-{uuid4().hex}"
    connection.execute(
        """
        INSERT INTO backups(id, path, status, created_by, size_bytes, checksum)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (backup_id, str(target), "created", actor_id, size_bytes, checksum),
    )
    EventStore(connection).append(
        aggregate_type="database",
        aggregate_id="nexus",
        event_type="database.backup.created",
        actor_id=actor_id,
        payload={"backup_path": str(target), "size_bytes": size_bytes, "checksum": checksum},
        metadata={"source_db": str(source)},
    )
    return BackupResult(
        ok=True,
        source_db=str(source),
        backup_path=str(target),
        size_bytes=size_bytes,
        checksum=checksum,
        checked_events=check.checked_events,
        schema_version=check.schema_version,
    )


def check_sqlite_backup(backup_path: str | Path) -> RestoreCheckResult:
    """Validate a backup database without mutating it."""

    backup = Path(backup_path)
    if not backup.is_file():
        raise ValidationError(f"backup not found: {backup}")
    size_bytes = backup.stat().st_size
    if size_bytes <= 0:
        raise ValidationError(f"backup is empty: {backup}")

    connection = connect_database(backup, read_only=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValidationError(f"backup integrity check failed: {integrity}")
        versions = applied_versions(connection)
        latest = max(m.version for m in MIGRATIONS)
        schema_version = max(versions) if versions else 0
        if schema_version < latest:
            raise ValidationError(f"backup schema version {schema_version} is older than required {latest}")
        event_report = EventStore(connection).verify_integrity()
        if not event_report.valid:
            raise ValidationError(f"backup event chain invalid: {event_report.first_error}")
        counts = _core_counts(connection)
    finally:
        connection.close()

    return RestoreCheckResult(
        ok=True,
        backup_path=str(backup),
        size_bytes=size_bytes,
        checksum=_sha256_file(backup),
        checked_events=event_report.checked_events,
        schema_version=schema_version,
        latest_schema_version=latest,
        counts=counts,
    )


def restore_sqlite_backup(
    *,
    backup_path: str | Path,
    target_db_path: str | Path,
    overwrite: bool = False,
) -> RestoreResult:
    """Restore a verified backup into a local SQLite database path."""

    backup = Path(backup_path)
    target = Path(target_db_path)
    check = check_sqlite_backup(backup)
    if target.exists() and not overwrite:
        raise ValidationError(f"restore target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    source = connect_database(backup, read_only=True)
    try:
        with sqlite3.connect(target) as destination:
            source.backup(destination)
    finally:
        source.close()

    restored = connect_database(target)
    try:
        apply_migrations(restored)
        restored_check = EventStore(restored).verify_integrity()
        if not restored_check.valid:
            raise ValidationError(f"restored event chain invalid: {restored_check.first_error}")
        counts = _core_counts(restored)
        versions = applied_versions(restored)
        schema_version = max(versions) if versions else 0
        restored.commit()
    except Exception:
        restored.rollback()
        raise
    finally:
        restored.close()

    return RestoreResult(
        ok=True,
        backup_path=str(backup),
        restored_db=str(target),
        checked_events=restored_check.checked_events,
        schema_version=schema_version,
        counts=counts or check.counts,
    )


def _core_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = ("domains", "agents", "capabilities", "goals", "feature_requests", "work_items", "events", "backups")
    counts: dict[str, int] = {}
    for table in tables:
        try:
            counts[table] = int(connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
        except sqlite3.Error:
            counts[table] = 0
    return counts
