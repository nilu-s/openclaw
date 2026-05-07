from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
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


def derive_review_state(reviews: list[dict[str, Any]], *, latest_commit_at: str | None = None, required_approvals: int = 1) -> str:
    """Derive a conservative PR review state from GitHub reviews.

    Latest review per reviewer wins. Dismissed reviews are ignored, and approvals
    older than the latest commit are treated as stale so a force-push or new
    commit cannot reuse an older approval as a green Nexus gate.
    """
    if not reviews:
        return "pending"
    latest_by_user: dict[str, dict[str, Any]] = {}
    for review in reviews:
        state = str(review.get("state") or "").upper()
        if state == "DISMISSED":
            continue
        user = review.get("user") or {}
        login = user.get("login") or review.get("user_login") or review.get("author") or "unknown"
        submitted = review.get("submitted_at") or review.get("updated_at") or review.get("created_at") or ""
        current = latest_by_user.get(login)
        current_submitted = current.get("submitted_at") or current.get("updated_at") or current.get("created_at") or "" if current else ""
        if current is None or submitted >= current_submitted:
            latest_by_user[login] = review
    states = {str(review.get("state") or "").upper() for review in latest_by_user.values()}
    if "CHANGES_REQUESTED" in states:
        return "changes_requested"
    approvals = [
        review for review in latest_by_user.values()
        if str(review.get("state") or "").upper() == "APPROVED"
        and (not latest_commit_at or (review.get("submitted_at") or review.get("updated_at") or review.get("created_at") or "") >= latest_commit_at)
    ]
    if len(approvals) >= required_approvals:
        return "approved"
    if approvals:
        return "pending"
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


