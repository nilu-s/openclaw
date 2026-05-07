"""OpenClaw Nexus domain models.

The models in this module are intentionally small dataclasses.  They define the
shape of the domain kernel before SQLite storage workflow introduces persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from .errors import ValidationError
from .states import (
    DomainStatus,
    FeatureRequestStatus,
    GitHubLinkKind,
    GoalStatus,
    ReviewStatus,
    ScopeLeaseStatus,
    WorkItemStatus,
)


def _require_id(value: str, field_name: str = "id") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple, set)):
        raise ValidationError("expected a sequence of strings")
    out: list[str] = []
    for value in values:
        out.append(_require_id(value, "sequence item"))
    return tuple(out)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Domain:
    id: str
    name: str
    status: DomainStatus = DomainStatus.MVP
    description: str = ""
    source_of_truth: str = "nexusctl"
    default_visibility: str = "own_domain"

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.name, "name")
        if self.source_of_truth != "nexusctl":
            raise ValidationError("domains must use nexusctl as source_of_truth")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Domain":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            status=DomainStatus(data.get("status", DomainStatus.MVP)),
            description=data.get("description", ""),
            source_of_truth=data.get("source_of_truth", "nexusctl"),
            default_visibility=data.get("default_visibility", "own_domain"),
        )


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    category: str
    mutating: bool
    cross_domain_mutating: bool
    side_effect: str
    target_domain_allowed: bool = False
    reserved_for: str | None = None

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.category, "category")
        _require_id(self.side_effect, "side_effect")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Capability":
        return cls(
            id=data["id"],
            category=data.get("category", "unknown"),
            mutating=bool(data.get("mutating", False)),
            cross_domain_mutating=bool(data.get("cross_domain_mutating", False)),
            side_effect=data.get("side_effect", "read_only"),
            target_domain_allowed=bool(data.get("target_domain_allowed", False)),
            reserved_for=data.get("reserved_for"),
        )


@dataclass(frozen=True, slots=True)
class Agent:
    id: str
    display_name: str
    domain: str
    role: str
    normal_agent: bool
    capabilities: tuple[str, ...]
    skills: tuple[str, ...] = ()
    description: str = ""
    github_direct_write: bool = False
    repo_direct_apply: bool = False

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.domain, "domain")
        _require_id(self.role, "role")
        if self.github_direct_write:
            raise ValidationError("agents may not have direct GitHub write")
        if self.repo_direct_apply:
            raise ValidationError("agents may not apply directly to the canonical repo")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Agent":
        return cls(
            id=data["id"],
            display_name=data.get("display_name", data["id"]),
            domain=data["domain"],
            role=data.get("role", data["id"]),
            normal_agent=bool(data.get("normal_agent", True)),
            capabilities=_tuple(data.get("capabilities", ())),
            skills=_tuple(data.get("skills", ())),
            description=data.get("description", ""),
            github_direct_write=bool((data.get("github") or {}).get("direct_write", False)),
            repo_direct_apply=bool((data.get("repo") or {}).get("direct_apply", False)),
        )


@dataclass(frozen=True, slots=True)
class Metric:
    id: str
    type: str
    operator: str
    target: Any
    unit: str | None = None

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.type, "metric type")
        _require_id(self.operator, "operator")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Metric":
        return cls(
            id=data["id"],
            type=data.get("type", "unknown"),
            operator=data.get("operator", "=="),
            target=data.get("target"),
            unit=data.get("unit"),
        )


@dataclass(frozen=True, slots=True)
class Goal:
    id: str
    domain: str
    owner_agent: str
    description: str
    metrics: tuple[Metric, ...]
    status: GoalStatus = GoalStatus.ACTIVE
    window: str | None = None
    evaluation: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.domain, "domain")
        _require_id(self.owner_agent, "owner_agent")
        if not self.metrics:
            raise ValidationError("goals must define at least one metric")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Goal":
        return cls(
            id=data["id"],
            domain=data["domain"],
            owner_agent=data["owner_agent"],
            description=data.get("description", ""),
            metrics=tuple(Metric.from_mapping(m) for m in data.get("metrics", ())),
            status=GoalStatus(data.get("status", GoalStatus.ACTIVE)),
            window=data.get("window"),
            evaluation=data.get("evaluation", {}),
        )


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    domain: str
    uri: str
    goal_id: str | None = None
    kind: str = "file"
    summary: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    added_by: str | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.domain, "domain")
        _require_id(self.uri, "uri")
        _require_id(self.kind, "kind")
        if self.goal_id is not None:
            _require_id(self.goal_id, "goal_id")
        if self.added_by is not None:
            _require_id(self.added_by, "added_by")


@dataclass(frozen=True, slots=True)
class GoalMeasurement:
    id: str
    goal_id: str
    metric_id: str
    value: Any
    evidence_id: str | None = None
    recorded_by: str | None = None
    measured_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.goal_id, "goal_id")
        _require_id(self.metric_id, "metric_id")
        if self.evidence_id is not None:
            _require_id(self.evidence_id, "evidence_id")
        if self.recorded_by is not None:
            _require_id(self.recorded_by, "recorded_by")


@dataclass(frozen=True, slots=True)
class GoalEvaluation:
    id: str
    goal_id: str
    status: str
    summary: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)
    evaluated_by: str | None = None
    evaluated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.goal_id, "goal_id")
        if self.status not in {"passing", "warning", "failing", "unknown"}:
            raise ValidationError("goal evaluation status must be passing, warning, failing, or unknown")
        if self.evaluated_by is not None:
            _require_id(self.evaluated_by, "evaluated_by")


@dataclass(frozen=True, slots=True)
class FeatureRequest:
    id: str
    source_domain: str
    target_domain: str
    created_by: str
    summary: str
    status: FeatureRequestStatus = FeatureRequestStatus.PROPOSED
    goal_id: str | None = None
    acceptance_contract: str | None = None
    safety_contract: str | None = None
    dedupe_key: str | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.source_domain, "source_domain")
        _require_id(self.target_domain, "target_domain")
        _require_id(self.created_by, "created_by")
        _require_id(self.summary, "summary")
        if self.dedupe_key is not None:
            _require_id(self.dedupe_key, "dedupe_key")


@dataclass(frozen=True, slots=True)
class WorkItem:
    id: str
    domain: str
    feature_request_id: str
    assigned_agent: str | None = None
    reviewer_agent: str | None = None
    status: WorkItemStatus = WorkItemStatus.PLANNED
    scope_lease_id: str | None = None
    summary: str = ""

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.domain, "domain")
        _require_id(self.feature_request_id, "feature_request_id")
        if self.assigned_agent is not None:
            _require_id(self.assigned_agent, "assigned_agent")
        if self.reviewer_agent is not None:
            _require_id(self.reviewer_agent, "reviewer_agent")


@dataclass(frozen=True, slots=True)
class ScopeLease:
    id: str
    work_item_id: str
    agent_id: str
    domain: str
    capabilities: tuple[str, ...]
    granted_by: str
    paths: tuple[str, ...] = ()
    status: ScopeLeaseStatus = ScopeLeaseStatus.ACTIVE
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.work_item_id, "work_item_id")
        _require_id(self.agent_id, "agent_id")
        _require_id(self.domain, "domain")
        _require_id(self.granted_by, "granted_by")
        if not self.capabilities:
            raise ValidationError("scope leases must include at least one capability")
        for capability in self.capabilities:
            _require_id(capability, "scope capability")
        for path in self.paths:
            _require_id(path, "scope path")


@dataclass(frozen=True, slots=True)
class Review:
    id: str
    work_item_id: str
    patch_id: str
    reviewer_agent: str
    status: ReviewStatus = ReviewStatus.PENDING
    verdict: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.work_item_id, "work_item_id")
        _require_id(self.patch_id, "patch_id")
        _require_id(self.reviewer_agent, "reviewer_agent")


@dataclass(frozen=True, slots=True)
class GitHubLink:
    id: str
    nexus_entity_id: str
    kind: GitHubLinkKind
    repository_id: str
    external_id: str
    url: str | None = None

    def __post_init__(self) -> None:
        _require_id(self.id)
        _require_id(self.nexus_entity_id, "nexus_entity_id")
        _require_id(self.repository_id, "repository_id")
        _require_id(self.external_id, "external_id")
