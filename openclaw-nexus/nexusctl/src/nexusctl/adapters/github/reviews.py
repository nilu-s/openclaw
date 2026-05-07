"""GitHub Pull Request review adapter for review/acceptance workflow.

Nexusctl remains the only writer.  Review services decide the Nexus lifecycle
state first, then project a small PR-review representation through this mockable
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexusctl.adapters.github.client import GitHubClient, GitHubRepositoryRef
from nexusctl.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class GitHubPullRequestReviewSpec:
    """Portable representation of a GitHub PR review projection."""

    event: str
    body: str
    commit_sha: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event not in {"APPROVE", "REQUEST_CHANGES", "COMMENT"}:
            raise ValidationError("GitHub PR review event must be APPROVE, REQUEST_CHANGES, or COMMENT")
        if not self.body.strip():
            raise ValidationError("GitHub PR review body must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "body": self.body,
            "commit_sha": self.commit_sha,
            "details": dict(self.details),
        }


class GitHubPullRequestReviewsAdapter:
    """Publish Nexus technical review verdicts as GitHub PR reviews."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def sync_review(
        self,
        repository: GitHubRepositoryRef,
        *,
        pull_number: int,
        spec: GitHubPullRequestReviewSpec,
    ) -> dict[str, Any]:
        create_review = getattr(self.client, "create_pull_request_review", None)
        if not callable(create_review):
            raise ValidationError("GitHub client does not implement PR-review projection")
        return create_review(repository, pull_number, spec)