def evaluate_changed_files_policy(changed_files: list[str | dict[str, Any]], do_not_touch: list[str]) -> dict[str, Any]:
    from fnmatch import fnmatch

    # Always block changes to environment, credential, SSH and key material files.
    sensitive_defaults = [
        ".env", ".env.*", "**/.env", "**/.env.*",
        "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_ed25519", "**/id_rsa", "**/id_ed25519",
        "secrets/*", "**/secrets/*", "**/*secret*", "**/*credential*",
    ]
    patterns = [pattern.strip() for pattern in do_not_touch if isinstance(pattern, str) and pattern.strip()] + sensitive_defaults

    violations: list[str] = []
    checked: set[str] = set()
    for item in changed_files:
        if isinstance(item, str):
            filename = item
            previous = None
            status = None
        elif isinstance(item, dict):
            filename = item.get("filename")
            previous = item.get("previous_filename")
            status = item.get("status")
        else:
            continue
        candidates = [value for value in (filename, previous) if isinstance(value, str) and value]
        if not candidates:
            continue
        display = candidates[0]
        if display in checked:
            continue
        if any(fnmatch(path, pattern) for path in candidates for pattern in patterns):
            violations.append(display)
            checked.add(display)
            continue
        # Treat renames out of protected paths as protected too, even if the new
        # path is benign-looking. This catches previous_filename based bypasses.
        if status == "renamed" and previous and any(fnmatch(previous, pattern) for pattern in patterns):
            violations.append(display)
            checked.add(display)
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
        data, _headers, _link = self._request_with_headers(method, path, owner=owner, repo=repo, payload=payload)
        return data

    def _request_with_headers(self, method: str, path: str, *, owner: str, repo: str, payload: dict[str, Any] | None = None) -> tuple[Any, dict[str, str], str | None]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = self._headers(owner, repo)
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = Request(f"{self._api_base}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=15) as response:
                raw = response.read()
                parsed = {} if not raw else json.loads(raw.decode("utf-8"))
                return parsed, dict(response.headers.items()), response.headers.get("Link")
        except HTTPError as exc:
            code = _map_github_error(exc.code)
            raise NexusError(code, "GitHub request failed")
        except (URLError, TimeoutError, OSError):
            raise NexusError("NX-GH-UPSTREAM", "GitHub upstream unavailable")

    @staticmethod
    def _next_path_from_link(link_header: str | None) -> str | None:
        if not link_header:
            return None
        for part in link_header.split(","):
            section = part.strip()
            if 'rel="next"' not in section:
                continue
            start = section.find("<")
            end = section.find(">", start + 1)
            if start == -1 or end == -1:
                continue
            parsed = urlparse(section[start + 1:end])
            return urlunparse(("", "", parsed.path, "", parsed.query, ""))
        return None

    def _paginated_request(self, path: str, *, owner: str, repo: str, max_pages: int = 20) -> list[Any]:
        separator = "&" if "?" in path else "?"
        next_path: str | None = f"{path}{separator}per_page=100"
        items: list[Any] = []
        pages = 0
        while next_path:
            pages += 1
            if pages > max_pages:
                raise NexusError("NX-GH-VALIDATION", "GitHub pagination exceeded safety limit")
            payload, _headers, link = self._request_with_headers("GET", next_path, owner=owner, repo=repo)
            if isinstance(payload, list):
                items.extend(payload)
            elif isinstance(payload, dict):
                # Some GitHub list endpoints, such as check-runs, wrap the list in
                # a named field. Preserve the object shape while aggregating the list.
                list_keys = [key for key, value in payload.items() if isinstance(value, list)]
                if len(list_keys) == 1:
                    key = list_keys[0]
                    if not items:
                        items.append({k: v for k, v in payload.items() if k != key})
                    items.extend(payload[key])
                else:
                    return [payload]
            next_path = self._next_path_from_link(link)
        return items

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}", owner=owner, repo=repo)

    def create_issue(self, owner: str, repo: str, title: str, body: str, labels: list[str], assignees: list[str]) -> dict[str, Any]:
        return self._request("POST", f"/repos/{owner}/{repo}/issues", owner=owner, repo=repo, payload={"title": title, "body": body, "labels": labels, "assignees": assignees})

    def get_branch_protection(self, owner: str, repo: str, branch: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/branches/{branch}/protection", owner=owner, repo=repo)

    def get_codeowners(self, owner: str, repo: str) -> str:
        for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            try:
                payload = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", owner=owner, repo=repo)
                if isinstance(payload, dict) and payload.get("type") == "file":
                    return path
            except NexusError as exc:
                if exc.code != "NX-GH-NOT-FOUND":
                    raise
        raise NexusError("NX-GH-NOT-FOUND", "CODEOWNERS not found")

    def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/issues/{number}", owner=owner, repo=repo)

    def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}", owner=owner, repo=repo)

    def list_pull_request_files(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return [item for item in self._paginated_request(f"/repos/{owner}/{repo}/pulls/{number}/files", owner=owner, repo=repo) if isinstance(item, dict)]

    def list_pull_request_reviews(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return [item for item in self._paginated_request(f"/repos/{owner}/{repo}/pulls/{number}/reviews", owner=owner, repo=repo) if isinstance(item, dict)]

    def list_pull_request_commits(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return [item for item in self._paginated_request(f"/repos/{owner}/{repo}/pulls/{number}/commits", owner=owner, repo=repo) if isinstance(item, dict)]

    def get_combined_status(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/commits/{ref}/status", owner=owner, repo=repo)

    def list_check_runs_for_ref(self, owner: str, repo: str, ref: str) -> dict[str, Any]:
        items = self._paginated_request(f"/repos/{owner}/{repo}/commits/{ref}/check-runs", owner=owner, repo=repo)
        metadata = items[0] if items and isinstance(items[0], dict) and "check_runs" not in items[0] else {}
        check_runs = [item for item in items if isinstance(item, dict) and "name" in item]
        total_count = metadata.get("total_count", len(check_runs)) if isinstance(metadata, dict) else len(check_runs)
        return {"total_count": total_count, "check_runs": check_runs}


class FakeGitHubClient:
    def __init__(self):
        self.issues: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.pull_requests: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.files: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self.reviews: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self.commits: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self.statuses: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.check_runs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.branch_protection: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.codeowners: set[tuple[str, str]] = set()
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


# Compatibility helpers for tests that use FakeGitHubClient policy state.
def _fake_get_branch_protection(self, owner: str, repo: str, branch: str) -> dict[str, Any]:
    key = (owner, repo, branch)
    if key not in self.branch_protection:
        raise NexusError("NX-GH-NOT-FOUND", "branch protection not found")
    return self.branch_protection[key]

def _fake_get_codeowners(self, owner: str, repo: str) -> str:
    if (owner, repo) not in self.codeowners:
        raise NexusError("NX-GH-NOT-FOUND", "CODEOWNERS not found")
    return ".github/CODEOWNERS"

FakeGitHubClient.get_branch_protection = _fake_get_branch_protection
FakeGitHubClient.get_codeowners = _fake_get_codeowners
