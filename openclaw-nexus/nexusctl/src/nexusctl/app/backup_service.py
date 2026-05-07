"""Application service for local database backup and restore workflows."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from nexusctl.storage.sqlite.backup import create_sqlite_backup, check_sqlite_backup, restore_sqlite_backup


class BackupService:
    """Thin app-layer facade over SQLite backup/restore helpers."""

    def __init__(self, connection: sqlite3.Connection | None = None, *, db_path: str | Path | None = None) -> None:
        self.connection = connection
        self.db_path = Path(db_path) if db_path is not None else None

    def create(self, *, backup_path: str | Path | None = None, actor_id: str | None = None) -> dict[str, Any]:
        if self.connection is None or self.db_path is None:
            raise RuntimeError("BackupService.create requires an open connection and db_path")
        return create_sqlite_backup(
            self.connection,
            source_db_path=self.db_path,
            backup_path=backup_path,
            actor_id=actor_id,
        ).to_json()

    def check(self, backup_path: str | Path) -> dict[str, Any]:
        return check_sqlite_backup(backup_path).to_json()

    def restore(self, *, backup_path: str | Path, target_db_path: str | Path, overwrite: bool = False) -> dict[str, Any]:
        return restore_sqlite_backup(
            backup_path=backup_path,
            target_db_path=target_db_path,
            overwrite=overwrite,
        ).to_json()
