"""GitHub Checks adapter for Nexusctl policy-gate projection.

The adapter intentionally stays tiny and mockable.  Application services pass
already-evaluated Nexus policy gates to this boundary; the boundary translates
those gate results into GitHub Check Run payloads without deciding lifecycle
state itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from nexusctl.adapters.github.client import GitHubClient, GitHubRepositoryRef
from nexusctl.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class GitHubCheckRunSpec:
    """Portable representation of one GitHub Check Run update."""

    name: str
    status: str
    conclusion: str | None
    head_sha: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    details_url: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValidationError("GitHub check run name must be non-empty")
        if self.status not in {"queued", "in_progress", "completed"}:
            raise ValidationError("GitHub check status must be queued, in_progress, or completed")
        if self.conclusion not in {None, "success", "failure", "neutral", "cancelled", "skipped", "timed_out", "action_required"}:
            raise ValidationError("GitHub check conclusion is invalid")
        if not self.head_sha.strip():
            raise ValidationError("GitHub check head_sha must be non-empty")

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "conclusion": self.conclusion,
            "head_sha": self.head_sha,
            "summary": self.summary,
            "details": dict(self.details),
            "details_url": self.details_url,
        }


class GitHubChecksAdapter:
    """Publish Nexus policy gates as GitHub Check Runs through a client."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def sync_check_run(
        self,
        repository: GitHubRepositoryRef,
        *,
        pull_number: int,
        spec: GitHubCheckRunSpec,
    ) -> dict[str, Any]:
        create_or_update = getattr(self.client, "create_or_update_check_run", None)
        if not callable(create_or_update):
            raise ValidationError("GitHub client does not implement check-run projection")
        return create_or_update(repository, pull_number, spec)

    def sync_check_runs(
        self,
        repository: GitHubRepositoryRef,
        *,
        pull_number: int,
        specs: Iterable[GitHubCheckRunSpec],
    ) -> list[dict[str, Any]]:
        return [self.sync_check_run(repository, pull_number=pull_number, spec=spec) for spec in specs]
