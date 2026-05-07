"""Technical review workflow for review/acceptance workflow.

Software review is a Nexusctl-owned technical gate.  It is deliberately separate
from business-domain acceptance and safety vetoes.  Any GitHub PR-review output
is a projection of the Nexusctl review record, not the source of truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.adapters.github.app_auth import GitHubAppAuthenticator
from nexusctl.adapters.github.client import GitHubClient, GitHubRepositoryRef, MockGitHubClient
from nexusctl.adapters.github.reviews import GitHubPullRequestReviewSpec, GitHubPullRequestReviewsAdapter
from nexusctl.app.github_service import GitHubProjectionConfig
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.domain.states import WorkItemStatus
from nexusctl.storage.sqlite.repositories import RepositoryContext


REVIEW_VERDICTS: dict[str, tuple[str, str, str]] = {
    "approved": ("approved", "approved", "APPROVE"),
    "changes-requested": ("changes_requested", "changes-requested", "REQUEST_CHANGES"),
    "changes_requested": ("changes_requested", "changes-requested", "REQUEST_CHANGES"),
    "rejected": ("rejected", "rejected", "REQUEST_CHANGES"),
}


class ReviewService:
    """Submit and inspect technical software reviews for patch proposals."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        policy: PolicyEngine,
        project_root: str | Path,
        *,
        github_client: GitHubClient | None = None,
    ) -> None:
        self.connection = connection
        self.policy = policy
        self.project_root = Path(project_root)
        self.repositories = RepositoryContext(connection)
        self.events = self.repositories.events
        self.github_config = GitHubProjectionConfig.from_project_root(self.project_root)
        self.github_config.assert_projection_guardrails()
        self.github_client = github_client or MockGitHubClient(GitHubAppAuthenticator.from_env())
        self.review_adapter = GitHubPullRequestReviewsAdapter(self.github_client)

    def queue(self, subject: Subject) -> dict[str, Any]:
        self.policy.require(subject, "work.read", resource_domain=subject.domain)
        rows = self.connection.execute(
            """
            SELECT
              p.id AS patch_id, p.status AS patch_status, p.diff_summary, p.created_at AS patch_created_at,
              w.id AS work_item_id, w.feature_request_id, w.domain_id, w.assigned_agent_id, w.reviewer_agent_id,
              fr.source_domain_id, fr.target_domain_id, fr.summary AS feature_summary,
              lr.id AS latest_review_id, lr.status AS latest_review_status, lr.verdict AS latest_review_verdict,
              pr.repository_id, pr.pull_number, pr.url AS pull_url
            FROM patch_proposals p
            JOIN work_items w ON w.id = p.work_item_id
            JOIN feature_requests fr ON fr.id = w.feature_request_id
            LEFT JOIN reviews lr ON lr.id = (
              SELECT r2.id FROM reviews r2
              WHERE r2.patch_id = p.id
              ORDER BY r2.updated_at DESC, r2.created_at DESC, r2.id DESC
              LIMIT 1
            )
            LEFT JOIN github_pull_links pr ON pr.patch_id = p.id
            WHERE w.domain_id = ?
              AND p.status IN ('submitted','reviewing')
              AND COALESCE(lr.status, 'pending') NOT IN ('approved','rejected')
            ORDER BY p.created_at ASC, p.id ASC
            """,
            (subject.domain,),
        ).fetchall()
        items = [self._queue_row(row) for row in rows]
        return {"ok": True, "agent_id": subject.agent_id, "domain": subject.domain, "review_queue": items}

    def submit(self, subject: Subject, patch_or_work_id: str, *, verdict: str, notes: str = "") -> dict[str, Any]:
        normalized = _normalize_review_verdict(verdict)
        status, stored_verdict, github_event = REVIEW_VERDICTS[normalized]
        patch = self._resolve_patch(patch_or_work_id)
        capability = "review.approve" if status == "approved" else "review.submit"
        self.policy.require(subject, capability, resource_domain=patch["domain"])
        if patch.get("reviewer_agent_id") and patch["reviewer_agent_id"] != subject.agent_id and subject.normal_agent:
            raise PolicyDeniedError(
                "only the assigned software reviewer may submit this technical review",
                rule_id="review-acceptance_assigned_reviewer_required",
            )
        if patch.get("submitted_by") == subject.agent_id:
            raise PolicyDeniedError(
                "patch submitter may not review their own patch",
                rule_id="review-acceptance_reviewer_separation_required",
            )

        review_id = f"review-{uuid4().hex}"
        now = _utcnow_iso()
        self.repositories.reviews.create(
            review_id=review_id,
            work_item_id=patch["work_item_id"],
            patch_id=patch["id"],
            reviewer_agent_id=subject.agent_id,
            status=status,
            verdict=stored_verdict,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
        next_work_status = WorkItemStatus.ACCEPTANCE_REQUIRED.value if status == "approved" else WorkItemStatus.REVIEWING.value
        self.repositories.reviews.update_work_status(
            work_item_id=patch["work_item_id"], status=next_work_status, updated_at=now
        )

        github_review = self._project_github_review(
            patch,
            review_id=review_id,
            reviewer=subject.agent_id,
            status=status,
            verdict=stored_verdict,
            notes=notes,
            github_event=github_event,
            synced_at=now,
        )
        label_projection = self._project_review_labels(patch, status=status, synced_at=now)
        event = self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=patch["id"],
            event_type="review.submitted",
            actor_id=subject.agent_id,
            payload={
                "review_id": review_id,
                "patch_id": patch["id"],
                "work_item_id": patch["work_item_id"],
                "feature_request_id": patch["feature_request_id"],
                "status": status,
                "verdict": stored_verdict,
                "github_pr_review": github_review,
                "label_projection": label_projection,
            },
            metadata={"milestone": 11, "service": self.__class__.__name__},
        )
        return {
            "ok": True,
            "review": {
                "id": review_id,
                "patch_id": patch["id"],
                "work_item_id": patch["work_item_id"],
                "feature_request_id": patch["feature_request_id"],
                "reviewer_agent_id": subject.agent_id,
                "status": status,
                "verdict": stored_verdict,
                "notes": notes,
                "created_at": now,
            },
            "github_pr_review": github_review,
            "label_projection": label_projection,
            "event_id": event.event_id,
        }

    def _resolve_patch(self, patch_or_work_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT
              p.*, w.feature_request_id, w.domain_id, w.assigned_agent_id, w.reviewer_agent_id,
              fr.source_domain_id, fr.target_domain_id, fr.acceptance_contract,
              pr.repository_id, pr.pull_number, pr.branch, pr.url AS pull_url,
              ps.head_sha
            FROM patch_proposals p
            JOIN work_items w ON w.id = p.work_item_id
            JOIN feature_requests fr ON fr.id = w.feature_request_id
            LEFT JOIN github_pull_links pr ON pr.patch_id = p.id
            LEFT JOIN github_pull_states ps
              ON ps.patch_id = p.id AND ps.repository_id = pr.repository_id AND ps.pull_number = pr.pull_number
            WHERE p.id = ?
            ORDER BY pr.synced_at DESC, pr.id ASC
            LIMIT 1
            """,
            (patch_or_work_id,),
        ).fetchone()
        if row is None:
            row = self.connection.execute(
                """
                SELECT
                  p.*, w.feature_request_id, w.domain_id, w.assigned_agent_id, w.reviewer_agent_id,
                  fr.source_domain_id, fr.target_domain_id, fr.acceptance_contract,
                  pr.repository_id, pr.pull_number, pr.branch, pr.url AS pull_url,
                  ps.head_sha
                FROM patch_proposals p
                JOIN work_items w ON w.id = p.work_item_id
                JOIN feature_requests fr ON fr.id = w.feature_request_id
                LEFT JOIN github_pull_links pr ON pr.patch_id = p.id
                LEFT JOIN github_pull_states ps
                  ON ps.patch_id = p.id AND ps.repository_id = pr.repository_id AND ps.pull_number = pr.pull_number
                WHERE w.id = ?
                ORDER BY p.created_at DESC, p.id DESC, pr.synced_at DESC
                LIMIT 1
                """,
                (patch_or_work_id,),
            ).fetchone()
        if row is None:
            raise ValidationError(f"unknown patch proposal or work item {patch_or_work_id}")
        diff = _json_object(row["diff_json"])
        changed_paths = diff.get("changed_paths") or []
        if not isinstance(changed_paths, list) or not all(isinstance(path, str) for path in changed_paths):
            raise ValidationError("stored patch changed_paths must be a list of strings")
        return {
            "id": row["id"],
            "work_item_id": row["work_item_id"],
            "feature_request_id": row["feature_request_id"],
            "domain": row["domain_id"],
            "source_domain": row["source_domain_id"],
            "target_domain": row["target_domain_id"],
            "assigned_agent_id": row["assigned_agent_id"],
            "reviewer_agent_id": row["reviewer_agent_id"],
            "submitted_by": row["submitted_by"],
            "scope_lease_id": row["scope_lease_id"],
            "status": row["status"],
            "summary": row["diff_summary"],
            "diff": diff,
            "changed_paths": changed_paths,
            "repository_id": row["repository_id"],
            "pull_number": row["pull_number"],
            "branch": row["branch"],
            "pull_url": row["pull_url"],
            "head_sha": row["head_sha"],
        }

    def _project_github_review(
        self,
        patch: dict[str, Any],
        *,
        review_id: str,
        reviewer: str,
        status: str,
        verdict: str,
        notes: str,
        github_event: str,
        synced_at: str,
    ) -> dict[str, Any] | None:
        if patch.get("repository_id") is None or patch.get("pull_number") is None:
            return None
        repository = self._repository(str(patch["repository_id"]))
        pull_number = int(patch["pull_number"])
        spec = GitHubPullRequestReviewSpec(
            event=github_event,
            body=_review_body(review_id=review_id, reviewer=reviewer, verdict=verdict, notes=notes),
            commit_sha=patch.get("head_sha"),
            details={
                "review_id": review_id,
                "patch_id": patch["id"],
                "feature_request_id": patch["feature_request_id"],
                "nexus_status": status,
            },
        )
        projected = self.review_adapter.sync_review(repository, pull_number=pull_number, spec=spec)
        link_id = f"gh-pr-review-{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO github_pr_review_links(
              id, review_id, patch_id, repository_id, pull_number, external_id, url, state, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                review_id,
                patch["id"],
                repository.id,
                pull_number,
                str(projected.get("id") or projected.get("number") or "") or None,
                projected.get("url"),
                github_event,
                synced_at,
            ),
        )
        projected["id"] = link_id
        projected["review_id"] = review_id
        return projected

    def _project_review_labels(self, patch: dict[str, Any], *, status: str, synced_at: str) -> dict[str, Any]:
        if patch.get("repository_id") is None or patch.get("pull_number") is None:
            return {"pull_request_labels": []}
        labels = [
            f"nexus:{patch['id']}",
            f"nexus:{patch['feature_request_id']}",
            "gate:review-approved" if status == "approved" else "gate:review-changes-requested",
        ]
        self._upsert_projection_labels(
            entity_kind="pull_request",
            nexus_entity_id=patch["id"],
            repository_id=str(patch["repository_id"]),
            external_number=int(patch["pull_number"]),
            labels=labels,
            synced_at=synced_at,
        )
        return {"pull_request_labels": labels}

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
            """
            UPDATE github_projection_labels
            SET labels_json = ?, synced_at = ?
            WHERE id = ?
            """,
            (labels_json, synced_at, label_id),
        )
        return label_id

    def _repository(self, repository_id: str) -> GitHubRepositoryRef:
        for repository in self.github_config.repositories:
            if repository.id == repository_id:
                return repository
        row = self.connection.execute("SELECT * FROM github_repositories WHERE id = ?", (repository_id,)).fetchone()
        if row is None:
            raise ValidationError(f"unknown GitHub repository {repository_id}")
        return GitHubRepositoryRef(
            id=row["id"],
            owner=row["owner"],
            name=row["name"],
            default_branch=row["default_branch"],
            visibility=row["visibility"],
        )

    @staticmethod
    def _queue_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "patch_id": row["patch_id"],
            "work_item_id": row["work_item_id"],
            "feature_request_id": row["feature_request_id"],
            "domain": row["domain_id"],
            "source_domain": row["source_domain_id"],
            "target_domain": row["target_domain_id"],
            "summary": row["diff_summary"],
            "feature_summary": row["feature_summary"],
            "assigned_agent_id": row["assigned_agent_id"],
            "reviewer_agent_id": row["reviewer_agent_id"],
            "patch_status": row["patch_status"],
            "latest_review": None if row["latest_review_id"] is None else {
                "id": row["latest_review_id"],
                "status": row["latest_review_status"],
                "verdict": row["latest_review_verdict"],
            },
            "github_pr": None if row["pull_number"] is None else {
                "repository_id": row["repository_id"],
                "pull_number": row["pull_number"],
                "url": row["pull_url"],
            },
            "created_at": row["patch_created_at"],
        }


def _normalize_review_verdict(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized not in REVIEW_VERDICTS:
        raise ValidationError("review verdict must be approved, changes-requested, or rejected")
    return normalized


def _review_body(*, review_id: str, reviewer: str, verdict: str, notes: str) -> str:
    body = [
        "## Nexus Technical Review",
        f"Review: `{review_id}`",
        f"Reviewer: `{reviewer}`",
        f"Verdict: `{verdict}`",
    ]
    if notes:
        body.extend(["## Notes", notes])
    body.append("GitHub is a projection only; Nexusctl stores the authoritative review record.")
    return "\n\n".join(body)


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
