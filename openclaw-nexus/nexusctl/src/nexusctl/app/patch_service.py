"""Patch proposal service for patch proposal workflow.

Builders submit scoped patch proposals from local worktrees.  Nexusctl compares
that worktree with the canonical project root, validates every changed path
against the builder's active scope lease, stores the proposal, and later lets the
GitHub-App boundary project it as a branch and pull request.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.adapters.git.applier import BranchProjector
from nexusctl.adapters.git.diff import WorktreeDiff, diff_worktree
from nexusctl.adapters.git.worktree import branch_for_work, plan_worktree_start
from nexusctl.adapters.github.app_auth import GitHubAppAuthenticator
from nexusctl.adapters.github.client import GitHubClient, GitHubPullRequestSpec, MockGitHubClient
from nexusctl.app.github_service import GitHubProjectionConfig
from nexusctl.app.check_service import patch_fingerprint
from nexusctl.app.scope_service import ScopeService
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.domain.states import WorkItemStatus
from nexusctl.storage.sqlite.repositories import RepositoryContext


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored patch JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("stored patch JSON must be an object")
    return data


class PatchService:
    """Application service for scoped patch proposals and PR projection."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        policy: PolicyEngine,
        project_root: str | Path,
        *,
        github_client: GitHubClient | None = None,
        branch_projector: BranchProjector | None = None,
    ) -> None:
        self.connection = connection
        self.policy = policy
        self.project_root = Path(project_root).resolve()
        self.repositories = RepositoryContext(connection)
        self.events = self.repositories.events
        self.github_config = GitHubProjectionConfig.from_project_root(self.project_root)
        self.github_config.assert_projection_guardrails()
        self.github_client = github_client or MockGitHubClient(GitHubAppAuthenticator.from_env())
        self.branch_projector = branch_projector or BranchProjector()

    def start_work(self, subject: Subject, work_item_id: str) -> dict[str, Any]:
        work = self._get_work(work_item_id)
        self.policy.require(subject, "work.read", resource_domain=work["domain_id"])
        if subject.agent_id not in {work["assigned_agent_id"], work["reviewer_agent_id"]} and subject.domain == work["domain_id"]:
            # Same-domain planners can inspect, but only the assigned builder starts implementation.
            if subject.agent_id != work["assigned_agent_id"]:
                raise PolicyDeniedError("only the assigned builder can start implementation work", rule_id="work_start_builder_bound")
        elif subject.agent_id != work["assigned_agent_id"]:
            raise PolicyDeniedError("only the assigned builder can start implementation work", rule_id="work_start_builder_bound")
        now = _utcnow_iso()
        self.repositories.patches.update_work_status(
            work_item_id=work_item_id, status=WorkItemStatus.IN_PROGRESS.value, updated_at=now
        )
        plan = plan_worktree_start(self.project_root, work_item_id, work["feature_request_id"]).to_json()
        event = self.events.append(
            aggregate_type="work_item",
            aggregate_id=work_item_id,
            event_type="work_item.started",
            actor_id=subject.agent_id,
            payload={"work_item_id": work_item_id, "feature_request_id": work["feature_request_id"], "branch": plan["branch"]},
            metadata={"milestone": 9, "service": self.__class__.__name__},
        )
        return {"work_item_id": work_item_id, "status": WorkItemStatus.IN_PROGRESS.value, "worktree": plan, "event_id": event.event_id}

    def submit(self, subject: Subject, work_or_request_id: str, *, from_worktree: str | Path) -> dict[str, Any]:
        work = self._resolve_work(work_or_request_id)
        if work["assigned_agent_id"] != subject.agent_id:
            raise PolicyDeniedError("only the assigned builder can submit this patch", rule_id="patch_submit_builder_bound")
        self.policy.require(subject, "patch.submit", resource_domain=work["domain_id"])
        lease = self._active_lease_for_builder(subject, work)
        candidate = diff_worktree(self.project_root, from_worktree)
        if not candidate.files:
            raise ValidationError("patch proposal contains no changed files")
        scope_service = ScopeService(self.connection, self.policy)
        for path in candidate.changed_paths:
            scope_service.assert_usable(subject, lease_id=lease["id"], capability_id="patch.submit", path=path)
        patch_id = f"patch-{uuid4().hex}"
        now = _utcnow_iso()
        branch = branch_for_work(work["id"], work["feature_request_id"])
        diff_json = candidate.to_json()
        diff_json["branch"] = branch
        self.repositories.patches.create(
            patch_id=patch_id,
            work_item_id=work["id"],
            submitted_by=subject.agent_id,
            scope_lease_id=lease["id"],
            status="submitted",
            diff_summary=candidate.summary(),
            diff_json=_json_dumps(diff_json),
            created_at=now,
            updated_at=now,
        )
        self.repositories.patches.update_work_status(
            work_item_id=work["id"], status=WorkItemStatus.PATCH_SUBMITTED.value, updated_at=now
        )
        event = self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=patch_id,
            event_type="patch.submitted",
            actor_id=subject.agent_id,
            payload={
                "patch_id": patch_id,
                "work_item_id": work["id"],
                "feature_request_id": work["feature_request_id"],
                "scope_lease_id": lease["id"],
                "changed_paths": list(candidate.changed_paths),
                "summary": candidate.summary(),
                "branch": branch,
            },
            metadata={"milestone": 9, "service": self.__class__.__name__},
        )
        body = self._get_patch(patch_id)
        body["event_id"] = event.event_id
        return body

    def show(self, subject: Subject, patch_id: str) -> dict[str, Any]:
        patch = self._get_patch(patch_id)
        self.policy.require(subject, "patch.read", resource_domain=patch["domain"])
        return patch

    def create_pr(self, subject: Subject, patch_id: str) -> dict[str, Any]:
        patch = self._get_patch(patch_id)
        self.policy.require(subject, "github.pr.create", target_domain=patch["domain"], resource_domain=patch["domain"])
        repository = self.github_config.default_repository()
        self.repositories.patches.upsert_repository(
            repository_id=repository.id, owner=repository.owner, name=repository.name,
            default_branch=repository.default_branch, visibility=repository.visibility
        )
        diff_data = patch["diff"]
        branch = str(diff_data.get("branch") or branch_for_work(patch["work_item_id"], patch["feature_request_id"]))
        projection = self.branch_projector.project_patch_branch(branch=branch, changed_paths=tuple(patch["changed_paths"]))
        pr_spec = GitHubPullRequestSpec(
            title=f"[{patch['feature_request_id']}] {patch['summary']}",
            body=self._pr_body(patch, projection.to_json()),
            head=branch,
            base=repository.default_branch,
            labels=(f"nexus:{patch['feature_request_id']}", f"patch:{patch_id}", "status:patch-submitted"),
        )
        existing = self._get_pull_link(patch_id, repository.id)
        pull = self.github_client.create_or_update_pull_request(
            repository,
            pr_spec,
            existing_pull_number=existing["pull_number"] if existing else None,
        )
        synced_at = _utcnow_iso()
        validated_patch_sha = patch_fingerprint(diff_data)
        # policy check workflow stores the PR head we validated. In mock/local operation the
        # projected branch is represented by the canonical patch fingerprint; a
        # later changed head SHA forces policy checks to fail until revalidated.
        head_sha = validated_patch_sha
        if existing is None:
            link_id = f"gh-pr-{uuid4().hex}"
            self.repositories.patches.insert_pull_link(
                link_id=link_id, patch_id=patch_id, repository_id=repository.id,
                pull_number=pull["number"], branch=branch, url=pull.get("url"), synced_at=synced_at
            )
        else:
            link_id = existing["id"]
            self.repositories.patches.update_pull_link(
                link_id=link_id, pull_number=pull["number"], branch=branch, url=pull.get("url"), synced_at=synced_at
            )
        state_id = f"gh-pr-state-{uuid4().hex}"
        self.repositories.patches.upsert_pull_state(
            state_id=state_id, patch_id=patch_id, repository_id=repository.id, pull_number=pull["number"],
            head_sha=head_sha, validated_patch_sha=validated_patch_sha, synced_at=synced_at
        )
        event = self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=patch_id,
            event_type="github.pr.created",
            actor_id=subject.agent_id,
            payload={
                "patch_id": patch_id,
                "repository_id": repository.id,
                "repository": repository.full_name,
                "pull_number": pull["number"],
                "branch": branch,
                "url": pull.get("url"),
                "branch_projection": projection.to_json(),
                "head_sha": head_sha,
                "validated_patch_sha": validated_patch_sha,
            },
            metadata={"milestone": 9, "service": self.__class__.__name__},
        )
        return {
            "ok": True,
            "patch_id": patch_id,
            "feature_request_id": patch["feature_request_id"],
            "github_pr": {
                "id": link_id,
                "repository_id": repository.id,
                "repository": repository.full_name,
                "pull_number": pull["number"],
                "branch": branch,
                "base": repository.default_branch,
                "url": pull.get("url"),
                "title": pr_spec.title,
                "labels": list(pr_spec.labels),
                "synced_at": synced_at,
                "mock_status": pull.get("status"),
                "branch_projection": projection.to_json(),
                "head_sha": head_sha,
                "validated_patch_sha": validated_patch_sha,
            },
            "event_id": event.event_id,
        }

    def _pr_body(self, patch: dict[str, Any], branch_projection: dict[str, Any]) -> str:
        return "\n\n".join(
            [
                "## Nexus Patch Proposal",
                f"Patch: `{patch['id']}`",
                f"Work Item: `{patch['work_item_id']}`",
                f"Feature Request: `{patch['feature_request_id']}`",
                f"Scope Lease: `{patch['scope_lease_id']}`",
                f"Summary: {patch['summary']}",
                "## Changed Paths\n" + "\n".join(f"- `{path}`" for path in patch["changed_paths"]),
                "## Authority\nGitHub is a projection only. Nexusctl owns patch, review, acceptance, and merge gates.",
                "## Branch Projection\n```json\n" + json.dumps(branch_projection, sort_keys=True, indent=2) + "\n```",
            ]
        )

    def _resolve_work(self, work_or_request_id: str) -> sqlite3.Row:
        row = self.repositories.patches.resolve_work(work_or_request_id)
        if row is None:
            raise ValidationError(f"unknown work item or feature request {work_or_request_id}")
        return row

    def _get_work(self, work_item_id: str) -> sqlite3.Row:
        row = self.repositories.patches.get_work(work_item_id)
        if row is None:
            raise ValidationError(f"unknown work item {work_item_id}")
        return row

    def _active_lease_for_builder(self, subject: Subject, work: sqlite3.Row) -> dict[str, Any]:
        row = self.repositories.patches.active_lease_for_builder(work_item_id=work["id"], agent_id=subject.agent_id)
        if row is None:
            raise PolicyDeniedError("assigned builder has no active scope lease", rule_id="patch_requires_active_scope_lease")
        # Show/usable path checks below will mark expired leases before accepting paths.
        return {"id": row["id"]}

    def _get_patch(self, patch_id: str) -> dict[str, Any]:
        row = self.repositories.patches.get_with_work(patch_id)
        if row is None:
            raise ValidationError(f"unknown patch proposal {patch_id}")
        diff_data = _json_loads(row["diff_json"])
        changed_paths = diff_data.get("changed_paths") or []
        if not isinstance(changed_paths, list):
            raise ValidationError("stored patch changed_paths must be a list")
        pr_link = self._get_pull_link(patch_id, self.github_config.default_repository().id)
        return {
            "id": row["id"],
            "work_item_id": row["work_item_id"],
            "feature_request_id": row["feature_request_id"],
            "domain": row["domain_id"],
            "submitted_by": row["submitted_by"],
            "scope_lease_id": row["scope_lease_id"],
            "status": row["status"],
            "summary": row["diff_summary"],
            "changed_paths": changed_paths,
            "diff": diff_data,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "github_pr": dict(pr_link) if pr_link else None,
        }

    def _get_pull_link(self, patch_id: str, repository_id: str) -> sqlite3.Row | None:
        return self.repositories.patches.get_pull_link(patch_id=patch_id, repository_id=repository_id)
