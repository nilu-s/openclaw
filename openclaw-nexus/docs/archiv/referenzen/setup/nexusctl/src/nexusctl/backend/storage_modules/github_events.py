from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GitHubEventTarget:
    request_id: str | None
    repo_id: str | None
    owner: str | None
    repo: str | None
    action: str | None


def event_target_from_payload(conn: sqlite3.Connection, payload: dict[str, Any]) -> GitHubEventTarget:
    """Resolve a GitHub webhook payload to the local Nexus work item, if any.

    This keeps webhook payload mapping out of Storage.record_github_event so the
    Storage facade can remain focused on transactions and lifecycle decisions.
    """
    action = payload.get("action") if isinstance(payload.get("action"), str) else None
    repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    owner = ((repository.get("owner") or {}) if isinstance(repository.get("owner"), dict) else {}).get("login")
    repo = repository.get("name")
    request_id = None
    repo_id = None
    if owner and repo:
        repo_row = conn.execute("SELECT repo_id FROM repositories WHERE github_owner = ? AND github_repo = ?", (owner, repo)).fetchone()
        repo_id = repo_row["repo_id"] if repo_row else None
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else None
        pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else None
        number = (pr or issue or {}).get("number") if (pr or issue) else None
        if isinstance(number, int):
            table = "github_pull_requests" if pr else "github_issues"
            column = "pr_number" if pr else "issue_number"
            linked = conn.execute(
                f"SELECT request_id FROM {table} WHERE github_owner = ? AND github_repo = ? AND {column} = ?",
                (owner, repo, number),
            ).fetchone()
            request_id = linked["request_id"] if linked else None
    return GitHubEventTarget(request_id=request_id, repo_id=repo_id, owner=owner, repo=repo, action=action)


def encode_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
