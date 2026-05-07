"""Cross-domain Feature Request service for feature request workflow.

Feature Requests are the explicit handoff channel between domains.  The source
side is always derived from the authenticated ``Subject``; callers may only name
the target domain and source-domain goal they need help with.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
from typing import Any, Mapping
from uuid import uuid4

from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, UnknownDomainError, ValidationError
from nexusctl.domain.models import FeatureRequest
from nexusctl.domain.states import FeatureRequestStatus
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.repositories import FeatureRequestRepository, GoalRepository


_ALLOWED_TRANSITIONS: dict[FeatureRequestStatus, set[FeatureRequestStatus]] = {
    FeatureRequestStatus.PROPOSED: {
        FeatureRequestStatus.ROUTED,
        FeatureRequestStatus.BLOCKED,
        FeatureRequestStatus.REJECTED,
        FeatureRequestStatus.CLOSED,
    },
    FeatureRequestStatus.ROUTED: {
        FeatureRequestStatus.IN_PROGRESS,
        FeatureRequestStatus.BLOCKED,
        FeatureRequestStatus.ACCEPTED,
        FeatureRequestStatus.REJECTED,
        FeatureRequestStatus.CLOSED,
    },
    FeatureRequestStatus.IN_PROGRESS: {
        FeatureRequestStatus.BLOCKED,
        FeatureRequestStatus.ACCEPTED,
        FeatureRequestStatus.REJECTED,
        FeatureRequestStatus.CLOSED,
    },
    FeatureRequestStatus.BLOCKED: {
        FeatureRequestStatus.ROUTED,
        FeatureRequestStatus.IN_PROGRESS,
        FeatureRequestStatus.REJECTED,
        FeatureRequestStatus.CLOSED,
    },
    FeatureRequestStatus.ACCEPTED: {FeatureRequestStatus.CLOSED},
    FeatureRequestStatus.REJECTED: {FeatureRequestStatus.CLOSED},
    FeatureRequestStatus.CLOSED: set(),
}


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored feature request contract JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("stored feature request contract must be a JSON object")
    return data


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


@dataclass(frozen=True, slots=True)
class AcceptanceContract:
    """Business-domain conditions required before a request can be accepted."""

    source_domain: str
    target_domain: str
    goal_id: str
    title: str
    required_acceptance_domain: str
    criteria: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def default(cls, *, source_domain: str, target_domain: str, goal_id: str, title: str) -> "AcceptanceContract":
        return cls(
            source_domain=source_domain,
            target_domain=target_domain,
            goal_id=goal_id,
            title=title,
            required_acceptance_domain=source_domain,
            criteria=(
                "target domain provides implementation or plan evidence",
                "source domain confirms the requested goal is addressed",
                "Nexus records acceptance as auditable state before closure",
            ),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "acceptance_contract",
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "goal_id": self.goal_id,
            "title": self.title,
            "required_acceptance_domain": self.required_acceptance_domain,
            "criteria": list(self.criteria),
        }


@dataclass(frozen=True, slots=True)
class SafetyContract:
    """Safety boundaries for a cross-domain request."""

    source_domain: str
    target_domain: str
    forbidden_source_capabilities: tuple[str, ...] = ("patch.submit", "github.pr.create", "repo.apply")
    guardrails: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def default(cls, *, source_domain: str, target_domain: str) -> "SafetyContract":
        return cls(
            source_domain=source_domain,
            target_domain=target_domain,
            guardrails=(
                "source domain cannot receive target-domain scope leases implicitly",
                "target domain owns implementation planning and scoped work",
                "all routing and lifecycle changes must append audit events",
                "GitHub remains projection; Nexusctl remains lifecycle source-of-truth",
            ),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "safety_contract",
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "forbidden_source_capabilities": list(self.forbidden_source_capabilities),
            "guardrails": list(self.guardrails),
        }


@dataclass(frozen=True, slots=True)
class FeatureRequestRecord:
    id: str
    source_domain: str
    target_domain: str
    created_by: str
    goal_id: str | None
    title: str
    status: FeatureRequestStatus
    acceptance_contract: dict[str, Any]
    safety_contract: dict[str, Any]
    dedupe_key: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FeatureRequestRecord":
        return cls(
            id=row["id"],
            source_domain=row["source_domain_id"],
            target_domain=row["target_domain_id"],
            created_by=row["created_by"],
            goal_id=row["goal_id"],
            title=row["summary"],
            status=FeatureRequestStatus(row["status"]),
            acceptance_contract=_json_loads(row["acceptance_contract"]),
            safety_contract=_json_loads(row["safety_contract"]),
            dedupe_key=row["dedupe_key"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "created_by": self.created_by,
            "goal_id": self.goal_id,
            "title": self.title,
            "summary": self.title,
            "status": self.status.value,
            "acceptance_contract": self.acceptance_contract,
            "safety_contract": self.safety_contract,
            "dedupe_key": self.dedupe_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class FeatureRequestService:
    """Authenticated cross-domain request lifecycle API."""

    def __init__(self, connection: sqlite3.Connection, policy: PolicyEngine) -> None:
        self.connection = connection
        self.policy = policy
        self.events = EventStore(connection)
        self.feature_requests = FeatureRequestRepository(connection, self.events)
        self.goals = GoalRepository(connection, self.events)

    def create(self, subject: Subject, *, target_domain: str, goal_id: str, title: str) -> dict[str, Any]:
        self._assert_domain(target_domain)
        clean_title = _require_text(title, "title")
        source_domain = subject.domain
        self.policy.require(subject, "feature_request.create", target_domain=target_domain, resource_domain=source_domain)
        self._require_goal_in_source_domain(goal_id, source_domain)

        dedupe_key = self.dedupe_key(
            source_domain=source_domain,
            target_domain=target_domain,
            goal_id=goal_id,
            title=clean_title,
        )
        existing = self._get_by_dedupe_key(dedupe_key)
        if existing is not None:
            event = self.events.append(
                aggregate_type="feature_request",
                aggregate_id=existing.id,
                event_type="feature_request.deduplicated",
                actor_id=subject.agent_id,
                payload={
                    "id": existing.id,
                    "dedupe_key": dedupe_key,
                    "source_domain": source_domain,
                    "target_domain": target_domain,
                    "goal_id": goal_id,
                    "title": clean_title,
                },
                metadata={"milestone": 6, "service": self.__class__.__name__},
            )
            body = existing.to_json()
            body["deduplicated"] = True
            body["event_id"] = event.event_id
            return body

        acceptance_contract = AcceptanceContract.default(
            source_domain=source_domain,
            target_domain=target_domain,
            goal_id=goal_id,
            title=clean_title,
        ).to_json()
        safety_contract = SafetyContract.default(source_domain=source_domain, target_domain=target_domain).to_json()
        request_id = f"fr-{uuid4().hex}"
        created_at = _utcnow_iso()
        event = self.feature_requests.create(
            FeatureRequest(
                id=request_id,
                source_domain=source_domain,
                target_domain=target_domain,
                created_by=subject.agent_id,
                goal_id=goal_id,
                summary=clean_title,
                status=FeatureRequestStatus.PROPOSED,
                acceptance_contract=_json_dumps(acceptance_contract),
                safety_contract=_json_dumps(safety_contract),
                dedupe_key=dedupe_key,
                created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")),
            ),
            actor_id=subject.agent_id,
            created_event_payload={
                "id": request_id,
                "source_domain": source_domain,
                "target_domain": target_domain,
                "goal_id": goal_id,
                "title": clean_title,
                "status": FeatureRequestStatus.PROPOSED.value,
                "dedupe_key": dedupe_key,
                "acceptance_contract": acceptance_contract,
                "safety_contract": safety_contract,
                "source_domain_from": "auth_subject",
            },
            created_event_metadata={"milestone": 6, "service": self.__class__.__name__},
        )
        record = self._get(request_id)
        body = record.to_json()
        body["deduplicated"] = False
        body["event_id"] = event.event_id
        return body

    def list(self, subject: Subject) -> list[dict[str, Any]]:
        self.policy.require(subject, "feature_request.read", resource_domain=subject.domain)
        if subject.normal_agent:
            rows = self.feature_requests.list_visible_to_domain(subject.domain)
        else:
            rows = self.feature_requests.list_all()
        return [FeatureRequestRecord.from_row(row).to_json() for row in rows]

    def show(self, subject: Subject, request_id: str) -> dict[str, Any]:
        record = self._get(request_id)
        self._require_visible(subject, record)
        body = record.to_json()
        body["events"] = [asdict(event) for event in self.events.list_for_aggregate("feature_request", request_id)]
        return body

    def route(self, subject: Subject, request_id: str, *, target_domain: str) -> dict[str, Any]:
        self._assert_domain(target_domain)
        record = self._get(request_id)
        self.policy.require(
            subject,
            "feature_request.route",
            target_domain=target_domain,
            resource_domain=record.target_domain,
        )
        if record.status is FeatureRequestStatus.CLOSED:
            raise ValidationError("closed feature requests cannot be routed")
        dedupe_key = self.dedupe_key(
            source_domain=record.source_domain,
            target_domain=target_domain,
            goal_id=record.goal_id or "",
            title=record.title,
        )
        collision = self._get_by_dedupe_key(dedupe_key)
        if collision is not None and collision.id != record.id:
            raise ValidationError(f"routing would duplicate existing feature request {collision.id}")
        updated_at = _utcnow_iso()
        self.feature_requests.route(
            request_id=request_id,
            target_domain=target_domain,
            status=FeatureRequestStatus.ROUTED,
            dedupe_key=dedupe_key,
            updated_at=updated_at,
        )
        event = self.events.append(
            aggregate_type="feature_request",
            aggregate_id=request_id,
            event_type="feature_request.routed",
            actor_id=subject.agent_id,
            payload={
                "id": request_id,
                "source_domain": record.source_domain,
                "previous_target_domain": record.target_domain,
                "target_domain": target_domain,
                "status": FeatureRequestStatus.ROUTED.value,
                "dedupe_key": dedupe_key,
            },
            metadata={"milestone": 6, "service": self.__class__.__name__},
        )
        body = self._get(request_id).to_json()
        body["event_id"] = event.event_id
        return body

    def transition(self, subject: Subject, request_id: str, status: str) -> dict[str, Any]:
        record = self._get(request_id)
        new_status = self._parse_status(status)
        self.policy.require(
            subject,
            "feature_request.transition",
            target_domain=record.target_domain,
            resource_domain=record.target_domain,
        )
        allowed_next = _ALLOWED_TRANSITIONS[record.status]
        if new_status != record.status and new_status not in allowed_next:
            raise ValidationError(f"invalid feature request transition {record.status.value} -> {new_status.value}")
        updated_at = _utcnow_iso()
        self.feature_requests.transition(request_id=request_id, status=new_status, updated_at=updated_at)
        event = self.events.append(
            aggregate_type="feature_request",
            aggregate_id=request_id,
            event_type="feature_request.transitioned",
            actor_id=subject.agent_id,
            payload={
                "id": request_id,
                "source_domain": record.source_domain,
                "target_domain": record.target_domain,
                "previous_status": record.status.value,
                "status": new_status.value,
            },
            metadata={"milestone": 6, "service": self.__class__.__name__},
        )
        body = self._get(request_id).to_json()
        body["event_id"] = event.event_id
        return body

    @staticmethod
    def dedupe_key(*, source_domain: str, target_domain: str, goal_id: str, title: str) -> str:
        raw = "|".join((_normalize(source_domain), _normalize(target_domain), _normalize(goal_id), _normalize(title)))
        return "frd-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _get(self, request_id: str) -> FeatureRequestRecord:
        row = self.feature_requests.get(request_id)
        if row is None:
            raise ValidationError(f"unknown feature request {request_id}")
        return FeatureRequestRecord.from_row(row)

    def _get_by_dedupe_key(self, dedupe_key: str) -> FeatureRequestRecord | None:
        row = self.feature_requests.get_by_dedupe_key(dedupe_key)
        return FeatureRequestRecord.from_row(row) if row is not None else None

    def _assert_domain(self, domain_id: str) -> None:
        if not self.feature_requests.domain_exists(domain_id):
            raise UnknownDomainError(f"unknown domain {domain_id}")

    def _require_goal_in_source_domain(self, goal_id: str, source_domain: str) -> None:
        goal = _require_text(goal_id, "goal")
        goal_domain = self.goals.goal_domain(goal)
        if goal_domain is None:
            raise ValidationError(f"unknown goal {goal}")
        if goal_domain != source_domain:
            raise PolicyDeniedError(
                "feature request goal must belong to the authenticated source domain",
                rule_id="feature_request_source_domain_from_subject",
            )

    def _require_visible(self, subject: Subject, record: FeatureRequestRecord) -> None:
        self.policy.require(subject, "feature_request.read", resource_domain=subject.domain)
        if not subject.normal_agent:
            return
        if subject.domain in {record.source_domain, record.target_domain}:
            return
        raise PolicyDeniedError(
            "feature requests are visible only to source domain, target domain, and Nexus",
            rule_id="feature_request_visibility_domain_scoped",
        )

    @staticmethod
    def _parse_status(status: str) -> FeatureRequestStatus:
        try:
            return FeatureRequestStatus(status)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in FeatureRequestStatus)
            raise ValidationError(f"invalid feature request status {status!r}; allowed: {allowed}") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value.strip()
