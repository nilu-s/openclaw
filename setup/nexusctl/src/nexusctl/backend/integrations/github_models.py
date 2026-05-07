from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubRepository:
    repo_id: str
    owner: str
    repo: str
    default_branch: str | None = None
    installation_id: str | None = None
    node_id: str | None = None
    html_url: str | None = None


@dataclass(frozen=True)
class GitHubIssueRef:
    owner: str
    repo: str
    number: int


@dataclass(frozen=True)
class GitHubPullRequestRef:
    owner: str
    repo: str
    number: int
