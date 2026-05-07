"""Repository diff helpers for patch proposal workflow patch proposals.

The adapter is deliberately local and deterministic.  It compares a candidate
worktree against the canonical project root and emits repository-relative paths
plus compact unified diffs for textual files.  Nexusctl services validate those
paths against active scope leases before a patch can be recorded.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from pathlib import Path, PurePosixPath
from typing import Iterable

from nexusctl.domain.errors import ValidationError


_IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_IGNORED_FILES = {"nexus.db"}


@dataclass(frozen=True, slots=True)
class FileDiff:
    path: str
    status: str
    additions: int
    deletions: int
    patch: str

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions,
            "patch": self.patch,
        }


@dataclass(frozen=True, slots=True)
class WorktreeDiff:
    base: str
    worktree: str
    files: tuple[FileDiff, ...]

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(file.path for file in self.files)

    @property
    def additions(self) -> int:
        return sum(file.additions for file in self.files)

    @property
    def deletions(self) -> int:
        return sum(file.deletions for file in self.files)

    def summary(self) -> str:
        return f"{len(self.files)} file(s), +{self.additions}/-{self.deletions}"

    def to_json(self) -> dict[str, object]:
        return {
            "base": self.base,
            "worktree": self.worktree,
            "changed_paths": list(self.changed_paths),
            "additions": self.additions,
            "deletions": self.deletions,
            "files": [file.to_json() for file in self.files],
        }


def diff_worktree(base_path: str | Path, worktree_path: str | Path) -> WorktreeDiff:
    base = Path(base_path).resolve()
    worktree = Path(worktree_path).resolve()
    if not base.is_dir():
        raise ValidationError(f"base project root does not exist: {base}")
    if not worktree.is_dir():
        raise ValidationError(f"worktree path does not exist: {worktree}")
    base_files = _collect_files(base)
    worktree_files = _collect_files(worktree)
    full_worktree = (worktree / ".nexusctl_full_worktree").exists()
    comparison_files = (base_files | worktree_files) if full_worktree else worktree_files
    changed: list[FileDiff] = []
    for rel in sorted(comparison_files):
        old = base / rel
        new = worktree / rel
        if rel not in base_files:
            changed.append(_file_diff(rel, None, new, "added"))
        elif rel not in worktree_files:
            changed.append(_file_diff(rel, old, None, "deleted"))
        elif _read_bytes(old) != _read_bytes(new):
            changed.append(_file_diff(rel, old, new, "modified"))
    return WorktreeDiff(base=str(base), worktree=str(worktree), files=tuple(changed))


def normalize_repo_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("path must be a non-empty repository-relative string")
    text = value.strip().replace("\\", "/")
    if text.startswith("/") or "\x00" in text:
        raise ValidationError("path must be a safe repository-relative path")
    parts = PurePosixPath(text).parts
    if any(part == ".." for part in parts):
        raise ValidationError("path cannot traverse outside the repository")
    normalized = PurePosixPath(text).as_posix()
    if normalized in {".", ""}:
        raise ValidationError("path must name a file")
    return normalized


def _collect_files(root: Path) -> set[str]:
    files: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in _IGNORED_DIRS for part in rel_parts):
            continue
        if path.name in _IGNORED_FILES:
            continue
        files.add(PurePosixPath(*rel_parts).as_posix())
    return files


def _file_diff(rel: str, old: Path | None, new: Path | None, status: str) -> FileDiff:
    rel = normalize_repo_path(rel)
    old_lines = _read_text_lines(old) if old else []
    new_lines = _read_text_lines(new) if new else []
    patch_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            lineterm="",
        )
    )
    additions = sum(1 for line in patch_lines if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in patch_lines if line.startswith("-") and not line.startswith("---"))
    patch = "\n".join(patch_lines)
    if not patch and status in {"added", "deleted", "modified"}:
        patch = f"Binary or non-textual change: {status} {rel}"
        additions = 1 if status == "added" else 0
        deletions = 1 if status == "deleted" else 0
    return FileDiff(path=rel, status=status, additions=additions, deletions=deletions, patch=patch)


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _read_text_lines(path: Path | None) -> list[str]:
    if path is None:
        return []
    data = path.read_bytes()
    if b"\x00" in data:
        return []
    try:
        return data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return []
