"""Policy checks and GitHub Check Run synchronization for policy check workflow.

Nexusctl evaluates merge-relevant gates from its own source-of-truth tables and
can project those results to GitHub Check Runs.  GitHub remains a projection:
policy decisions are derived from Nexusctl state, then mirrored outward.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.adapters.github.app_auth import GitHubAppAuthenticator
from nexusctl.adapters.github.checks import GitHubCheckRunSpec, GitHubChecksAdapter
from nexusctl.adapters.github.client import GitHubClient, GitHubRepositoryRef, MockGitHubClient
from nexusctl.app.github_service import GitHubProjectionConfig
from nexusctl.app.scope_service import PathScope
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import ValidationError
from nexusctl.storage.sqlite.repositories import RepositoryContext


POLICY_GATE_ORDER: tuple[str, ...] = (
    "scope_respected",
    "required_review",
    "acceptance",
    "no_safety_veto",
    "head_sha_matches_validated_patch",
)


@dataclass(frozen=True, slots=True)
class PolicyGate:
    name: str
    status: str
    summary: str
    required: bool = True
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.name not in POLICY_GATE_ORDER:
            raise ValidationError(f"unknown policy gate {self.name}")
        if self.status not in {"passed", "pending", "failed"}:
            raise ValidationError("policy gate status must be passed, pending, or failed")

    @property
    def conclusion(self) -> str:
        return {"passed": "success", "pending": "pending", "failed": "failure"}[self.status]

    @property
    def check_status(self) -> str:
        return "completed" if self.status in {"passed", "failed"} else "in_progress"

    @property
    def github_conclusion(self) -> str | None:
        if self.status == "pending":
            return None
        return "success" if self.status == "passed" else "failure"

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "conclusion": self.conclusion,
            "required": self.required,
            "summary": self.summary,
            "details": dict(self.details or {}),
        }


class PolicyCheckService:
    """Evaluate Nexus policy gates and sync them to GitHub checks."""

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
        self.checks_adapter = GitHubChecksAdapter(self.github_client)

    def check(self, subject: Subject, patch_id: str) -> dict[str, Any]:
        patch = self._get_patch_with_pr(patch_id)
        self.policy.require(subject, "policy.check", resource_domain=patch["domain"])
        return self._evaluate_patch(patch)

    def sync_github_checks(self, subject: Subject, patch_id: str) -> dict[str, Any]:
        patch = self._get_patch_with_pr(patch_id)
        self.policy.require(subject, "github.check.sync", target_domain=patch["domain"], resource_domain=patch["domain"])
        if patch["repository_id"] is None or patch["pull_number"] is None:
            raise ValidationError("patch proposal has no GitHub PR projection; run `nexusctl github pr create` first")

        evaluation = self._evaluate_patch(patch)
        repository = self._repository(str(patch["repository_id"]))
        pull_number = int(patch["pull_number"])
        now = _utcnow_iso()
        check_runs: list[dict[str, Any]] = []
        for gate in evaluation["gates"]:
            gate_payload = dict(gate)
            policy_check_id = self._upsert_policy_check(
                patch_id=patch_id,
                gate=gate_payload,
                head_sha=evaluation["current_head_sha"],
                checked_at=now,
            )
            spec = GitHubCheckRunSpec(
                name=f"nexus/policy/{gate['name']}",
                status="completed" if gate["status"] in {"passed", "failed"} else "in_progress",
                conclusion=None if gate["status"] == "pending" else ("success" if gate["status"] == "passed" else "failure"),
                head_sha=evaluation["current_head_sha"],
                summary=gate["summary"],
                details={"policy_check_id": policy_check_id, **gate_payload},
            )
            synced = self.checks_adapter.sync_check_run(repository, pull_number=pull_number, spec=spec)
            github_check_id = self._upsert_github_check_run(
                patch_id=patch_id,
                repository_id=repository.id,
                pull_number=pull_number,
                spec=spec,
                external=synced,
                synced_at=now,
            )
            synced["id"] = github_check_id
            synced["policy_check_id"] = policy_check_id
            check_runs.append(synced)

        event = self.events.append(
            aggregate_type="patch_proposal",
            aggregate_id=patch_id,
            event_type="github.checks.synced",
            actor_id=subject.agent_id,
            payload={
                "patch_id": patch_id,
                "repository_id": repository.id,
                "pull_number": pull_number,
                "current_head_sha": evaluation["current_head_sha"],
                "validated_patch_sha": evaluation["validated_patch_sha"],
                "overall_status": evaluation["overall_status"],
                "merge_allowed": evaluation["merge_allowed"],
                "checks": check_runs,
            },
            metadata={"milestone": 10, "service": self.__class__.__name__},
        )
        return {
            "ok": True,
            "patch_id": patch_id,
            "feature_request_id": evaluation["feature_request_id"],
            "policy_check": evaluation,
            "github_checks": check_runs,
            "event_id": event.event_id,
        }

    def _evaluate_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        diff = patch["diff"]
        validated_patch_sha = patch_fingerprint(diff)
        current_head_sha = patch.get("head_sha") or validated_patch_sha
        gates = [
            self._gate_scope_respected(patch),
            self._gate_required_review(patch),
            self._gate_acceptance(patch),
            self._gate_no_safety_veto(patch),
            self._gate_head_sha(patch, validated_patch_sha=validated_patch_sha, current_head_sha=current_head_sha),
        ]
        failed = [gate.name for gate in gates if gate.status == "failed" and gate.required]
        pending = [gate.name for gate in gates if gate.status == "pending" and gate.required]
        merge_allowed = not failed and not pending
        if failed:
            overall = "failed"
        elif pending:
            overall = "pending"
        else:
            overall = "passed"
        return {
            "patch_id": patch["id"],
            "work_item_id": patch["work_item_id"],
            "feature_request_id": patch["feature_request_id"],
            "domain": patch["domain"],
            "repository_id": patch.get("repository_id"),
            "pull_number": patch.get("pull_number"),
            "current_head_sha": current_head_sha,
            "validated_patch_sha": validated_patch_sha,
            "overall_status": overall,
            "merge_allowed": merge_allowed,
            "failed_gates": failed,
            "pending_gates": pending,
            "gates": [gate.to_json() for gate in gates],
        }

    def _gate_scope_respected(self, patch: dict[str, Any]) -> PolicyGate:
        lease_id = patch.get("scope_lease_id")
        changed_paths = patch.get("changed_paths") or []
        if not lease_id:
            return PolicyGate("scope_respected", "failed", "patch has no scope lease", details={"changed_paths": changed_paths})
        lease = self.repositories.scope_leases.get(lease_id)
        if lease is None:
            return PolicyGate("scope_respected", "failed", "scope lease does not exist", details={"scope_lease_id": lease_id})
        try:
            patterns = _json_list(lease["paths_json"])
            capabilities = _json_list(lease["capabilities_json"])
            path_scope = PathScope.from_patterns(patterns)
        except Exception as exc:  # pragma: no cover - corrupt persisted JSON
            return PolicyGate("scope_respected", "failed", f"stored scope lease is invalid: {exc}", details={"scope_lease_id": lease_id})
        out_of_scope = [path for path in changed_paths if not path_scope.allows(path)]
        if out_of_scope:
            return PolicyGate(
                "scope_respected",
                "failed",
                "patch includes paths outside the leased scope",
                details={"scope_lease_id": lease_id, "out_of_scope_paths": out_of_scope, "patterns": patterns},
            )
        if "patch.submit" not in capabilities:
            return PolicyGate(
                "scope_respected",
                "failed",
                "scope lease did not grant patch.submit",
                details={"scope_lease_id": lease_id, "capabilities": capabilities},
            )
        return PolicyGate(
            "scope_respected",
            "passed",
            "changed paths match the submitted scope lease",
            details={"scope_lease_id": lease_id, "changed_paths": changed_paths, "patterns": patterns},
        )

    def _gate_required_review(self, patch: dict[str, Any]) -> PolicyGate:
        rows = self.repositories.reviews.list_for_patch(patch["id"])
        if not rows:
            return PolicyGate("required_review", "pending", "technical review is still pending", details={"review_count": 0})
        latest = rows[0]
        status = str(latest["status"])
        verdict = str(latest["verdict"] or "")
        if status == "approved" or verdict == "approved":
            return PolicyGate("required_review", "passed", "technical review is approved", details={"review_id": latest["id"], "reviewer": latest["reviewer_agent_id"]})
        if status in {"rejected", "changes_requested"} or verdict in {"rejected", "changes-requested", "changes_requested"}:
            return PolicyGate("required_review", "failed", "technical review blocks this patch", details={"review_id": latest["id"], "status": status, "verdict": verdict})
        return PolicyGate("required_review", "pending", "technical review is still pending", details={"review_id": latest["id"], "status": status})

    def _gate_acceptance(self, patch: dict[str, Any]) -> PolicyGate:
        required = patch["source_domain"] == "trading" or bool(patch.get("acceptance_contract"))
        rows = self.repositories.acceptances.list_for_feature_request(patch["feature_request_id"])
        statuses = [str(row["status"]) for row in rows]
        if "rejected" in statuses:
            return PolicyGate("acceptance", "failed", "business-domain acceptance rejected the request", required=required, details={"statuses": statuses})
        if "accepted" in statuses:
            return PolicyGate("acceptance", "passed", "business-domain acceptance is present", required=required, details={"statuses": statuses})
        if required:
            return PolicyGate("acceptance", "pending", "business-domain acceptance is pending", required=True, details={"statuses": statuses})
        return PolicyGate("acceptance", "passed", "business-domain acceptance is not required", required=False, details={"statuses": statuses})

    def _gate_no_safety_veto(self, patch: dict[str, Any]) -> PolicyGate:
        veto = self.repositories.acceptances.latest_veto_for_feature_request(patch["feature_request_id"])
        if veto is not None:
            return PolicyGate("no_safety_veto", "failed", "a safety veto blocks this patch", details={"acceptance_id": veto["id"], "submitted_by": veto["submitted_by"]})
        return PolicyGate("no_safety_veto", "passed", "no safety veto is recorded", details={})

    def _gate_head_sha(self, patch: dict[str, Any], *, validated_patch_sha: str, current_head_sha: str) -> PolicyGate:
        if patch.get("pull_number") is None:
            return PolicyGate(
                "head_sha_matches_validated_patch",
                "pending",
                "no GitHub PR head SHA is recorded yet",
                details={"validated_patch_sha": validated_patch_sha},
            )
        if current_head_sha == validated_patch_sha:
            return PolicyGate(
                "head_sha_matches_validated_patch",
                "passed",
                "PR head SHA matches the validated patch fingerprint",
                details={"head_sha": current_head_sha, "validated_patch_sha": validated_patch_sha},
            )
        return PolicyGate(
            "head_sha_matches_validated_patch",
            "failed",
            "PR head SHA changed after Nexusctl validated the patch",
            details={"head_sha": current_head_sha, "validated_patch_sha": validated_patch_sha},
        )

    def _get_patch_with_pr(self, patch_id: str) -> dict[str, Any]:
        row = self.repositories.patches.get_with_pr(patch_id)
        if row is None:
            raise ValidationError(f"unknown patch proposal {patch_id}")
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
            "stored_validated_patch_sha": row["validated_patch_sha"],
        }

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

    def _upsert_policy_check(self, *, patch_id: str, gate: dict[str, Any], head_sha: str, checked_at: str) -> str:
        details_json = _json_dumps(gate)
        return self.repositories.policy_checks.upsert_policy_check(
            check_id=f"policy-check-{uuid4().hex}",
            patch_id=patch_id,
            name=gate["name"],
            status=gate["status"],
            conclusion=gate["conclusion"],
            required=bool(gate["required"]),
            head_sha=head_sha,
            details_json=details_json,
            checked_at=checked_at,
        )

    def _upsert_github_check_run(
        self,
        *,
        patch_id: str,
        repository_id: str,
        pull_number: int,
        spec: GitHubCheckRunSpec,
        external: dict[str, Any],
        synced_at: str,
    ) -> str:
        details_json = _json_dumps({"spec": spec.to_json(), "external": external})
        external_id = str(external.get("id") or external.get("number") or "") or None
        return self.repositories.policy_checks.upsert_github_check_run(
            check_id=f"gh-check-{uuid4().hex}",
            patch_id=patch_id,
            repository_id=repository_id,
            pull_number=pull_number,
            name=spec.name,
            status=spec.status,
            conclusion=spec.conclusion,
            head_sha=spec.head_sha,
            external_id=external_id,
            url=external.get("url"),
            details_json=details_json,
            synced_at=synced_at,
        )


def patch_fingerprint(diff: dict[str, Any]) -> str:
    stable = json.dumps(diff, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(stable).hexdigest()


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


def _json_list(value: str | None) -> list[str]:
    if value in (None, ""):
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored JSON is invalid: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValidationError("stored JSON must be a list of strings")
    return data
