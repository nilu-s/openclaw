"""GitHub projection service for GitHub projection workflow.

Feature Requests remain Nexusctl-owned state. This service projects them to
GitHub Issues through a mockable adapter, records database links, and appends
Nexus events for every projection mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

import yaml

from nexusctl.adapters.github.app_auth import GitHubAppAuthenticator
from nexusctl.adapters.github.client import GitHubClient, GitHubIssueSpec, GitHubLabelSpec, GitHubRepositoryRef, MockGitHubClient
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.storage.event_store import EventStore


def _json_loads(value: str | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("stored JSON value must be an object")
    return data


def _json_pretty(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, indent=2)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _status_label_value(status: str) -> str:
    return status.replace("_", "-")


@dataclass(frozen=True, slots=True)
class GitHubProjectionConfig:
    repositories: tuple[GitHubRepositoryRef, ...]
    labels: tuple[GitHubLabelSpec, ...]
    feature_request_sections: tuple[str, ...]
    source_of_truth: str
    role: str
    lifecycle_authority: bool
    agents_have_direct_write_tokens: bool

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "GitHubProjectionConfig":
        path = Path(project_root) / "nexus" / "github.yml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValidationError("nexus/github.yml must contain a mapping")
        github = data.get("github") or {}
        repositories = tuple(
            GitHubRepositoryRef(
                id=repo["id"],
                owner=repo.get("owner", ""),
                name=repo.get("name", repo["id"]),
                default_branch=repo.get("default_branch", "main"),
                visibility=repo.get("visibility", "private_or_internal"),
            )
            for repo in github.get("repositories", [])
        )
        labels = tuple(
            GitHubLabelSpec(
                name=label["name"],
                description=label.get("description", ""),
                color=label.get("color"),
            )
            for label in github.get("labels", [])
        )
        sections = tuple(
            (github.get("mappings") or {})
            .get("feature_request", {})
            .get("body_sections", ("summary", "source_domain", "target_domain", "goal", "acceptance_contract", "safety_contract"))
        )
        return cls(
            repositories=repositories,
            labels=labels,
            feature_request_sections=sections,
            source_of_truth=github.get("source_of_truth", ""),
            role=github.get("role", ""),
            lifecycle_authority=bool(github.get("lifecycle_authority", True)),
            agents_have_direct_write_tokens=bool(github.get("agents_have_direct_write_tokens", True)),
        )

    def default_repository(self) -> GitHubRepositoryRef:
        if not self.repositories:
            raise ValidationError("nexus/github.yml defines no repositories")
        return self.repositories[0]

    def assert_projection_guardrails(self) -> None:
        if self.role != "projection" or self.source_of_truth != "nexusctl" or self.lifecycle_authority:
            raise ValidationError("github.yml must mark GitHub as projection with Nexusctl lifecycle authority")
        if self.agents_have_direct_write_tokens:
            raise ValidationError("github.yml must forbid direct GitHub write tokens for agents")


class GitHubService:
    """Application service for GitHub repository, label, and issue projection."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        policy: PolicyEngine,
        project_root: str | Path,
        *,
        client: GitHubClient | None = None,
    ) -> None:
        self.connection = connection
        self.policy = policy
        self.project_root = Path(project_root)
        self.config = GitHubProjectionConfig.from_project_root(self.project_root)
        self.config.assert_projection_guardrails()
        self.client = client or MockGitHubClient(GitHubAppAuthenticator.from_env())
        self.events = EventStore(connection)

    def app_status(self, subject: Subject) -> dict[str, Any]:
        self.policy.require(subject, "github.issue.sync", resource_domain=subject.domain)
        status = self.client.app_status()
        status.update(
            {
                "source_of_truth": self.config.source_of_truth,
                "role": self.config.role,
                "lifecycle_authority": self.config.lifecycle_authority,
                "agents_have_direct_write_tokens": self.config.agents_have_direct_write_tokens,
            }
        )
        return {"ok": True, "github_app": status}

    def sync_repositories(self, subject: Subject) -> dict[str, Any]:
        self.policy.require(subject, "github.repo.sync", resource_domain=subject.domain)
        synced: list[dict[str, Any]] = []
        for repository in self.config.repositories:
            self.connection.execute(
                """
                INSERT INTO github_repositories(id, owner, name, default_branch, visibility)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  owner=excluded.owner,
                  name=excluded.name,
                  default_branch=excluded.default_branch,
                  visibility=excluded.visibility
                """,
                (repository.id, repository.owner, repository.name, repository.default_branch, repository.visibility),
            )
            synced.append(self.client.sync_repository(repository))
        event = self.events.append(
            aggregate_type="github",
            aggregate_id="repositories",
            event_type="github.repositories.synced",
            actor_id=subject.agent_id,
            payload={"repositories": synced},
            metadata={"milestone": 7, "source": "nexus/github.yml"},
        )
        return {"ok": True, "repositories": synced, "event_id": event.event_id}

    def sync_labels(self, subject: Subject) -> dict[str, Any]:
        self.policy.require(subject, "github.label.sync", resource_domain=subject.domain)
        repository = self._ensure_default_repository()
        labels = [self.client.sync_label(repository, label) for label in self.config.labels]
        event = self.events.append(
            aggregate_type="github",
            aggregate_id="labels",
            event_type="github.labels.synced",
            actor_id=subject.agent_id,
            payload={"repository": repository.full_name, "labels": labels},
            metadata={"milestone": 7, "source": "nexus/github.yml"},
        )
        return {"ok": True, "repository": repository.full_name, "labels": labels, "event_id": event.event_id}

    def sync_feature_request_issue(self, subject: Subject, feature_request_id: str) -> dict[str, Any]:
        request = self._get_feature_request(feature_request_id)
        self.policy.require(
            subject,
            "github.issue.sync",
            target_domain=request["target_domain"],
            resource_domain=request["target_domain"],
        )
        repository = self._ensure_default_repository()
        existing = self._get_issue_link(feature_request_id, repository.id)
        issue_spec = self._issue_spec(request)
        issue = self.client.create_or_update_issue(
            repository,
            issue_spec,
            existing_issue_number=existing["issue_number"] if existing else None,
        )
        synced_at = _utcnow_iso()
        if existing is None:
            link_id = f"gh-issue-{uuid4().hex}"
            self.connection.execute(
                """
                INSERT INTO github_issue_links(id, feature_request_id, repository_id, issue_number, url, synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (link_id, feature_request_id, repository.id, issue["number"], issue.get("url"), synced_at),
            )
        else:
            link_id = existing["id"]
            self.connection.execute(
                """
                UPDATE github_issue_links
                SET issue_number = ?, url = ?, synced_at = ?
                WHERE id = ?
                """,
                (issue["number"], issue.get("url"), synced_at, link_id),
            )
        event = self.events.append(
            aggregate_type="feature_request",
            aggregate_id=feature_request_id,
            event_type="github.issue.synced",
            actor_id=subject.agent_id,
            payload={
                "feature_request_id": feature_request_id,
                "repository_id": repository.id,
                "repository": repository.full_name,
                "issue_number": issue["number"],
                "url": issue.get("url"),
                "labels": list(issue_spec.labels),
                "status": issue.get("status"),
            },
            metadata={"milestone": 7, "source": "nexus/github.yml"},
        )
        return {
            "ok": True,
            "feature_request_id": feature_request_id,
            "github_issue": {
                "id": link_id,
                "repository_id": repository.id,
                "repository": repository.full_name,
                "issue_number": issue["number"],
                "url": issue.get("url"),
                "title": issue_spec.title,
                "body": issue_spec.body,
                "labels": list(issue_spec.labels),
                "synced_at": synced_at,
                "mock_status": issue.get("status"),
            },
            "event_id": event.event_id,
        }

    def _ensure_default_repository(self) -> GitHubRepositoryRef:
        repository = self.config.default_repository()
        self.connection.execute(
            """
            INSERT INTO github_repositories(id, owner, name, default_branch, visibility)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              owner=excluded.owner,
              name=excluded.name,
              default_branch=excluded.default_branch,
              visibility=excluded.visibility
            """,
            (repository.id, repository.owner, repository.name, repository.default_branch, repository.visibility),
        )
        return repository

    def _get_feature_request(self, feature_request_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM feature_requests WHERE id = ?", (feature_request_id,)).fetchone()
        if row is None:
            raise ValidationError(f"unknown feature request {feature_request_id}")
        return {
            "id": row["id"],
            "source_domain": row["source_domain_id"],
            "target_domain": row["target_domain_id"],
            "created_by": row["created_by"],
            "goal_id": row["goal_id"],
            "summary": row["summary"],
            "title": row["summary"],
            "status": row["status"],
            "acceptance_contract": _json_loads(row["acceptance_contract"]),
            "safety_contract": _json_loads(row["safety_contract"]),
            "dedupe_key": row["dedupe_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _get_issue_link(self, feature_request_id: str, repository_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM github_issue_links
            WHERE feature_request_id = ? AND repository_id = ?
            ORDER BY synced_at DESC, id ASC
            LIMIT 1
            """,
            (feature_request_id, repository_id),
        ).fetchone()

    def _issue_spec(self, request: dict[str, Any]) -> GitHubIssueSpec:
        labels = (
            f"nexus:{request['id']}",
            f"domain:{request['source_domain']}",
            f"target:{request['target_domain']}",
            f"status:{_status_label_value(request['status'])}",
        )
        return GitHubIssueSpec(
            title=f"[{request['source_domain']} -> {request['target_domain']}] {request['title']}",
            body=self._issue_body(request),
            labels=labels,
        )

    def _issue_body(self, request: dict[str, Any]) -> str:
        sections: list[str] = []
        for section in self.config.feature_request_sections:
            if section == "summary":
                sections.append(f"## Summary\n\n{request['summary']}")
            elif section == "source_domain":
                sections.append(f"## Source Domain\n\n`{request['source_domain']}`")
            elif section == "target_domain":
                sections.append(f"## Target Domain\n\n`{request['target_domain']}`")
            elif section == "goal":
                sections.append(f"## Goal\n\n`{request['goal_id'] or 'none'}`")
            elif section == "acceptance_contract":
                sections.append(f"## Acceptance Contract\n\n```json\n{_json_pretty(request['acceptance_contract'])}\n```")
            elif section == "safety_contract":
                sections.append(f"## Safety Contract\n\n```json\n{_json_pretty(request['safety_contract'])}\n```")
        sections.append(
            "## Nexus Authority\n\nGitHub is a projection only. Nexusctl remains the lifecycle source of truth."
        )
        return "\n\n".join(sections)
