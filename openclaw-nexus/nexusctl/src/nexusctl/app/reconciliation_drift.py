"""Drift decision helpers for GitHub reconciliation.

The helpers in this module answer two intentionally narrow questions:
what labels Nexusctl expects on a projection, and whether an observed external
GitHub value drifted from that expectation.  They do not perform writes.
"""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any


@dataclass(frozen=True, slots=True)
class LabelDrift:
    expected: list[str]
    actual: list[str]
    drifted: bool


class GitHubReconciliationDriftAnalyzer:
    """Calculate Nexus-authoritative projection expectations."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def issue_labels(self, link: sqlite3.Row) -> list[str]:
        return sorted(
            {
                f"nexus:{link['feature_request_id']}",
                f"domain:{link['source_domain_id']}",
                f"target:{link['target_domain_id']}",
                f"status:{status_label_value(link['status'])}",
            }
        )

    def pull_labels(self, link: sqlite3.Row) -> list[str]:
        labels = {f"nexus:{link['patch_id']}", f"status:{status_label_value(link['patch_status'])}"}
        latest_review = self.connection.execute(
            "SELECT status, verdict FROM reviews WHERE patch_id = ? ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT 1",
            (link["patch_id"],),
        ).fetchone()
        if latest_review is None:
            labels.add("gate:review-required")
        elif latest_review["status"] == "approved" or latest_review["verdict"] == "approved":
            labels.add("gate:review-approved")
        else:
            labels.add("gate:review-changes-requested")
        latest_acceptance = self.connection.execute(
            "SELECT status FROM acceptances WHERE feature_request_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (link["feature_request_id"],),
        ).fetchone()
        if link["source_domain_id"] == "trading" and latest_acceptance is None:
            labels.add("gate:acceptance-required")
        elif latest_acceptance is not None and latest_acceptance["status"] == "accepted":
            labels.add("gate:acceptance-accepted")
        elif latest_acceptance is not None and latest_acceptance["status"] in {"rejected", "vetoed"}:
            labels.add("gate:acceptance-rejected" if latest_acceptance["status"] == "rejected" else "gate:safety-veto")
        return sorted(labels)

    def label_drift(self, *, expected: list[str], actual: list[str]) -> LabelDrift:
        # GitHub may omit labels on webhook shapes that are otherwise valid.  A
        # missing label list is not treated as drift; a present divergent list is.
        normalized_expected = sorted(set(expected))
        normalized_actual = sorted(set(actual))
        return LabelDrift(expected=normalized_expected, actual=normalized_actual, drifted=bool(normalized_actual) and normalized_actual != normalized_expected)


def status_label_value(status: Any) -> str:
    return str(status).replace("_", "-")
