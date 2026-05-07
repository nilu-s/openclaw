"""GitHub Pull Request adapter for merge gate merge projection.

Nexusctl owns the merge decision.  This adapter is a small, mockable boundary
that translates a Nexus-approved merge into a GitHub PR merge call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexusctl.adapters.github.client import GitHubClient, GitHubRepositoryRef
from nexusctl.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class GitHubPullMergeSpec:
    """Portable representation of an approved pull-request merge."""

    method: str = "squash"
    commit_title: str = ""
    commit_message: str = ""
    expected_head_sha: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.method not in {"merge", "squash", "rebase"}:
            raise ValidationError("GitHub merge method must be merge, squash, or rebase")
        if self.expected_head_sha is not None and not self.expected_head_sha.strip():
            raise ValidationError("expected_head_sha must be non-empty when provided")

    def to_json(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "commit_title": self.commit_title,
            "commit_message": self.commit_message,
            "expected_head_sha": self.expected_head_sha,
            "details": dict(self.details),
        }


class GitHubPullRequestsAdapter:
    """Publish Nexus-approved PR merges through a GitHub client."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def merge_pull_request(
        self,
        repository: GitHubRepositoryRef,
        *,
        pull_number: int,
        spec: GitHubPullMergeSpec,
    ) -> dict[str, Any]:
        merge = getattr(self.client, "merge_pull_request", None)
        if not callable(merge):
            raise ValidationError("GitHub client does not implement pull-request merge projection")
        return merge(repository, pull_number, spec)
