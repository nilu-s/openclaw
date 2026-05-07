"""GitHub webhook persistence and reconciliation for webhook reconciliation.

GitHub remains a projection.  Incoming signed webhooks are persisted
idempotently, then reconciled against Nexusctl state.  External GitHub changes
never become lifecycle authority; unknown or unauthorized changes create alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from nexusctl.adapters.github.app_auth import GitHubAppAuthenticator
from nexusctl.adapters.github.webhooks import (
    SUPPORTED_WEBHOOK_EVENTS,
    GitHubWebhookEnvelope,
    canonical_payload,
    compute_signature,
    require_valid_signature,
    verify_signature,
)
from nexusctl.app.github_service import GitHubProjectionConfig
from nexusctl.app.reconciliation_alerts import GitHubReconciliationAlerts
from nexusctl.app.reconciliation_drift import GitHubReconciliationDriftAnalyzer
from nexusctl.app.reconciliation_payloads import GitHubWebhookPayloadNormalizer, int_or_none
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import ValidationError
from nexusctl.storage.event_store import EventStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored JSON is invalid: {exc}") from exc


@dataclass(frozen=True, slots=True)
class WebhookReceipt:
    id: str
    delivery_id: str
    event_name: str
    action: str | None
    repository_id: str | None
    duplicate: bool
    signature_verified: bool
    processing_status: str

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "delivery_id": self.delivery_id,
            "event_name": self.event_name,
            "action": self.action,
            "repository_id": self.repository_id,
            "duplicate": self.duplicate,
            "signature_verified": self.signature_verified,
            "processing_status": self.processing_status,
        }


class GitHubReconciliationService:
    """Persist signed GitHub webhooks and reconcile projection drift."""

    def __init__(self, connection: sqlite3.Connection, policy: PolicyEngine, project_root: str | Path) -> None:
        self.connection = connection
        self.policy = policy
        self.project_root = Path(project_root)
        self.events = EventStore(connection)
        self.alerts = GitHubReconciliationAlerts(connection)
        self.drift = GitHubReconciliationDriftAnalyzer(connection)
        self.payloads = GitHubWebhookPayloadNormalizer()
        self.config = GitHubProjectionConfig.from_project_root(self.project_root)
        self.config.assert_projection_guardrails()

    def verify_webhook(
        self,
        subject: Subject,
        *,
        body: bytes | str,
        signature: str | None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        self.policy.require(subject, "github.webhook.verify", resource_domain=subject.domain)
        webhook_secret = self._webhook_secret(secret)
        verified = verify_signature(webhook_secret, body, signature)
        return {
            "ok": verified,
            "verified": verified,
            "signature_algorithm": "hmac-sha256",
            "expected_signature": compute_signature(webhook_secret, body),
        }

    def receive_webhook(
        self,
        *,
        headers: Mapping[str, str],
        body: bytes | str,
        secret: str | None = None,
        actor_id: str | None = "github-webhook",
    ) -> dict[str, Any]:
        raw_body = body.encode("utf-8") if isinstance(body, str) else body
        webhook_secret = self._webhook_secret(secret)
        normalized_headers = {str(key).lower(): value for key, value in headers.items()}
        delivery_id = normalized_headers.get("x-github-delivery") or normalized_headers.get("github-delivery")
        event_name = normalized_headers.get("x-github-event") or normalized_headers.get("github-event")
        if not delivery_id:
            raise ValidationError("missing X-GitHub-Delivery header")
        if not event_name:
            raise ValidationError("missing X-GitHub-Event header")
        signature = normalized_headers.get("x-hub-signature-256")
        require_valid_signature(webhook_secret, raw_body, signature)
        envelope = GitHubWebhookEnvelope.from_headers_and_body(headers, raw_body)
        receipt = self.persist_envelope(envelope, actor_id=actor_id)
        return {"ok": True, "webhook": receipt.to_json()}

    def persist_envelope(self, envelope: GitHubWebhookEnvelope, *, actor_id: str | None = None) -> WebhookReceipt:
        repository_id = self._repository_id_from_payload(envelope.payload)
        payload_json = canonical_payload(envelope.payload)
        existing = self.connection.execute(
            "SELECT * FROM github_webhook_events WHERE delivery_id = ?",
            (envelope.delivery_id,),
        ).fetchone()
        if existing is not None:
            if existing["payload_json"] != payload_json or existing["event_name"] != envelope.event_name:
                raise ValidationError("conflicting GitHub webhook delivery: delivery id was already received with different content")
            return WebhookReceipt(
                id=existing["id"],
                delivery_id=existing["delivery_id"],
                event_name=existing["event_name"],
                action=_row_get(existing, "action"),
                repository_id=existing["repository_id"],
                duplicate=True,
                signature_verified=bool(_row_get(existing, "signature_verified", 1)),
                processing_status=str(_row_get(existing, "processing_status", "pending")),
            )

        webhook_id = f"gh-webhook-{uuid4().hex}"
        columns = _table_columns(self.connection, "github_webhook_events")
        values: dict[str, Any] = {
            "id": webhook_id,
            "repository_id": repository_id,
            "delivery_id": envelope.delivery_id,
            "event_name": envelope.event_name,
            "payload_json": payload_json,
            "received_at": _utcnow_iso(),
        }
        if "action" in columns:
            values["action"] = envelope.action
        unsupported_event = envelope.event_name not in SUPPORTED_WEBHOOK_EVENTS
        if "processing_status" in columns:
            values["processing_status"] = "ignored" if unsupported_event else "pending"
        if unsupported_event and "processed_at" in columns:
            values["processed_at"] = _utcnow_iso()
        if "signature_verified" in columns:
            values["signature_verified"] = 1
        keys = [key for key in values if key in columns]
        self.connection.execute(
            f"INSERT INTO github_webhook_events({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
            tuple(values[key] for key in keys),
        )
        self.events.append(
            aggregate_type="github_webhook",
            aggregate_id=webhook_id,
            event_type="github.webhook.received",
            actor_id=actor_id,
            payload={
                "delivery_id": envelope.delivery_id,
                "event_name": envelope.event_name,
                "action": envelope.action,
                "repository_id": repository_id,
            },
            metadata={"milestone": 13, "service": self.__class__.__name__},
        )
        return WebhookReceipt(
            id=webhook_id,
            delivery_id=envelope.delivery_id,
            event_name=envelope.event_name,
            action=envelope.action,
            repository_id=repository_id,
            duplicate=False,
            signature_verified=True,
            processing_status="ignored" if unsupported_event else "pending",
        )

    def reconcile(self, subject: Subject, *, limit: int = 100) -> dict[str, Any]:
        self.policy.require(subject, "github.reconcile", target_domain="software", resource_domain="software")
        rows = self.connection.execute(
            """
            SELECT * FROM github_webhook_events
            WHERE processed_at IS NULL
              AND processing_status = 'pending'
            ORDER BY received_at ASC, id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        processed: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        for row in rows:
            outcome = self._process_webhook_row(row, actor_id=subject.agent_id)
            processed.append(outcome)
            alerts.extend(outcome.get("alerts", []))
        event = self.events.append(
            aggregate_type="github",
            aggregate_id="reconciliation",
            event_type="github.reconciled",
            actor_id=subject.agent_id,
            payload={"processed_count": len(processed), "alert_count": len(alerts), "delivery_ids": [p["delivery_id"] for p in processed]},
            metadata={"milestone": 13, "service": self.__class__.__name__},
        )
        return {"ok": True, "processed_count": len(processed), "alerts": alerts, "processed": processed, "event_id": event.event_id}

    def _process_webhook_row(self, row: sqlite3.Row, *, actor_id: str | None) -> dict[str, Any]:
        payload = _json_loads(row["payload_json"], default={})
        event_name = str(row["event_name"])
        delivery_id = str(row["delivery_id"])
        action = _row_get(row, "action") or (payload.get("action") if isinstance(payload, dict) else None)
        alerts: list[dict[str, Any]] = []
        repairs: list[dict[str, Any]] = []
        status = "processed"

        if event_name == "issues":
            alerts, repairs = self._process_issue(delivery_id, payload, actor_id=actor_id)
        elif event_name == "issue_comment":
            alerts, repairs = self._process_issue_comment(delivery_id, payload, actor_id=actor_id)
        elif event_name == "pull_request":
            alerts, repairs = self._process_pull_request(delivery_id, payload, actor_id=actor_id)
        elif event_name == "pull_request_review":
            alerts, repairs = self._process_pull_request_review(delivery_id, payload, actor_id=actor_id)
        elif event_name == "check_run":
            alerts, repairs = self._process_check_run(delivery_id, payload, actor_id=actor_id)
        elif event_name == "workflow_run":
            alerts, repairs = self._process_workflow_run(delivery_id, payload, actor_id=actor_id)
        elif event_name == "push":
            alerts, repairs = self._process_push(delivery_id, payload, actor_id=actor_id)
        else:
            alerts = [
                self._create_alert(
                    delivery_id=delivery_id,
                    kind="unsupported_github_webhook",
                    severity="warning",
                    summary=f"unsupported GitHub webhook event {event_name}",
                    repository_id=row["repository_id"],
                )
            ]
            status = "alerted"

        if alerts and status == "processed":
            status = "alerted"
        self._mark_processed(row["id"], status=status, alert_id=(alerts[0]["id"] if alerts else None))
        self.events.append(
            aggregate_type="github_webhook",
            aggregate_id=row["id"],
            event_type="github.webhook.processed",
            actor_id=actor_id,
            payload={
                "delivery_id": delivery_id,
                "event_name": event_name,
                "action": action,
                "status": status,
                "alerts": alerts,
                "repairs": repairs,
            },
            metadata={"milestone": 13, "service": self.__class__.__name__},
        )
        return {"id": row["id"], "delivery_id": delivery_id, "event_name": event_name, "action": action, "status": status, "alerts": alerts, "repairs": repairs}

    def _process_issue(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        issue_number = int_or_none(issue.get("number"))
        if repository_id is None or issue_number is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_issue_change", repository_id=repository_id)], [])
        link = self.connection.execute(
            """
            SELECT il.*, fr.source_domain_id, fr.target_domain_id, fr.status, fr.id AS feature_request_id
            FROM github_issue_links il
            JOIN feature_requests fr ON fr.id = il.feature_request_id
            WHERE il.repository_id = ? AND il.issue_number = ?
            """,
            (repository_id, issue_number),
        ).fetchone()
        if link is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_issue_change", repository_id=repository_id, issue_number=issue_number)], [])
        expected = self.drift.issue_labels(link)
        actual = self.payloads.label_names(issue.get("labels"))
        repair = self._record_projection_labels("issue", link["feature_request_id"], repository_id, issue_number, expected)
        alerts: list[dict[str, Any]] = []
        if actual and actual != expected:
            alerts.append(
                self._create_alert(
                    delivery_id=delivery_id,
                    kind="github_label_drift_reconciled",
                    severity="warning",
                    summary=f"issue #{issue_number} labels drifted and were reset to Nexusctl state",
                    repository_id=repository_id,
                    feature_request_id=link["feature_request_id"],
                )
            )
        self.events.append(
            aggregate_type="feature_request",
            aggregate_id=link["feature_request_id"],
            event_type="github.issue.reconciled",
            actor_id=actor_id,
            payload={"repository_id": repository_id, "issue_number": issue_number, "expected_labels": expected, "actual_labels": actual},
            metadata={"milestone": 13, "delivery_id": delivery_id},
        )
        return alerts, [repair]

    def _process_issue_comment(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        issue_number = int_or_none(issue.get("number"))
        link = None
        if repository_id is not None and issue_number is not None:
            link = self.connection.execute(
                "SELECT * FROM github_issue_links WHERE repository_id = ? AND issue_number = ?",
                (repository_id, issue_number),
            ).fetchone()
        if link is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_issue_comment", repository_id=repository_id, issue_number=issue_number)], [])
        self.events.append(
            aggregate_type="feature_request",
            aggregate_id=link["feature_request_id"],
            event_type="github.issue_comment.observed",
            actor_id=actor_id,
            payload={"repository_id": repository_id, "issue_number": issue_number, "comment_id": (payload.get("comment") or {}).get("id")},
            metadata={"milestone": 13, "delivery_id": delivery_id},
        )
        return [], []

    def _process_pull_request(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        pull = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
        pull_number = int_or_none(pull.get("number") or payload.get("number"))
        if repository_id is None or pull_number is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_pr_change", repository_id=repository_id)], [])
        link = self._pull_link(repository_id, pull_number)
        if link is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_pr_change", repository_id=repository_id, pull_number=pull_number)], [])

        alerts: list[dict[str, Any]] = []
        repairs: list[dict[str, Any]] = []
        expected_labels = self.drift.pull_labels(link)
        actual_labels = self.payloads.label_names(pull.get("labels"))
        repairs.append(self._record_projection_labels("pull_request", link["patch_id"], repository_id, pull_number, expected_labels))
        if actual_labels and actual_labels != expected_labels:
            alerts.append(
                self._create_alert(
                    delivery_id=delivery_id,
                    kind="github_label_drift_reconciled",
                    severity="warning",
                    summary=f"PR #{pull_number} labels drifted and were reset to Nexusctl state",
                    repository_id=repository_id,
                    pull_number=pull_number,
                    patch_id=link["patch_id"],
                    feature_request_id=link["feature_request_id"],
                )
            )

        head_sha = ((pull.get("head") or {}) or {}).get("sha")
        if head_sha:
            prior = self.connection.execute(
                "SELECT * FROM github_pull_states WHERE patch_id = ? AND repository_id = ? AND pull_number = ?",
                (link["patch_id"], repository_id, pull_number),
            ).fetchone()
            if prior is not None and prior["head_sha"] != head_sha:
                alerts.append(
                    self._create_alert(
                        delivery_id=delivery_id,
                        kind="github_pr_head_sha_changed",
                        severity="warning",
                        summary=f"PR #{pull_number} head SHA changed after Nexusctl validation",
                        repository_id=repository_id,
                        pull_number=pull_number,
                        patch_id=link["patch_id"],
                        feature_request_id=link["feature_request_id"],
                    )
                )
            self._upsert_pull_state(link, head_sha=str(head_sha))
            repairs.append({"kind": "pull_state_synced", "patch_id": link["patch_id"], "head_sha": str(head_sha)})

        if payload.get("action") == "closed" and pull.get("merged") is True:
            merge = self.connection.execute(
                "SELECT * FROM merge_records WHERE patch_id = ? AND repository_id = ? AND pull_number = ? AND status = 'merged'",
                (link["patch_id"], repository_id, pull_number),
            ).fetchone()
            if merge is None:
                alerts.append(
                    self._create_alert(
                        delivery_id=delivery_id,
                        kind="unauthorized_github_merge",
                        severity="critical",
                        summary=f"PR #{pull_number} was merged on GitHub without a Nexusctl merge record",
                        repository_id=repository_id,
                        pull_number=pull_number,
                        patch_id=link["patch_id"],
                        feature_request_id=link["feature_request_id"],
                    )
                )
        self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=link["patch_id"],
            event_type="github.pull_request.reconciled",
            actor_id=actor_id,
            payload={"repository_id": repository_id, "pull_number": pull_number, "head_sha": head_sha, "expected_labels": expected_labels, "actual_labels": actual_labels},
            metadata={"milestone": 13, "delivery_id": delivery_id},
        )
        return alerts, repairs

    def _process_pull_request_review(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        pull = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
        pull_number = int_or_none(pull.get("number"))
        link = self._pull_link(repository_id, pull_number) if repository_id is not None and pull_number is not None else None
        if link is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_pr_review", repository_id=repository_id, pull_number=pull_number)], [])
        review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
        external_id = str(review.get("id")) if review.get("id") is not None else None
        matched = None
        if external_id:
            matched = self.connection.execute(
                "SELECT * FROM github_pr_review_links WHERE patch_id = ? AND repository_id = ? AND pull_number = ? AND external_id = ?",
                (link["patch_id"], repository_id, pull_number, external_id),
            ).fetchone()
        alerts: list[dict[str, Any]] = []
        if matched is None:
            alerts.append(
                self._create_alert(
                    delivery_id=delivery_id,
                    kind="external_github_review_ignored",
                    severity="warning",
                    summary=f"external PR review on #{pull_number} is ignored; Nexusctl review remains authoritative",
                    repository_id=repository_id,
                    pull_number=pull_number,
                    patch_id=link["patch_id"],
                    feature_request_id=link["feature_request_id"],
                )
            )
        self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=link["patch_id"],
            event_type="github.pull_request_review.observed",
            actor_id=actor_id,
            payload={"repository_id": repository_id, "pull_number": pull_number, "external_id": external_id, "matched_nexus_review": matched is not None},
            metadata={"milestone": 13, "delivery_id": delivery_id},
        )
        return alerts, []

    def _process_check_run(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        check = payload.get("check_run") if isinstance(payload.get("check_run"), dict) else {}
        pull_number = self.payloads.first_pull_request_number(check.get("pull_requests"))
        link = self._pull_link(repository_id, pull_number) if repository_id is not None and pull_number is not None else None
        if link is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_check_run", repository_id=repository_id, pull_number=pull_number)], [])
        name = str(check.get("name") or "github/check-run")
        head_sha = str(check.get("head_sha") or "")
        conclusion = check.get("conclusion")
        status = str(check.get("status") or "completed")
        check_id = self._upsert_check_run(
            patch_id=link["patch_id"],
            repository_id=repository_id,
            pull_number=pull_number,
            name=name,
            status=status,
            conclusion=str(conclusion) if conclusion is not None else None,
            head_sha=head_sha,
            external_id=str(check.get("id")) if check.get("id") is not None else None,
            url=check.get("html_url"),
            details={"source": "github_webhook", "delivery_id": delivery_id, "payload_action": payload.get("action")},
        )
        alerts: list[dict[str, Any]] = []
        if status == "completed" and conclusion not in {None, "success", "neutral", "skipped"}:
            alerts.append(
                self._create_alert(
                    delivery_id=delivery_id,
                    kind="external_github_check_failed",
                    severity="warning",
                    summary=f"external GitHub check {name} on PR #{pull_number} completed with {conclusion}; Nexusctl policy checks remain authoritative",
                    repository_id=repository_id,
                    pull_number=pull_number,
                    patch_id=link["patch_id"],
                    feature_request_id=link["feature_request_id"],
                )
            )
        self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=link["patch_id"],
            event_type="github.check_run.reconciled",
            actor_id=actor_id,
            payload={"repository_id": repository_id, "pull_number": pull_number, "check_run_id": check_id, "name": name, "status": status, "conclusion": conclusion, "alerted": bool(alerts)},
            metadata={"milestone": 13, "delivery_id": delivery_id},
        )
        return alerts, [{"kind": "github_check_run_synced", "id": check_id, "name": name}]

    def _process_workflow_run(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        workflow = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}
        pull_number = self.payloads.first_pull_request_number(workflow.get("pull_requests"))
        link = self._pull_link(repository_id, pull_number) if repository_id is not None and pull_number is not None else None
        if link is None:
            return ([self._unknown_alert(delivery_id, "unknown_github_workflow_run", repository_id=repository_id, pull_number=pull_number)], [])
        name = str(workflow.get("name") or workflow.get("workflow_id") or "github/workflow-run")
        status = str(workflow.get("status") or "completed")
        conclusion = workflow.get("conclusion")
        head_sha = str(workflow.get("head_sha") or "")
        check_id = self._upsert_check_run(
            patch_id=link["patch_id"],
            repository_id=repository_id,
            pull_number=pull_number,
            name=f"workflow/{name}",
            status=status,
            conclusion=str(conclusion) if conclusion is not None else None,
            head_sha=head_sha,
            external_id=str(workflow.get("id")) if workflow.get("id") is not None else None,
            url=workflow.get("html_url"),
            details={"source": "github_webhook", "delivery_id": delivery_id, "payload_action": payload.get("action")},
        )
        return [], [{"kind": "github_workflow_run_synced", "id": check_id, "name": name}]

    def _process_push(self, delivery_id: str, payload: dict[str, Any], *, actor_id: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        repository_id = self._repository_id_from_payload(payload)
        ref = str(payload.get("ref") or "")
        repository = self._repository_ref(repository_id) if repository_id else self.config.default_repository()
        default_ref = f"refs/heads/{repository.default_branch}"
        severity = "critical" if ref == default_ref else "warning"
        kind = "unauthorized_default_branch_push" if ref == default_ref else "unmapped_github_push"
        alert = self._create_alert(
            delivery_id=delivery_id,
            kind=kind,
            severity=severity,
            summary=f"GitHub push on {ref or 'unknown ref'} has no Nexusctl lifecycle source",
            repository_id=repository_id,
        )
        return [alert], []

    def _upsert_check_run(
        self,
        *,
        patch_id: str,
        repository_id: str,
        pull_number: int,
        name: str,
        status: str,
        conclusion: str | None,
        head_sha: str,
        external_id: str | None,
        url: str | None,
        details: dict[str, Any],
    ) -> str:
        existing = self.connection.execute(
            """
            SELECT id FROM github_check_runs
            WHERE patch_id = ? AND repository_id = ? AND pull_number = ? AND name = ?
            """,
            (patch_id, repository_id, pull_number, name),
        ).fetchone()
        now = _utcnow_iso()
        if existing is None:
            check_id = f"gh-check-{uuid4().hex}"
            self.connection.execute(
                """
                INSERT INTO github_check_runs(id, patch_id, repository_id, pull_number, name, status, conclusion, head_sha, external_id, url, details_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (check_id, patch_id, repository_id, pull_number, name, status, conclusion, head_sha, external_id, url, _json_dumps(details), now),
            )
            return check_id
        check_id = existing["id"]
        self.connection.execute(
            """
            UPDATE github_check_runs
            SET status = ?, conclusion = ?, head_sha = ?, external_id = ?, url = ?, details_json = ?, synced_at = ?
            WHERE id = ?
            """,
            (status, conclusion, head_sha, external_id, url, _json_dumps(details), now, check_id),
        )
        return check_id

    def _upsert_pull_state(self, link: sqlite3.Row, *, head_sha: str) -> None:
        now = _utcnow_iso()
        existing = self.connection.execute(
            "SELECT id FROM github_pull_states WHERE patch_id = ? AND repository_id = ? AND pull_number = ?",
            (link["patch_id"], link["repository_id"], link["pull_number"]),
        ).fetchone()
        validated_patch_sha = link["validated_patch_sha"] or head_sha
        if existing is None:
            self.connection.execute(
                """
                INSERT INTO github_pull_states(id, patch_id, repository_id, pull_number, head_sha, validated_patch_sha, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (f"gh-pull-state-{uuid4().hex}", link["patch_id"], link["repository_id"], link["pull_number"], head_sha, validated_patch_sha, now),
            )
        else:
            self.connection.execute(
                "UPDATE github_pull_states SET head_sha = ?, synced_at = ? WHERE id = ?",
                (head_sha, now, existing["id"]),
            )

    def _record_projection_labels(self, entity_kind: str, nexus_entity_id: str, repository_id: str, external_number: int, labels: list[str]) -> dict[str, Any]:
        now = _utcnow_iso()
        labels_json = _json_dumps(sorted(set(labels)))
        existing = self.connection.execute(
            """
            SELECT id FROM github_projection_labels
            WHERE entity_kind = ? AND nexus_entity_id = ? AND repository_id = ? AND external_number = ?
            """,
            (entity_kind, nexus_entity_id, repository_id, external_number),
        ).fetchone()
        if existing is None:
            label_id = f"gh-labels-{uuid4().hex}"
            self.connection.execute(
                """
                INSERT INTO github_projection_labels(id, entity_kind, nexus_entity_id, repository_id, external_number, labels_json, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (label_id, entity_kind, nexus_entity_id, repository_id, external_number, labels_json, now),
            )
        else:
            label_id = existing["id"]
            self.connection.execute(
                "UPDATE github_projection_labels SET labels_json = ?, synced_at = ? WHERE id = ?",
                (labels_json, now, label_id),
            )
        return {"kind": "labels_reconciled", "id": label_id, "entity_kind": entity_kind, "nexus_entity_id": nexus_entity_id, "labels": sorted(set(labels))}

    def _create_alert(
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
        return self.alerts.create(
            delivery_id=delivery_id,
            kind=kind,
            severity=severity,
            summary=summary,
            repository_id=repository_id,
            pull_number=pull_number,
            patch_id=patch_id,
            feature_request_id=feature_request_id,
        )

    def _unknown_alert(
        self,
        delivery_id: str,
        kind: str,
        *,
        repository_id: str | None = None,
        issue_number: int | None = None,
        pull_number: int | None = None,
    ) -> dict[str, Any]:
        return self.alerts.unknown(
            delivery_id,
            kind,
            repository_id=repository_id,
            issue_number=issue_number,
            pull_number=pull_number,
        )

    def _mark_processed(self, webhook_id: str, *, status: str, alert_id: str | None = None) -> None:
        columns = _table_columns(self.connection, "github_webhook_events")
        updates = ["processed_at = ?"]
        values: list[Any] = [_utcnow_iso()]
        if "processing_status" in columns:
            updates.append("processing_status = ?")
            values.append(status)
        if "alert_id" in columns:
            updates.append("alert_id = ?")
            values.append(alert_id)
        values.append(webhook_id)
        self.connection.execute(f"UPDATE github_webhook_events SET {', '.join(updates)} WHERE id = ?", tuple(values))

    def _pull_link(self, repository_id: str | None, pull_number: int | None) -> sqlite3.Row | None:
        if repository_id is None or pull_number is None:
            return None
        return self.connection.execute(
            """
            SELECT pl.*, p.status AS patch_status, w.feature_request_id, fr.source_domain_id, fr.target_domain_id,
                   ps.validated_patch_sha
            FROM github_pull_links pl
            JOIN patch_proposals p ON p.id = pl.patch_id
            JOIN work_items w ON w.id = p.work_item_id
            JOIN feature_requests fr ON fr.id = w.feature_request_id
            LEFT JOIN github_pull_states ps ON ps.patch_id = p.id AND ps.repository_id = pl.repository_id AND ps.pull_number = pl.pull_number
            WHERE pl.repository_id = ? AND pl.pull_number = ?
            ORDER BY pl.synced_at DESC, pl.id ASC
            LIMIT 1
            """,
            (repository_id, pull_number),
        ).fetchone()

    def _repository_id_from_payload(self, payload: dict[str, Any]) -> str | None:
        ref = self.payloads.repository_ref(payload)
        for repo in self.config.repositories:
            if ref.full_name and repo.full_name == ref.full_name:
                return repo.id
            if ref.name and repo.name == ref.name and (not ref.owner or repo.owner == ref.owner):
                return repo.id
        if ref.full_name or ref.name:
            row = self.connection.execute(
                "SELECT id FROM github_repositories WHERE (owner || '/' || name) = ? OR name = ? ORDER BY id LIMIT 1",
                (ref.full_name or "", ref.name or ""),
            ).fetchone()
            if row is not None:
                return row["id"]
        return None

    def _repository_ref(self, repository_id: str | None):
        if repository_id is not None:
            for repo in self.config.repositories:
                if repo.id == repository_id:
                    return repo
        return self.config.default_repository()

    def _webhook_secret(self, explicit: str | None = None) -> str:
        if explicit:
            return explicit
        secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
        if secret:
            return secret
        raise ValidationError("GITHUB_WEBHOOK_SECRET or --secret is required for GitHub webhook verification")


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return default
