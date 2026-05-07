"""Worktree adapter for patch proposal workflow.

Nexusctl starts work by declaring a deterministic branch name.  The actual
checkout can be managed by a human or local automation; this adapter provides a
small guardrail-friendly contract that is easy to mock in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from nexusctl.domain.errors import ValidationError


_SAFE_BRANCH_RE = re.compile(r"[^a-zA-Z0-9._/-]+")


@dataclass(frozen=True, slots=True)
class WorktreeStartPlan:
    work_item_id: str
    branch: str
    base_path: str
    instructions: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "work_item_id": self.work_item_id,
            "branch": self.branch,
            "base_path": self.base_path,
            "instructions": list(self.instructions),
        }


def branch_for_work(work_item_id: str, feature_request_id: str) -> str:
    if not work_item_id.strip() or not feature_request_id.strip():
        raise ValidationError("work and feature request ids are required for branch planning")
    raw = f"nexus/{feature_request_id}/{work_item_id}"
    branch = _SAFE_BRANCH_RE.sub("-", raw).strip("/.-")
    return branch[:180]


def plan_worktree_start(project_root: str | Path, work_item_id: str, feature_request_id: str) -> WorktreeStartPlan:
    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValidationError(f"project root does not exist: {root}")
    branch = branch_for_work(work_item_id, feature_request_id)
    return WorktreeStartPlan(
        work_item_id=work_item_id,
        branch=branch,
        base_path=str(root),
        instructions=(
            f"Create a local worktree from the canonical project root on branch {branch}.",
            "Modify only files covered by the active Nexusctl scope lease.",
            "Submit with: nexusctl patch submit <work_or_request_id> --from-worktree <path> --json.",
        ),
    )
