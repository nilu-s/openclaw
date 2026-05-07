"""Lifecycle state enums for the OpenClaw Nexus domain model."""

from __future__ import annotations

from enum import StrEnum


class DomainStatus(StrEnum):
    """Operational availability of a Nexus domain."""

    MVP = "mvp"
    PREPARED_OPTIONAL = "prepared_optional"
    DISABLED = "disabled"


class GoalStatus(StrEnum):
    """Lifecycle states for measurable Nexus goals."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class FeatureRequestStatus(StrEnum):
    """Cross-domain feature request lifecycle."""

    PROPOSED = "proposed"
    ROUTED = "routed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CLOSED = "closed"


class WorkItemStatus(StrEnum):
    """Software/platform work item lifecycle."""

    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    PATCH_SUBMITTED = "patch_submitted"
    REVIEWING = "reviewing"
    ACCEPTANCE_REQUIRED = "acceptance_required"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ScopeLeaseStatus(StrEnum):
    """Bounded authorization lease lifecycle."""

    REQUESTED = "requested"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ReviewStatus(StrEnum):
    """Technical review lifecycle."""

    PENDING = "pending"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class GitHubLinkKind(StrEnum):
    """GitHub projection target type."""

    ISSUE = "issue"
    BRANCH = "branch"
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    CHECK_RUN = "check_run"
