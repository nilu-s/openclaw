"""Hardening helpers for the GitHub projection adapter.

These helpers normalize external GitHub facts before application services use
or record them.  They intentionally derive projection-only state; Nexusctl
state remains authoritative for lifecycle decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

from nexusctl.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class GitHubUrlRef:
    """Normalized reference parsed from a common GitHub URL form."""

    owner: str
    name: str
    kind: str = "repository"
    number: int | None = None
    branch: str | None = None
    path: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    def to_json(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "name": self.name,
            "full_name": self.full_name,
            "kind": self.kind,
            "number": self.number,
            "branch": self.branch,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class DerivedReviewState:
    """Projection-only state derived from one or more GitHub review payloads."""

    state: str
    authoritative: bool = False
    latest_external_id: str | None = None
    source: str = "github_projection"
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "authoritative": self.authoritative,
            "latest_external_id": self.latest_external_id,
            "source": self.source,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class DerivedChecksState:
    """Projection-only aggregate state derived from GitHub check payloads."""

    state: str
    authoritative: bool = False
    total: int = 0
    failed: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()
    passed: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "authoritative": self.authoritative,
            "total": self.total,
            "failed": list(self.failed),
            "pending": list(self.pending),
            "passed": list(self.passed),
        }


@dataclass(frozen=True, slots=True)
class ChangedFilesPolicyResult:
    """Normalized changed-files result used by projection safety checks."""

    ok: bool
    changed_paths: tuple[str, ...]
    blocked_paths: tuple[str, ...] = ()
    out_of_scope_paths: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "changed_paths": list(self.changed_paths),
            "blocked_paths": list(self.blocked_paths),
            "out_of_scope_paths": list(self.out_of_scope_paths),
        }


def parse_github_url(value: str) -> GitHubUrlRef:
    """Parse common GitHub repository, issue, PR, blob, tree, git, and SSH URLs."""

    raw = value.strip()
    if not raw:
        raise ValidationError("GitHub URL must be non-empty")
    if raw.startswith("git@"):
        return _parse_ssh_url(raw)
    if raw.startswith("ssh://git@"):
        parsed = urlparse(raw)
        path = parsed.path.lstrip("/")
        return _parse_repo_path(_strip_git_suffix(path))
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https", "git"} and parsed.netloc.lower() in {"github.com", "www.github.com"}:
        return _parse_repo_path(_strip_git_suffix(parsed.path.lstrip("/")))
    if "://" not in raw and raw.count("/") >= 1:
        return _parse_repo_path(_strip_git_suffix(raw))
    raise ValidationError(f"unsupported GitHub URL form: {value}")


def derive_review_state(reviews: Iterable[Mapping[str, Any]]) -> DerivedReviewState:
    """Derive an external review state without making it Nexus-authoritative."""

    latest_state = "pending"
    latest_id: str | None = None
    seen: list[str] = []
    for review in reviews:
        state = str(review.get("state") or review.get("event") or "").strip().upper()
        if not state:
            continue
        seen.append(state)
        latest_id = str(review.get("id") or review.get("node_id") or "") or latest_id
        if state in {"CHANGES_REQUESTED", "REQUEST_CHANGES"}:
            latest_state = "changes_requested"
        elif state in {"APPROVED", "APPROVE"} and latest_state != "changes_requested":
            latest_state = "approved"
        elif state in {"COMMENTED", "COMMENT"} and latest_state == "pending":
            latest_state = "commented"
        elif state in {"DISMISSED"}:
            latest_state = "dismissed"
    return DerivedReviewState(
        state=latest_state,
        latest_external_id=latest_id,
        details={"observed_states": seen},
    )


def derive_checks_state(checks: Iterable[Mapping[str, Any]]) -> DerivedChecksState:
    """Derive an aggregate external checks state without changing Nexus gates."""

    failed: list[str] = []
    pending: list[str] = []
    passed: list[str] = []
    total = 0
    for check in checks:
        total += 1
        name = str(check.get("name") or check.get("app", {}).get("name") or f"check-{total}")
        status = str(check.get("status") or "").lower()
        conclusion = str(check.get("conclusion") or "").lower()
        if status in {"queued", "requested", "waiting", "pending", "in_progress"} or not conclusion:
            pending.append(name)
        elif conclusion in {"success", "neutral", "skipped"}:
            passed.append(name)
        else:
            failed.append(name)
    if failed:
        state = "failed"
    elif pending:
        state = "pending"
    elif total:
        state = "passed"
    else:
        state = "missing"
    return DerivedChecksState(
        state=state,
        total=total,
        failed=tuple(failed),
        pending=tuple(pending),
        passed=tuple(passed),
    )


def evaluate_changed_files_policy(
    changed_paths: Iterable[str],
    *,
    allowed_patterns: Iterable[str] = (),
    blocked_patterns: Iterable[str] = (".git/**", ".github/workflows/**"),
) -> ChangedFilesPolicyResult:
    """Normalize changed files and detect blocked or out-of-scope paths."""

    normalized = tuple(_normalize_changed_path(path) for path in changed_paths)
    allowed = tuple(pattern.strip() for pattern in allowed_patterns if pattern and pattern.strip())
    blocked = tuple(pattern.strip() for pattern in blocked_patterns if pattern and pattern.strip())
    blocked_paths = tuple(path for path in normalized if _matches_any(path, blocked))
    out_of_scope: tuple[str, ...] = ()
    if allowed:
        out_of_scope = tuple(path for path in normalized if not _matches_any(path, allowed))
    return ChangedFilesPolicyResult(
        ok=not blocked_paths and not out_of_scope,
        changed_paths=tuple(sorted(set(normalized))),
        blocked_paths=tuple(sorted(set(blocked_paths))),
        out_of_scope_paths=tuple(sorted(set(out_of_scope))),
    )


def _parse_ssh_url(raw: str) -> GitHubUrlRef:
    # git@github.com:owner/repo.git
    try:
        host, path = raw.split(":", 1)
    except ValueError as exc:
        raise ValidationError(f"unsupported GitHub SSH URL form: {raw}") from exc
    if host.lower() != "git@github.com":
        raise ValidationError(f"unsupported GitHub SSH host: {host}")
    return _parse_repo_path(_strip_git_suffix(path))


def _parse_repo_path(path: str) -> GitHubUrlRef:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValidationError("GitHub URL must include owner and repository")
    owner, name = parts[0], parts[1]
    if not _safe_segment(owner) or not _safe_segment(name):
        raise ValidationError("GitHub owner and repository must be safe path segments")
    kind = "repository"
    number: int | None = None
    branch: str | None = None
    file_path: str | None = None
    if len(parts) >= 4 and parts[2] in {"issues", "pull"}:
        kind = "issue" if parts[2] == "issues" else "pull_request"
        number = _positive_int(parts[3], label=kind)
    elif len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        kind = parts[2]
        branch = parts[3]
        file_path = "/".join(parts[4:]) or None
    elif len(parts) > 2:
        raise ValidationError(f"unsupported GitHub URL path kind: {parts[2]}")
    return GitHubUrlRef(owner=owner, name=name, kind=kind, number=number, branch=branch, path=file_path)


def _strip_git_suffix(path: str) -> str:
    return path[:-4] if path.endswith(".git") else path


def _safe_segment(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value


def _positive_int(value: str, *, label: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ValidationError(f"GitHub {label} number must be an integer") from exc
    if number <= 0:
        raise ValidationError(f"GitHub {label} number must be positive")
    return number


def _normalize_changed_path(value: str) -> str:
    path = str(value).strip().replace("\\", "/")
    if not path or path.startswith("/") or path.startswith("~"):
        raise ValidationError(f"unsafe changed path: {value}")
    pure = PurePosixPath(path)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValidationError(f"unsafe changed path: {value}")
    return pure.as_posix()


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(path, pattern) or fnmatchcase(path, pattern.rstrip("/**")) for pattern in patterns)
