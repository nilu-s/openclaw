"""Alert creation helpers for GitHub reconciliation."""

from __future__ import annotations

import sqlite3
from typing import Any


class GitHubReconciliationAlerts:
    """Create idempotent reconciliation alerts without changing lifecycle state."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(
        self,
        *,
        delivery_id: str,
        kind: str,
        severity: str,
        summary: str,
        repository_id: str | None = None,
        pull_number: int | None = None,
        patch_id: str | None = None,
        feature_request_id: str | None = None,
    ) -> dict[str, Any]:
        alert_id = f"gh-alert-{delivery_id}-{kind}"[:128]
        self.connection.execute(
            """
            INSERT OR IGNORE INTO github_alerts(id, repository_id, pull_number, patch_id, feature_request_id, severity, status, kind, summary)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (alert_id, repository_id, pull_number, patch_id, feature_request_id, severity, kind, summary),
        )
        return {
            "id": alert_id,
            "severity": severity,
            "kind": kind,
            "summary": summary,
            "repository_id": repository_id,
            "pull_number": pull_number,
            "patch_id": patch_id,
            "feature_request_id": feature_request_id,
        }

    def unknown(
        self,
        delivery_id: str,
        kind: str,
        *,
        repository_id: str | None = None,
        issue_number: int | None = None,
        pull_number: int | None = None,
    ) -> dict[str, Any]:
        external_number = issue_number or pull_number
        summary = f"GitHub webhook {kind} could not be mapped to Nexusctl state"
        if external_number is not None:
            summary += f" for external #{external_number}"
        return self.create(
            delivery_id=delivery_id,
            kind=kind,
            severity="warning",
            summary=summary,
            repository_id=repository_id,
            pull_number=pull_number,
        )
