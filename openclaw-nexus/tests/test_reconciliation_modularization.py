from __future__ import annotations

import sqlite3

from nexusctl.app.reconciliation_alerts import GitHubReconciliationAlerts
from nexusctl.app.reconciliation_drift import GitHubReconciliationDriftAnalyzer
from nexusctl.app.reconciliation_payloads import GitHubWebhookPayloadNormalizer


def test_reconciliation_payload_normalizer_extracts_repository_pull_and_labels() -> None:
    payload = {
        "repository": {"owner": {"login": "openclaw"}, "name": "openclaw-nexus", "full_name": "openclaw/openclaw-nexus"},
        "pull_request": {"number": "42", "labels": [{"name": "status:proposed"}, "nexus:patch-1", {"name": "status:proposed"}]},
    }

    normalizer = GitHubWebhookPayloadNormalizer()

    repo = normalizer.repository_ref(payload)
    assert repo.full_name == "openclaw/openclaw-nexus"
    assert repo.owner == "openclaw"
    assert repo.name == "openclaw-nexus"
    assert normalizer.pull_request_ref(payload, "repo-main").pull_number == 42
    assert normalizer.label_names(payload["pull_request"]["labels"]) == ["nexus:patch-1", "status:proposed"]


def test_reconciliation_drift_analyzer_keeps_missing_labels_non_drift_but_detects_divergence() -> None:
    analyzer = GitHubReconciliationDriftAnalyzer(sqlite3.connect(":memory:"))

    assert analyzer.label_drift(expected=["status:proposed"], actual=[]).drifted is False
    assert analyzer.label_drift(expected=["status:proposed"], actual=["status:wrong"]).drifted is True


def test_reconciliation_alert_helper_is_idempotent_and_non_authoritative() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE github_alerts(
            id TEXT PRIMARY KEY,
            repository_id TEXT,
            pull_number INTEGER,
            patch_id TEXT,
            feature_request_id TEXT,
            severity TEXT,
            status TEXT,
            kind TEXT,
            summary TEXT
        )
        """
    )
    alerts = GitHubReconciliationAlerts(connection)

    first = alerts.create(delivery_id="delivery-1", kind="external_github_review_ignored", severity="warning", summary="ignored external review")
    second = alerts.create(delivery_id="delivery-1", kind="external_github_review_ignored", severity="warning", summary="ignored external review")

    assert first == second
    assert connection.execute("SELECT COUNT(*) AS count FROM github_alerts").fetchone()["count"] == 1
    assert connection.execute("SELECT status FROM github_alerts").fetchone()["status"] == "open"
