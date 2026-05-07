"""Business-domain acceptance and safety-veto workflow for review/acceptance workflow.

Acceptance is owned by the request's source domain.  A technical review can make
a patch ready for domain acceptance, but it cannot replace that acceptance.
Safety vetoes are first-class blocking records written by the Trading Sentinel.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.app.github_service import GitHubProjectionConfig
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import ValidationError
from nexusctl.storage.sqlite.repositories import RepositoryContext


ACCEPTANCE_VERDICTS = {"accepted", "rejected", "vetoed"}


class AcceptanceService:
    """Submit and inspect business acceptance records for Feature Requests."""

    def __init__(self, connection: sqlite3.Connection, policy: PolicyEngine, project_root: str | Path) -> None:
        self.connection = connection
        self.policy = policy
        self.project_root = Path(project_root)
        self.repositories = RepositoryContext(connection)
        self.events = self.repositories.events
        self.github_config = GitHubProjectionConfig.from_project_root(self.project_root)
        self.github_config.assert_projection_guardrails()

    def submit(self, subject: Subject, feature_request_or_patch_id: str, *, verdict: str, notes: str = "") -> dict[str, Any]:
        normalized = _normalize_acceptance_verdict(verdict)
        request = self._resolve_feature_request(feature_request_or_patch_id)
        if normalized == "vetoed":
            self.policy.require(subject, "safety.veto", resource_domain=request["source_domain"])
            event_type = "safety.veto.submitted"
        else:
            self.policy.require(subject, "acceptance.submit", resource_domain=request["source_domain"])
            event_type = "acceptance.submitted"

        acceptance_id = f"acceptance-{uuid4().hex}"
        now = _utcnow_iso()
        self.connection.execute(
            """
            INSERT INTO acceptances(id, feature_request_id, submitted_by, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (acceptance_id, request["id"], subject.agent_id, normalized, notes, now),
        )
        label_projection = self._project_acceptance_labels(request, status=normalized, synced_at=now)
        event = self.events.append(
            aggregate_type="feature_request",
            aggregate_id=request["id"],
            event_type=event_type,
            actor_id=subject.agent_id,
            payload={
                "acceptance_id": acceptance_id,
                "feature_request_id": request["id"],
                "status": normalized,
                "submitted_by": subject.agent_id,
                "label_projection": label_projection,
            },
            metadata={"milestone": 11, "service": self.__class__.__name__},
        )
        return {
            "ok": True,
            "acceptance": {
                "id": acceptance_id,
                "feature_request_id": request["id"],
                "submitted_by": subject.agent_id,
                "status": normalized,
                "notes": notes,
                "created_at": now,
            },
            "acceptance_status": self._status_for_request(request["id"]),
            "label_projection": label_projection,
            "event_id": event.event_id,
        }

    def status(self, subject: Subject, feature_request_or_patch_id: str) -> dict[str, Any]:
        request = self._resolve_feature_request(feature_request_or_patch_id)
        self.policy.require(subject, "feature_request.read")
        return {
            "ok": True,
            "agent_id": subject.agent_id,
            "domain": subject.domain,
            "feature_request_id": request["id"],
            "acceptance_status": self._status_for_request(request["id"]),
        }

    def _resolve_feature_request(self, feature_request_or_patch_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM feature_requests WHERE id = ?",
            (feature_request_or_patch_id,),
        ).fetchone()
        if row is None:
            row = self.connection.execute(
                """
                SELECT fr.*
                FROM patch_proposals p
                JOIN work_items w ON w.id = p.work_item_id
                JOIN feature_requests fr ON fr.id = w.feature_request_id
                WHERE p.id = ?
                LIMIT 1
                """,
                (feature_request_or_patch_id,),
            ).fetchone()
        if row is None:
            raise ValidationError(f"unknown feature request or patch proposal {feature_request_or_patch_id}")
        return {
            "id": row["id"],
            "source_domain": row["source_domain_id"],
            "target_domain": row["target_domain_id"],
            "created_by": row["created_by"],
            "goal_id": row["goal_id"],
            "summary": row["summary"],
            "status": row["status"],
            "acceptance_contract": _json_object(row["acceptance_contract"]),
            "safety_contract": _json_object(row["safety_contract"]),
        }

    def _status_for_request(self, feature_request_id: str) -> dict[str, Any]:
        rows = self.connection.execute(
            """
            SELECT * FROM acceptances
            WHERE feature_request_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (feature_request_id,),
        ).fetchall()
        latest_acceptance = None
        latest_safety_veto = None
        for row in rows:
            item = {
                "id": row["id"],
                "status": row["status"],
                "submitted_by": row["submitted_by"],
                "notes": row["notes"],
                "created_at": row["created_at"],
            }
            if row["status"] == "vetoed" and latest_safety_veto is None:
                latest_safety_veto = item
            if row["status"] in {"accepted", "rejected"} and latest_acceptance is None:
                latest_acceptance = item
        effective = "pending"
        if latest_safety_veto is not None:
            effective = "vetoed"
        elif latest_acceptance is not None:
            effective = latest_acceptance["status"]
        return {
            "feature_request_id": feature_request_id,
            "effective_status": effective,
            "latest_acceptance": latest_acceptance,
            "latest_safety_veto": latest_safety_veto,
            "history": [
                {
                    "id": row["id"],
                    "status": row["status"],
                    "submitted_by": row["submitted_by"],
                    "notes": row["notes"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }

    def _project_acceptance_labels(self, request: dict[str, Any], *, status: str, synced_at: str) -> dict[str, Any]:
        labels = self._acceptance_labels(request, status=status)
        issue_labels: list[dict[str, Any]] = []
        pull_request_labels: list[dict[str, Any]] = []
        for issue in self.connection.execute(
            "SELECT * FROM github_issue_links WHERE feature_request_id = ? ORDER BY synced_at DESC, id ASC",
            (request["id"],),
        ).fetchall():
            label_id = self._upsert_projection_labels(
                entity_kind="issue",
                nexus_entity_id=request["id"],
                repository_id=issue["repository_id"],
                external_number=int(issue["issue_number"]),
                labels=labels,
                synced_at=synced_at,
            )
            issue_labels.append({"id": label_id, "repository_id": issue["repository_id"], "issue_number": issue["issue_number"], "labels": labels})
        for pull in self.connection.execute(
            """
            SELECT pr.*
            FROM github_pull_links pr
            JOIN patch_proposals p ON p.id = pr.patch_id
            JOIN work_items w ON w.id = p.work_item_id
            WHERE w.feature_request_id = ?
            ORDER BY pr.synced_at DESC, pr.id ASC
            """,
            (request["id"],),
        ).fetchall():
            pr_labels = [*labels, f"patch:{pull['patch_id']}"]
            label_id = self._upsert_projection_labels(
                entity_kind="pull_request",
                nexus_entity_id=pull["patch_id"],
                repository_id=pull["repository_id"],
                external_number=int(pull["pull_number"]),
                labels=pr_labels,
                synced_at=synced_at,
            )
            pull_request_labels.append({"id": label_id, "repository_id": pull["repository_id"], "pull_number": pull["pull_number"], "patch_id": pull["patch_id"], "labels": pr_labels})
        return {"issue_labels": issue_labels, "pull_request_labels": pull_request_labels}

    def _acceptance_labels(self, request: dict[str, Any], *, status: str) -> list[str]:
        labels = [
            f"nexus:{request['id']}",
            f"domain:{request['source_domain']}",
            f"target:{request['target_domain']}",
        ]
        if status == "accepted":
            labels.extend(["status:accepted", "gate:acceptance-accepted"])
        elif status == "rejected":
            labels.extend(["status:blocked", "gate:acceptance-rejected"])
        else:
            labels.extend(["status:blocked", "gate:safety-veto"])
        return labels

    def _upsert_projection_labels(
        self,
        *,
        entity_kind: str,
        nexus_entity_id: str,
        repository_id: str,
        external_number: int,
        labels: list[str],
        synced_at: str,
    ) -> str:
        existing = self.connection.execute(
            """
            SELECT id FROM github_projection_labels
            WHERE entity_kind = ? AND nexus_entity_id = ? AND repository_id = ? AND external_number = ?
            """,
            (entity_kind, nexus_entity_id, repository_id, external_number),
        ).fetchone()
        labels_json = _json_dumps(labels)
        if existing is None:
            label_id = f"gh-labels-{uuid4().hex}"
            self.connection.execute(
                """
                INSERT INTO github_projection_labels(id, entity_kind, nexus_entity_id, repository_id, external_number, labels_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (label_id, entity_kind, nexus_entity_id, repository_id, external_number, labels_json, synced_at),
            )
            return label_id
        label_id = existing["id"]
        self.connection.execute(
            "UPDATE github_projection_labels SET labels_json = ?, synced_at = ? WHERE id = ?",
            (labels_json, synced_at, label_id),
        )
        return label_id


def _normalize_acceptance_verdict(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized in {"safety-veto", "veto"}:
        normalized = "vetoed"
    if normalized not in ACCEPTANCE_VERDICTS:
        raise ValidationError("acceptance verdict must be accepted, rejected, or vetoed")
    return normalized


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_object(value: str | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("stored JSON must be an object")
    return data


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [], sort_keys=True, separators=(",", ":"))
