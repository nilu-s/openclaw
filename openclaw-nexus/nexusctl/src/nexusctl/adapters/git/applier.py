"""Branch projection adapter for patch proposal workflow.

OpenClaw Nexus does not mutate the canonical repository directly.  It only
records a Nexusctl-owned branch projection plan and leaves future apply/merge to
later gated workflows.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexusctl.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class BranchProjection:
    branch: str
    changed_paths: tuple[str, ...]
    pushed: bool
    mode: str = "mock"

    def to_json(self) -> dict[str, object]:
        return {
            "branch": self.branch,
            "changed_paths": list(self.changed_paths),
            "pushed": self.pushed,
            "mode": self.mode,
            "canonical_repo_mutated": False,
        }


class BranchProjector:
    """Mockable boundary for branch creation and push operations."""

    def project_patch_branch(self, *, branch: str, changed_paths: tuple[str, ...]) -> BranchProjection:
        if not branch.strip():
            raise ValidationError("branch name is required")
        if not changed_paths:
            raise ValidationError("cannot project an empty patch branch")
        return BranchProjection(branch=branch, changed_paths=tuple(changed_paths), pushed=True)
