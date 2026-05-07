"""Mockable GitHub client boundary for Nexusctl projections.

The GitHub projection client keeps all GitHub writes behind a Nexusctl-owned adapter. The
``MockGitHubClient`` is deterministic and network-free so tests and local CLI
usage do not require GitHub credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Protocol

from .app_auth import GitHubAppAuthenticator


@dataclass(frozen=True, slots=True)
class GitHubRepositoryRef:
    id: str
    owner: str
    name: str
    default_branch: str = "main"
    visibility: str = "private_or_internal"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}" if self.owner else self.name


@dataclass(frozen=True, slots=True)
class GitHubLabelSpec:
    name: str
    description: str = ""
    color: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubIssueSpec:
    title: str
    body: str
    labels: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class GitHubPullRequestSpec:
    title: str
    body: str
    head: str
    base: str
    labels: tuple[str, ...] = field(default_factory=tuple)


class GitHubClient(Protocol):
    """Protocol implemented by mock and future real GitHub clients."""

    def app_status(self) -> dict[str, Any]: ...

    def sync_repository(self, repository: GitHubRepositoryRef) -> dict[str, Any]: ...

    def sync_label(self, repository: GitHubRepositoryRef, label: GitHubLabelSpec) -> dict[str, Any]: ...

    def create_or_update_issue(
        self,
        repository: GitHubRepositoryRef,
        issue: GitHubIssueSpec,
        *,
        existing_issue_number: int | None = None,
    ) -> dict[str, Any]: ...

    def create_or_update_pull_request(
        self,
        repository: GitHubRepositoryRef,
        pull_request: GitHubPullRequestSpec,
        *,
        existing_pull_number: int | None = None,
    ) -> dict[str, Any]: ...

    def create_or_update_check_run(
        self,
        repository: GitHubRepositoryRef,
        pull_number: int,
        check_run: Any,
    ) -> dict[str, Any]: ...

    def create_pull_request_review(
        self,
        repository: GitHubRepositoryRef,
        pull_number: int,
        review: Any,
    ) -> dict[str, Any]: ...

    def merge_pull_request(
        self,
        repository: GitHubRepositoryRef,
        pull_number: int,
        merge: Any,
    ) -> dict[str, Any]: ...


class MockGitHubClient:
    """Deterministic in-memory GitHub client used for local tests."""

    def __init__(self, authenticator: GitHubAppAuthenticator | None = None) -> None:
        self.authenticator = authenticator or GitHubAppAuthenticator.from_env({"NEXUSCTL_GITHUB_MODE": "mock"})
        self.repositories: dict[str, dict[str, Any]] = {}
        self.labels: dict[tuple[str, str], dict[str, Any]] = {}
        self.issues: dict[tuple[str, int], dict[str, Any]] = {}
        self.pull_requests: dict[tuple[str, int], dict[str, Any]] = {}
        self.check_runs: dict[tuple[str, int, str], dict[str, Any]] = {}
        self.pull_request_reviews: dict[tuple[str, int, int], dict[str, Any]] = {}
        self.merges: dict[tuple[str, int], dict[str, Any]] = {}
        self._next_issue_number = 1
        self._next_pull_number = 1
        self._next_check_run_number = 1
        self._next_review_number = 1

    def app_status(self) -> dict[str, Any]:
        status = dict(self.authenticator.status())
        status.update(
            {
                "client": self.__class__.__name__,
                "network_enabled": False,
                "credentials_required_for_local_tests": False,
            }
        )
        return status

    def sync_repository(self, repository: GitHubRepositoryRef) -> dict[str, Any]:
        payload = {
            "id": repository.id,
            "full_name": repository.full_name,
            "owner": repository.owner,
            "name": repository.name,
            "default_branch": repository.default_branch,
            "visibility": repository.visibility,
            "status": "mock_synced",
        }
        self.repositories[repository.id] = payload
        return dict(payload)

    def sync_label(self, repository: GitHubRepositoryRef, label: GitHubLabelSpec) -> dict[str, Any]:
        payload = {
            "repository": repository.full_name,
            "name": label.name,
            "description": label.description,
            "color": label.color,
            "status": "mock_synced",
        }
        self.labels[(repository.id, label.name)] = payload
        return dict(payload)

    def create_or_update_issue(
        self,
        repository: GitHubRepositoryRef,
        issue: GitHubIssueSpec,
        *,
        existing_issue_number: int | None = None,
    ) -> dict[str, Any]:
        number = existing_issue_number or self._next_issue_number
        if existing_issue_number is None:
            self._next_issue_number += 1
        payload = {
            "repository": repository.full_name,
            "number": number,
            "url": f"mock://github/{repository.full_name}/issues/{number}",
            "title": issue.title,
            "body": issue.body,
            "labels": list(issue.labels),
            "status": "mock_updated" if existing_issue_number else "mock_created",
        }
        self.issues[(repository.id, number)] = payload
        return dict(payload)

    def create_or_update_pull_request(
        self,
        repository: GitHubRepositoryRef,
        pull_request: GitHubPullRequestSpec,
        *,
        existing_pull_number: int | None = None,
    ) -> dict[str, Any]:
        self.sync_repository(repository)
        number = existing_pull_number or self._next_pull_number
        if existing_pull_number is None:
            self._next_pull_number += 1
        payload = {
            "repository": repository.full_name,
            "number": number,
            "url": f"mock://github/{repository.full_name}/pull/{number}",
            "title": pull_request.title,
            "body": pull_request.body,
            "head": pull_request.head,
            "base": pull_request.base,
            "labels": list(pull_request.labels),
            "head_sha": _stable_sha({
                "repository": repository.full_name,
                "head": pull_request.head,
                "base": pull_request.base,
                "title": pull_request.title,
                "body": pull_request.body,
                "labels": list(pull_request.labels),
            }),
            "status": "mock_updated" if existing_pull_number else "mock_created",
        }
        self.pull_requests[(repository.id, number)] = payload
        return dict(payload)

    def create_or_update_check_run(
        self,
        repository: GitHubRepositoryRef,
        pull_number: int,
        check_run: Any,
    ) -> dict[str, Any]:
        self.sync_repository(repository)
        name = str(getattr(check_run, "name"))
        key = (repository.id, int(pull_number), name)
        existing = self.check_runs.get(key)
        number = int(existing["number"]) if existing else self._next_check_run_number
        if existing is None:
            self._next_check_run_number += 1
        payload = {
            "id": f"mock-check-{number}",
            "number": number,
            "repository": repository.full_name,
            "pull_number": int(pull_number),
            "url": f"mock://github/{repository.full_name}/pull/{pull_number}/checks/{number}",
            "name": name,
            "status": getattr(check_run, "status"),
            "conclusion": getattr(check_run, "conclusion"),
            "head_sha": getattr(check_run, "head_sha"),
            "summary": getattr(check_run, "summary"),
            "details": dict(getattr(check_run, "details", {}) or {}),
            "details_url": getattr(check_run, "details_url", None),
            "mock_status": "mock_updated" if existing else "mock_created",
        }
        self.check_runs[key] = payload
        return dict(payload)

    def create_pull_request_review(
        self,
        repository: GitHubRepositoryRef,
        pull_number: int,
        review: Any,
    ) -> dict[str, Any]:
        self.sync_repository(repository)
        number = self._next_review_number
        self._next_review_number += 1
        payload = {
            "id": f"mock-pr-review-{number}",
            "number": number,
            "repository": repository.full_name,
            "pull_number": int(pull_number),
            "url": f"mock://github/{repository.full_name}/pull/{pull_number}/reviews/{number}",
            "event": getattr(review, "event"),
            "body": getattr(review, "body"),
            "commit_sha": getattr(review, "commit_sha", None),
            "details": dict(getattr(review, "details", {}) or {}),
            "status": "mock_created",
        }
        self.pull_request_reviews[(repository.id, int(pull_number), number)] = payload
        return dict(payload)

    def merge_pull_request(
        self,
        repository: GitHubRepositoryRef,
        pull_number: int,
        merge: Any,
    ) -> dict[str, Any]:
        self.sync_repository(repository)
        key = (repository.id, int(pull_number))
        merge_sha = _stable_sha({
            "repository": repository.full_name,
            "pull_number": int(pull_number),
            "method": getattr(merge, "method"),
            "expected_head_sha": getattr(merge, "expected_head_sha", None),
            "commit_title": getattr(merge, "commit_title", ""),
            "commit_message": getattr(merge, "commit_message", ""),
        })
        payload = {
            "id": f"mock-merge-{merge_sha[:12]}",
            "repository": repository.full_name,
            "pull_number": int(pull_number),
            "url": f"mock://github/{repository.full_name}/pull/{pull_number}/merge",
            "merged": True,
            "merge_sha": merge_sha,
            "method": getattr(merge, "method"),
            "expected_head_sha": getattr(merge, "expected_head_sha", None),
            "commit_title": getattr(merge, "commit_title", ""),
            "commit_message": getattr(merge, "commit_message", ""),
            "details": dict(getattr(merge, "details", {}) or {}),
            "status": "mock_merged",
        }
        self.merges[key] = payload
        existing_pr = self.pull_requests.get(key)
        if existing_pr is not None:
            existing_pr["merged"] = True
            existing_pr["merge_sha"] = merge_sha
        return dict(payload)


def _stable_sha(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()
