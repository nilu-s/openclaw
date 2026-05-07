from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from nexusctl.backend.integrations.github_auth import EnvGitHubAuthProvider, GitHubAuthProvider
from nexusctl.backend.integrations.github_models import GitHubIssueRef, GitHubPullRequestRef, GitHubRepository
from nexusctl.errors import NexusError


_ALLOWED_HOSTS = {"github.com"}
_GITHUB_API_VERSION = "2022-11-28"
_USER_AGENT = "nexusctl"


def _map_github_error(status: int) -> str:
    if status in {401, 403}:
        return "NX-GH-AUTH"
    if status == 404:
        return "NX-GH-NOT-FOUND"
    if status == 410:
        return "NX-GH-DISABLED"
    if status == 422:
        return "NX-GH-VALIDATION"
    if status == 429:
        return "NX-GH-RATE-LIMIT"
    if status >= 500:
        return "NX-GH-UPSTREAM"
    return "NX-GH-UPSTREAM"


def parse_github_issue_url(url: str) -> GitHubIssueRef:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in _ALLOWED_HOSTS:
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub issue URL host")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] != "issues":
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub issue URL path")
    try:
        number = int(parts[3])
    except ValueError:
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub issue number")
    if number <= 0:
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub issue number")
    return GitHubIssueRef(owner=parts[0], repo=parts[1], number=number)


def parse_github_pr_url(url: str) -> GitHubPullRequestRef:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in _ALLOWED_HOSTS:
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub PR URL host")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4 or parts[2] != "pull":
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub PR URL path")
    try:
        number = int(parts[3])
    except ValueError:
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub PR number")
    if number <= 0:
        raise NexusError("NX-GH-VALIDATION", "invalid GitHub PR number")
    return GitHubPullRequestRef(owner=parts[0], repo=parts[1], number=number)


def assert_repo_matches(ref: GitHubIssueRef | GitHubPullRequestRef, repo: GitHubRepository) -> None:
    if ref.owner != repo.owner or ref.repo != repo.repo:
        raise NexusError("NX-GH-VALIDATION", "GitHub URL does not match target repository")


def derive_review_state(reviews: list[dict[str, Any]]) -> str:
    if not reviews:
        return "pending"
    latest_by_user: dict[str, dict[str, Any]] = {}
    for review in reviews:
        user = review.get("user") or {}
        login = user.get("login") or review.get("user_login") or review.get("author") or "unknown"
        submitted = review.get("submitted_at") or review.get("updated_at") or review.get("created_at") or ""
        current = latest_by_user.get(login)
        if current is None or submitted >= (current.get("submitted_at") or current.get("updated_at") or current.get("created_at") or ""):
            latest_by_user[login] = review
    states = {str(review.get("state") or "").upper() for review in latest_by_user.values()}
    if "CHANGES_REQUESTED" in states:
        return "changes_requested"
    if "APPROVED" in states:
        return "approved"
    return "commented"


def derive_checks_state(check_runs: dict[str, Any] | None, combined_status: dict[str, Any] | None) -> str:
    seen = False
    failing = {"failure", "error", "cancelled", "timed_out", "action_required"}
    pending = {"pending", "queued", "in_progress", "requested", "waiting"}
    passing = {"success", "completed success"}

    def consume(status: str | None, conclusion: str | None = None) -> str | None:
        nonlocal seen
        raw_status = (status or "").lower()
        raw_conclusion = (conclusion or "").lower()
        if raw_conclusion or raw_status:
            seen = True
        if raw_conclusion in failing or raw_status in failing:
            return "failing"
        if raw_status in pending or raw_conclusion in pending:
            return "pending"
        if raw_status == "completed" and raw_conclusion == "success":
            return "passing"
        if raw_status in passing or raw_conclusion in passing:
            return "passing"
        return None

    worst = None
    if check_runs:
        for run in check_runs.get("check_runs", []) or []:
            state = consume(run.get("status"), run.get("conclusion"))
            if state == "failing":
                return "failing"
            if state == "pending":
                worst = "pending"
            elif state == "passing" and worst is None:
                worst = "passing"
    if combined_status:
        state = consume(combined_status.get("state"))
        if state == "failing":
            return "failing"
        if state == "pending":
            worst = "pending"
        elif state == "passing" and worst is None:
            worst = "passing"
        for status_item in combined_status.get("statuses", []) or []:
            state = consume(status_item.get("state"))
            if state == "failing":
                return "failing"
            if state == "pending":
                worst = "pending"
            elif state == "passing" and worst is None:
                worst = "passing"
    if worst:
        return worst
    return "unknown" if not seen else "unknown"


