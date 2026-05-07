"""Normalization helpers for GitHub reconciliation payloads.

These helpers keep raw GitHub webhook shape handling out of the reconciliation
service. They do not mutate Nexus state and deliberately return small,
plain values that the service can compare against Nexusctl authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RepositoryRef:
    full_name: str | None
    owner: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class IssueRef:
    repository_id: str | None
    issue_number: int | None


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    repository_id: str | None
    pull_number: int | None


class GitHubWebhookPayloadNormalizer:
    """Extract stable reconciliation inputs from loose GitHub payloads."""

    @staticmethod
    def repository_ref(payload: Mapping[str, Any]) -> RepositoryRef:
        repository = payload.get("repository") if isinstance(payload.get("repository"), Mapping) else {}
        owner = repository.get("owner") if isinstance(repository, Mapping) else {}
        return RepositoryRef(
            full_name=str(repository["full_name"]) if repository.get("full_name") is not None else None,
            owner=str(owner["login"]) if isinstance(owner, Mapping) and owner.get("login") is not None else None,
            name=str(repository["name"]) if repository.get("name") is not None else None,
        )

    @staticmethod
    def issue_ref(payload: Mapping[str, Any], repository_id: str | None) -> IssueRef:
        issue = payload.get("issue") if isinstance(payload.get("issue"), Mapping) else {}
        return IssueRef(repository_id=repository_id, issue_number=int_or_none(issue.get("number")))

    @staticmethod
    def pull_request_ref(payload: Mapping[str, Any], repository_id: str | None) -> PullRequestRef:
        pull = payload.get("pull_request") if isinstance(payload.get("pull_request"), Mapping) else {}
        return PullRequestRef(repository_id=repository_id, pull_number=int_or_none(pull.get("number") or payload.get("number")))

    @staticmethod
    def first_pull_request_number(items: Any) -> int | None:
        if not isinstance(items, list) or not items:
            return None
        first = items[0]
        if isinstance(first, Mapping):
            return int_or_none(first.get("number"))
        return None

    @staticmethod
    def label_names(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        labels: list[str] = []
        for item in raw:
            if isinstance(item, str):
                labels.append(item)
            elif isinstance(item, Mapping) and item.get("name") is not None:
                labels.append(str(item["name"]))
        return sorted(set(labels))


def int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
