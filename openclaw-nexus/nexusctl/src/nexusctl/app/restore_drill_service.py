"""Application service for local backup/restore recovery drills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.app.backup_service import BackupService
from nexusctl.app.recovery_evidence import RecoveryEvidenceBuilder
from nexusctl.app.generation_service import GenerationService
from nexusctl.storage.sqlite.backup import restore_sqlite_backup
from nexusctl.storage.sqlite.connection import connect_database


@dataclass(frozen=True, slots=True)
class RestoreDrillResult:
    """Machine-readable result of a local restore drill."""

    ok: bool
    backup_path: str
    restored_db: str
    checked_events: int
    schema_version: int
    counts: dict[str, int]
    doctor_status: str
    failed_checks: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "backup_path": self.backup_path,
            "restored_db": self.restored_db,
            "checked_events": self.checked_events,
            "schema_version": self.schema_version,
            "counts": self.counts,
            "doctor_status": self.doctor_status,
            "failed_checks": self.failed_checks,
        }


class RestoreDrillService:
    """Run a bounded local recovery drill without overwriting existing databases."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        source_db_path: str | Path,
        project_root: str | Path,
    ) -> None:
        self.connection = connection
        self.source_db_path = Path(source_db_path)
        self.project_root = Path(project_root)

    def run(
        self,
        *,
        backup_dir: str | Path | None = None,
        backup_path: str | Path | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or reuse a backup, restore it into a fresh DB, then run doctor.

        The restored database path is always newly generated. Callers cannot pass
        an overwrite target, which keeps the drill safe for production-adjacent
        operation and makes the report deterministic enough for automation.
        """

        working_dir = Path(backup_dir) if backup_dir is not None else self.source_db_path.with_name("restore-drills")
        if backup_path is not None and backup_dir is None:
            working_dir = Path(backup_path).parent
        working_dir.mkdir(parents=True, exist_ok=True)

        if backup_path is None:
            backup_target = working_dir / f"{self.source_db_path.stem}.restore-drill.{uuid4().hex}.backup.sqlite3"
            backup_payload = BackupService(self.connection, db_path=self.source_db_path).create(
                backup_path=backup_target,
                actor_id=actor_id,
            )
            backup_for_restore = Path(str(backup_payload["backup_path"]))
        else:
            backup_for_restore = Path(backup_path)

        restored_db = working_dir / f"{self.source_db_path.stem}.restore-drill.{uuid4().hex}.restored.sqlite3"
        restore = restore_sqlite_backup(backup_path=backup_for_restore, target_db_path=restored_db)

        restored_connection = connect_database(restored_db)
        try:
            doctor = GenerationService(self.project_root, connection=restored_connection).doctor()
        finally:
            restored_connection.rollback()
            restored_connection.close()

        failed_checks = self._failed_checks(doctor)
        result = RestoreDrillResult(
            ok=bool(restore.ok and doctor.get("ok")),
            backup_path=str(backup_for_restore),
            restored_db=str(restored_db),
            checked_events=restore.checked_events,
            schema_version=restore.schema_version,
            counts=restore.counts,
            doctor_status=str(doctor.get("status_code", "unknown")),
            failed_checks=failed_checks,
        )
        payload = result.to_json()
        payload["recovery_evidence"] = RecoveryEvidenceBuilder.from_restore_drill(
            source_db=self.source_db_path,
            restore_drill=payload,
        ).to_json()
        return payload

    def _failed_checks(self, doctor: dict[str, Any]) -> list[dict[str, Any]]:
        failed: list[dict[str, Any]] = []
        for item in doctor.get("drift", []):
            failed.append(
                {
                    "kind": "generated_artifact",
                    "status_code": item.get("status_code", "drift"),
                    "summary": item.get("path") or item.get("reason") or "generated artifact drift",
                }
            )
        for item in doctor.get("operational_warnings", []):
            failed.append(
                {
                    "kind": "operational_readiness",
                    "status_code": item.get("status_code", "warning"),
                    "summary": item.get("summary", "operational warning"),
                    "severity": item.get("severity"),
                }
            )
        event_integrity = doctor.get("event_integrity", {})
        if event_integrity and event_integrity.get("status_code") != "ok":
            failed.append(
                {
                    "kind": "event_integrity",
                    "status_code": event_integrity.get("status_code", "invalid"),
                    "summary": event_integrity.get("first_error") or "event chain integrity failed",
                }
            )
        database = doctor.get("database", {})
        if database and database.get("status_code") != "ok":
            failed.append(
                {
                    "kind": "database",
                    "status_code": database.get("status_code", "invalid"),
                    "summary": database.get("summary") or "database check failed",
                }
            )
        for alert in doctor.get("alerts", []):
            failed.append(
                {
                    "kind": "alert",
                    "status_code": alert.get("kind", "alert"),
                    "summary": alert.get("summary", "open alert"),
                    "severity": alert.get("severity"),
                }
            )
        return failed
