"""Merge/apply gate service for merge gate.

Only the Merge Applier Agent may merge, and only after nexusctl-owned gates are green:
scoped patch, current PR head SHA, successful required policy checks, approved
software review, required business acceptance, no safety veto, and no open
critical GitHub alerts.
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
from nexusctl.adapters.github.pulls import GitHubPullMergeSpec, GitHubPullRequestsAdapter
from nexusctl.app.check_service import POLICY_GATE_ORDER, PolicyCheckService, patch_fingerprint
from nexusctl.app.github_service import GitHubProjectionConfig
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.domain.states import FeatureRequestStatus, WorkItemStatus
from nexusctl.storage.sqlite.repositories import RepositoryContext


class MergeService:
    """Apply a Nexus-approved patch through the GitHub merge projection."""

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
        self.pull_adapter = GitHubPullRequestsAdapter(self.github_client)

    def merge(self, subject: Subject, feature_request_or_pr_id: str) -> dict[str, Any]:
        patch = self._resolve_merge_target(feature_request_or_pr_id)
        self.policy.require(subject, "repo.apply", target_domain=patch["domain"], resource_domain=patch["domain"])
        if subject.agent_id != "merge-applier":
            raise PolicyDeniedError(
                "only the Merge Applier Agent may execute a merge",
                rule_id="merge_only_merge_applier",
            )
        if patch.get("repository_id") is None or patch.get("pull_number") is None:
            raise ValidationError("patch proposal has no GitHub PR projection; run `nexusctl github pr create` first")
        if self._existing_merge(patch) is not None:
            raise ValidationError(f"patch {patch['id']} is already merged")

        gate = self._merge_gate(subject, patch)
        if not gate["merge_allowed"]:
            raise PolicyDeniedError(gate["summary"], rule_id=gate["rule_id"])

        repository = self._repository(str(patch["repository_id"]))
        pull_number = int(patch["pull_number"])
        merge_spec = GitHubPullMergeSpec(
            method="squash",
            commit_title=f"[{patch['feature_request_id']}] {patch['summary']}",
            commit_message="Merged by Nexusctl after all merge gates passed.",
            expected_head_sha=gate["policy_check"]["current_head_sha"],
            details={
                "patch_id": patch["id"],
                "feature_request_id": patch["feature_request_id"],
                "work_item_id": patch["work_item_id"],
                "required_checks": gate["required_checks"],
            },
        )
        github_merge = self.pull_adapter.merge_pull_request(repository, pull_number=pull_number, spec=merge_spec)
        now = _utcnow_iso()
        merge_id = f"merge-{uuid4().hex}"
        merge_sha = str(github_merge.get("merge_sha") or github_merge.get("sha") or "")
        if not merge_sha:
            raise ValidationError("GitHub merge projection did not return a merge SHA")

        self.repositories.merges.create(
            merge_id=merge_id,
            patch_id=patch["id"],
            feature_request_id=patch["feature_request_id"],
            work_item_id=patch["work_item_id"],
            repository_id=repository.id,
            pull_number=pull_number,
            merged_by=subject.agent_id,
            merge_sha=merge_sha,
            status="merged",
            details_json=_json_dumps({"github_merge": github_merge, "policy_gate": gate}),
        )
        self.repositories.reviews.update_patch_status(patch_id=patch["id"], status="merged", updated_at=now)
        self.repositories.work_items.update_status(work_id=patch["work_item_id"], status=WorkItemStatus.DONE.value, updated_at=now)
        self.repositories.feature_requests.transition(request_id=patch["feature_request_id"], status=FeatureRequestStatus.CLOSED, updated_at=now)
        label_projection = self._project_merge_labels(patch, repository_id=repository.id, pull_number=pull_number, synced_at=now)
        event = self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=patch["id"],
            event_type="merge.applied",
            actor_id=subject.agent_id,
            payload={
                "merge_id": merge_id,
                "patch_id": patch["id"],
                "feature_request_id": patch["feature_request_id"],
                "work_item_id": patch["work_item_id"],
                "repository_id": repository.id,
                "pull_number": pull_number,
                "merge_sha": merge_sha,
                "github_merge": github_merge,
                "label_projection": label_projection,
            },
            metadata={"milestone": 12, "service": self.__class__.__name__},
        )
        fr_event = self.events.append(
            aggregate_type="feature_request",
            aggregate_id=patch["feature_request_id"],
            event_type="feature_request.merged",
            actor_id=subject.agent_id,
            payload={"merge_id": merge_id, "patch_id": patch["id"], "status": FeatureRequestStatus.CLOSED.value},
            metadata={"milestone": 12, "service": self.__class__.__name__},
        )
        return {
            "ok": True,
            "merge": {
                "id": merge_id,
                "patch_id": patch["id"],
                "feature_request_id": patch["feature_request_id"],
                "work_item_id": patch["work_item_id"],
                "repository_id": repository.id,
                "repository": repository.full_name,
                "pull_number": pull_number,
                "merged_by": subject.agent_id,
                "merge_sha": merge_sha,
                "status": "merged",
                "created_at": now,
            },
            "github_merge": github_merge,
            "policy_check": gate["policy_check"],
            "required_checks": gate["required_checks"],
            "label_projection": label_projection,
            "event_id": event.event_id,
            "feature_request_event_id": fr_event.event_id,
        }

    def _merge_gate(self, subject: Subject, patch: dict[str, Any]) -> dict[str, Any]:
        check_service = PolicyCheckService(self.connection, self.policy, self.project_root, github_client=self.github_client)
        evaluation = check_service.check(subject, patch["id"])
        if not evaluation["merge_allowed"]:
            return {
                "merge_allowed": False,
                "rule_id": "merge-gate_policy_gate_blocked",
                "summary": "merge blocked because one or more Nexus policy gates are not passing",
                "policy_check": evaluation,
                "required_checks": [],
                "critical_alerts": [],
            }

        checks = self._required_checks(evaluation)
        bad_checks = [check for check in checks if check["status"] != "passed"]
        if bad_checks:
            return {
                "merge_allowed": False,
                "rule_id": "required_checks_not_green",
                "summary": "merge blocked because required GitHub check projections are not green",
                "policy_check": evaluation,
                "required_checks": checks,
                "critical_alerts": [],
            }

        alerts = self._open_critical_alerts(patch)
        if alerts:
            return {
                "merge_allowed": False,
                "rule_id": "critical_github_alerts_block_merge",
                "summary": "merge blocked because open critical GitHub alerts exist",
                "policy_check": evaluation,
                "required_checks": checks,
                "critical_alerts": alerts,
            }

        return {
            "merge_allowed": True,
            "rule_id": None,
            "summary": "all merge gates passed",
            "policy_check": evaluation,
            "required_checks": checks,
            "critical_alerts": [],
        }

    def _required_checks(self, evaluation: dict[str, Any]) -> list[dict[str, Any]]:
        patch_id = evaluation["patch_id"]
        current_head_sha = evaluation["current_head_sha"]
        required_gate_names = [gate["name"] for gate in evaluation["gates"] if gate.get("required", True)]
        out: list[dict[str, Any]] = []
        for name in required_gate_names:
            policy = self.connection.execute(
                "SELECT * FROM policy_checks WHERE patch_id = ? AND name = ?",
                (patch_id, name),
            ).fetchone()
            github = self.connection.execute(
                """
                SELECT * FROM github_check_runs
                WHERE patch_id = ? AND name = ?
                ORDER BY synced_at DESC, id DESC
                LIMIT 1
                """,
                (patch_id, f"nexus/policy/{name}"),
            ).fetchone()
            reasons: list[str] = []
            if policy is None:
                reasons.append("missing policy_check row")
            else:
                if policy["status"] != "passed" or policy["conclusion"] != "success":
                    reasons.append(f"policy_check is {policy['status']}/{policy['conclusion']}")
                if policy["head_sha"] != current_head_sha:
                    reasons.append("policy_check head SHA is stale")
            if github is None:
                reasons.append("missing GitHub Check Run projection")
            else:
                if github["status"] != "completed" or github["conclusion"] != "success":
                    reasons.append(f"GitHub check is {github['status']}/{github['conclusion']}")
                if github["head_sha"] != current_head_sha:
                    reasons.append("GitHub check head SHA is stale")
            out.append(
                {
                    "name": name,
                    "status": "failed" if reasons else "passed",
                    "policy_check_id": None if policy is None else policy["id"],
                    "github_check_id": None if github is None else github["id"],
                    "head_sha": current_head_sha,
                    "reasons": reasons,
                }
            )
        # Keep output stable even if future gates are added out of order.
        order = {name: idx for idx, name in enumerate(POLICY_GATE_ORDER)}
        out.sort(key=lambda item: order.get(str(item["name"]), 999))
        return out

    def _open_critical_alerts(self, patch: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM github_alerts
            WHERE status = 'open'
              AND severity = 'critical'
              AND (
                patch_id = ?
                OR feature_request_id = ?
                OR (repository_id = ? AND pull_number = ?)
              )
            ORDER BY created_at ASC, id ASC
            """,
            (patch["id"], patch["feature_request_id"], patch["repository_id"], patch["pull_number"]),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "repository_id": row["repository_id"],
                "pull_number": row["pull_number"],
                "patch_id": row["patch_id"],
                "feature_request_id": row["feature_request_id"],
                "severity": row["severity"],
                "status": row["status"],
                "kind": row["kind"],
                "summary": row["summary"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _resolve_merge_target(self, identifier: str) -> dict[str, Any]:
        patch_id = self._resolve_patch_id(identifier)
        row = self.connection.execute(
            """
            SELECT
              p.*, w.feature_request_id, w.domain_id, w.assigned_agent_id, w.reviewer_agent_id,
              fr.source_domain_id, fr.target_domain_id, fr.acceptance_contract,
              pr.repository_id, pr.pull_number, pr.branch, pr.url AS pull_url,
              ps.head_sha, ps.validated_patch_sha
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
            (patch_id,),
        ).fetchone()
        if row is None:
            raise ValidationError(f"unknown merge target {identifier}")
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
            "submitted_by": row["submitted_by"],
            "scope_lease_id": row["scope_lease_id"],
            "status": row["status"],
            "summary": row["diff_summary"],
            "changed_paths": changed_paths,
            "diff": diff,
            "acceptance_contract": _json_object(row["acceptance_contract"]),
            "repository_id": row["repository_id"],
            "pull_number": row["pull_number"],
            "branch": row["branch"],
            "pull_url": row["pull_url"],
            "head_sha": row["head_sha"],
            "validated_patch_sha": row["validated_patch_sha"] or patch_fingerprint(diff),
        }

    def _resolve_patch_id(self, identifier: str) -> str:
        direct = self.connection.execute("SELECT id FROM patch_proposals WHERE id = ?", (identifier,)).fetchone()
        if direct is not None:
            return str(direct["id"])
        from_feature = self.connection.execute(
            """
            SELECT p.id
            FROM patch_proposals p
            JOIN work_items w ON w.id = p.work_item_id
            WHERE w.feature_request_id = ?
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT 1
            """,
            (identifier,),
        ).fetchone()
        if from_feature is not None:
            return str(from_feature["id"])
        from_link = self.connection.execute("SELECT patch_id FROM github_pull_links WHERE id = ?", (identifier,)).fetchone()
        if from_link is not None:
            return str(from_link["patch_id"])
        if identifier.isdigit():
            from_pull_number = self.connection.execute(
                "SELECT patch_id FROM github_pull_links WHERE pull_number = ? ORDER BY synced_at DESC, id DESC LIMIT 1",
                (int(identifier),),
            ).fetchone()
            if from_pull_number is not None:
                return str(from_pull_number["patch_id"])
        raise ValidationError(f"unknown feature request, patch proposal, or PR id {identifier}")

    def _existing_merge(self, patch: dict[str, Any]) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM merge_records
            WHERE patch_id = ? AND repository_id = ? AND pull_number = ? AND status = 'merged'
            LIMIT 1
            """,
            (patch["id"], patch["repository_id"], patch["pull_number"]),
        ).fetchone()

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

    def _project_merge_labels(self, patch: dict[str, Any], *, repository_id: str, pull_number: int, synced_at: str) -> dict[str, Any]:
        issue_labels = self._merge_labels(patch, pull_request=False)
        pull_labels = self._merge_labels(patch, pull_request=True)
        issue_rows: list[dict[str, Any]] = []
        for issue in self.connection.execute(
            "SELECT * FROM github_issue_links WHERE feature_request_id = ? ORDER BY synced_at DESC, id ASC",
            (patch["feature_request_id"],),
        ).fetchall():
            label_id = self._upsert_projection_labels(
                entity_kind="issue",
                nexus_entity_id=patch["feature_request_id"],
                repository_id=issue["repository_id"],
                external_number=int(issue["issue_number"]),
                labels=issue_labels,
                synced_at=synced_at,
            )
            issue_rows.append({"id": label_id, "repository_id": issue["repository_id"], "issue_number": issue["issue_number"], "labels": issue_labels})
        pr_label_id = self._upsert_projection_labels(
            entity_kind="pull_request",
            nexus_entity_id=patch["id"],
            repository_id=repository_id,
            external_number=pull_number,
            labels=pull_labels,
            synced_at=synced_at,
        )
        return {
            "issue_labels": issue_rows,
            "pull_request_labels": [{"id": pr_label_id, "repository_id": repository_id, "pull_number": pull_number, "patch_id": patch["id"], "labels": pull_labels}],
        }

    def _merge_labels(self, patch: dict[str, Any], *, pull_request: bool) -> list[str]:
        labels = [
            f"nexus:{patch['feature_request_id']}",
            f"domain:{patch['source_domain']}",
            f"target:{patch['target_domain']}",
            "status:merged",
            "gate:review-approved",
        ]
        if patch["source_domain"] == "trading" or patch.get("acceptance_contract"):
            labels.append("gate:acceptance-accepted")
        if pull_request:
            labels.append(f"patch:{patch['id']}")
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


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


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