def evaluate_changed_files_policy(changed_files: list[str], do_not_touch: list[str]) -> dict[str, Any]:
    from fnmatch import fnmatch

    violations: list[str] = []
    patterns = [pattern.strip() for pattern in do_not_touch if isinstance(pattern, str) and pattern.strip()]
    for filename in changed_files:
        if any(fnmatch(filename, pattern) for pattern in patterns):
            violations.append(filename)
    return {"policy_state": "violated" if violations else "ok", "violations": violations}


class GitHubClient:
    def __init__(self, auth_provider: GitHubAuthProvider | None = None, *, api_base: str | None = None, env: Mapping[str, str] | None = None):
        self._auth_provider = auth_provider or EnvGitHubAuthProvider(env=env)
        source = env if env is not None else os.environ
        self._api_base = (api_base or source.get("NEXUS_GITHUB_API_BASE") or "https://api.github.com").rstrip("/")

    def _headers(self, owner: str, repo: str) -> dict[str, str]:
        token = self._auth_provider.get_token(GitHubRepository(repo_id=f"{owner}/{repo}", owner=owner, repo=repo))
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            "User-Agent": _USER_AGENT,
        }

    def _request(self, method: str, path: str, *, owner: str, repo: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = self._headers(owner, repo)
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = Request(f"{self._api_base}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=15) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            code = _map_github_error(exc.code)
            raise NexusError(code, "GitHub request failed")
        except (URLError, TimeoutError, OSError):
            raise NexusError("NX-GH-UPSTREAM", "GitHub upstream unavailable")

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}", owner=owner, repo=repo)

    def create_issue(self, owner: str, repo: str, title: str, body: str, labels: list[str], assignees: list[str]) -> dict[str, Any]:
        return self._request("POST", f"/repos/{owner}/{repo}/issues", owner=owner, repo=repo, payload={"title": title, "body": body, "labels": labels, "assignees": assignees})

    def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/issues/{number}", owner=owner, repo=repo)

    def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}", owner=owner, repo=repo)

    def list_pull_request_files(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}/files", owner=owner, repo=repo)

    def list_pull_request_reviews(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}/reviews", owner=owner, repo=repo)

    def list_pull_request_commits(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}/commits", owner=owner, repo=repo)

    def get_combined_status(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/commits/{ref}/status", owner=owner, repo=repo)

    def list_check_runs_for_ref(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/commits/{ref}/check-runs", owner=owner, repo=repo)


class FakeGitHubClient:
    def __init__(self):
        self.issues: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.pull_requests: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.files: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self.reviews: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self.commits: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self.statuses: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.check_runs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.created_issues: list[dict[str, Any]] = []

    def create_issue(self, owner: str, repo: str, title: str, body: str, labels: list[str], assignees: list[str]) -> dict[str, Any]:
        number = len([key for key in self.issues if key[0] == owner and key[1] == repo]) + 1
        issue = {
            "number": number,
            "node_id": f"I_{number}",
            "title": title,
            "state": "open",
            "html_url": f"https://github.com/{owner}/{repo}/issues/{number}",
            "url": f"https://api.github.com/repos/{owner}/{repo}/issues/{number}",
            "labels": [{"name": label} for label in labels],
            "assignees": [{"login": user} for user in assignees],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "closed_at": None,
        }
        self.issues[(owner, repo, number)] = issue
        self.created_issues.append({"owner": owner, "repo": repo, "title": title, "body": body, "labels": labels, "assignees": assignees})
        return issue

    def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self.issues[(owner, repo, number)]

    def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self.pull_requests[(owner, repo, number)]

    def list_pull_request_files(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return self.files.get((owner, repo, number), [])

    def list_pull_request_reviews(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return self.reviews.get((owner, repo, number), [])

    def list_pull_request_commits(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return self.commits.get((owner, repo, number), [])

    def get_combined_status(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        return self.statuses.get((owner, repo, ref), {})

    def list_check_runs_for_ref(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        return self.check_runs.get((owner, repo, ref), {})
