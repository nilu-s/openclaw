"""Software work planning service for work/scope workflow.

Work items are Nexusctl-owned planning records for routed FeatureRequests.  They
keep the FeatureRequest/GitHub-Issue link visible while builders and reviewers
receive explicit assignments and later path-scoped leases.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.domain.states import FeatureRequestStatus, WorkItemStatus
from nexusctl.storage.sqlite.repositories import RepositoryContext


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class WorkItemRecord:
    id: str
    domain: str
    feature_request_id: str
    assigned_agent: str | None
    reviewer_agent: str | None
    status: WorkItemStatus
    scope_lease_id: str | None
    summary: str
    created_at: str
    updated_at: str
    feature_request: dict[str, Any]
    github_issue: dict[str, Any] | None

    @classmethod
    def from_row(cls, row: sqlite3.Row, *, feature_request: dict[str, Any], github_issue: dict[str, Any] | None) -> "WorkItemRecord":
        return cls(
            id=row["id"],
            domain=row["domain_id"],
            feature_request_id=row["feature_request_id"],
            assigned_agent=row["assigned_agent_id"],
            reviewer_agent=row["reviewer_agent_id"],
            status=WorkItemStatus(row["status"]),
            scope_lease_id=row["scope_lease_id"],
            summary=row["summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            feature_request=feature_request,
            github_issue=github_issue,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "feature_request_id": self.feature_request_id,
            "assigned_agent": self.assigned_agent,
            "builder": self.assigned_agent,
            "reviewer_agent": self.reviewer_agent,
            "reviewer": self.reviewer_agent,
            "status": self.status.value,
            "scope_lease_id": self.scope_lease_id,
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "feature_request": self.feature_request,
            "github_issue": self.github_issue,
        }


class WorkService:
    """Plan, assign, and read software work for routed FeatureRequests."""

    def __init__(self, connection: sqlite3.Connection, policy: PolicyEngine) -> None:
        self.connection = connection
        self.policy = policy
        self.repositories = RepositoryContext(connection)
        self.events = self.repositories.events

    def plan(self, subject: Subject, feature_request_id: str) -> dict[str, Any]:
        request = self._feature_request(feature_request_id)
        self._require_plannable(request)
        self.policy.require(subject, "work.plan", resource_domain=request["target_domain"])
        existing = self._get_by_feature_request(feature_request_id)
        if existing is not None:
            body = existing.to_json()
            body["already_planned"] = True
            return body
        return self._create_planned_work(subject, request)

    def assign(self, subject: Subject, feature_request_id: str, *, builder: str, reviewer: str) -> dict[str, Any]:
        request = self._feature_request(feature_request_id)
        self._require_plannable(request, allow_in_progress=True)
        self._require_work_assign(subject, request["target_domain"])
        self._require_agent_in_domain(builder, request["target_domain"], required_capability="patch.submit", role_label="builder")
        self._require_agent_in_domain(reviewer, request["target_domain"], required_capability="review.submit", role_label="reviewer")
        if builder == reviewer:
            raise ValidationError("builder and reviewer must be different agents")
        work = self._get_by_feature_request(feature_request_id)
        if work is None:
            # Assignment is allowed to materialize a planned work item when the request was already routed.
            planned = self._create_planned_work(subject, request)
            work_id = planned["id"]
        else:
            work_id = work.id
        now = _utcnow_iso()
        self.repositories.work_items.assign(
            work_id=work_id, builder=builder, reviewer=reviewer, status=WorkItemStatus.READY.value, updated_at=now
        )
        self.repositories.feature_requests.transition(
            request_id=feature_request_id, status=FeatureRequestStatus.IN_PROGRESS, updated_at=now
        )
        event = self.events.append(
            aggregate_type="work_item",
            aggregate_id=work_id,
            event_type="work_item.assigned",
            actor_id=subject.agent_id,
            payload={
                "id": work_id,
                "feature_request_id": feature_request_id,
                "builder": builder,
                "reviewer": reviewer,
                "status": WorkItemStatus.READY.value,
            },
            metadata={"milestone": 8, "service": self.__class__.__name__},
        )
        body = self._get(work_id).to_json()
        body["event_id"] = event.event_id
        return body

    def show(self, subject: Subject, work_id: str) -> dict[str, Any]:
        record = self._get(work_id)
        self.policy.require(subject, "work.read", resource_domain=record.domain)
        body = record.to_json()
        body["events"] = [asdict(event) for event in self.events.list_for_aggregate("work_item", work_id)]
        return body


    def _create_planned_work(self, subject: Subject, request: dict[str, Any]) -> dict[str, Any]:
        work_id = f"work-{uuid4().hex}"
        now = _utcnow_iso()
        summary = f"Plan: {request['title']}"
        self.repositories.work_items.create_planned(
            work_id=work_id,
            domain_id=request["target_domain"],
            feature_request_id=request["id"],
            summary=summary,
            created_at=now,
            updated_at=now,
            status=WorkItemStatus.PLANNED.value,
        )
        if request["status"] == FeatureRequestStatus.ROUTED.value:
            self.repositories.feature_requests.transition(
                request_id=request["id"], status=FeatureRequestStatus.IN_PROGRESS, updated_at=now
            )
        event = self.events.append(
            aggregate_type="work_item",
            aggregate_id=work_id,
            event_type="work_item.planned",
            actor_id=subject.agent_id,
            payload={
                "id": work_id,
                "feature_request_id": request["id"],
                "domain": request["target_domain"],
                "github_issue": self._github_issue_for_request(request["id"]),
                "status": WorkItemStatus.PLANNED.value,
            },
            metadata={"milestone": 8, "service": self.__class__.__name__},
        )
        body = self._get(work_id).to_json()
        body["event_id"] = event.event_id
        return body

    def _require_work_assign(self, subject: Subject, target_domain: str) -> None:
        if subject.domain == target_domain:
            self.policy.require(subject, "work.assign", resource_domain=target_domain)
            return
        if not subject.normal_agent and subject.domain == "control":
            self.policy.require(subject, "work.assign", resource_domain=subject.domain)
            return
        self.policy.require(subject, "work.assign", resource_domain=target_domain)

    def _get(self, work_id: str) -> WorkItemRecord:
        row = self.repositories.work_items.get(work_id)
        if row is None:
            raise ValidationError(f"unknown work item {work_id}")
        request = self._feature_request(row["feature_request_id"])
        return WorkItemRecord.from_row(row, feature_request=request, github_issue=self._github_issue_for_request(row["feature_request_id"]))

    def _get_by_feature_request(self, feature_request_id: str) -> WorkItemRecord | None:
        row = self.repositories.work_items.get_by_feature_request(feature_request_id)
        if row is None:
            return None
        request = self._feature_request(feature_request_id)
        return WorkItemRecord.from_row(row, feature_request=request, github_issue=self._github_issue_for_request(feature_request_id))

    def _feature_request(self, feature_request_id: str) -> dict[str, Any]:
        row = self.repositories.feature_requests.get(feature_request_id)
        if row is None:
            raise ValidationError(f"unknown feature request {feature_request_id}")
        return {
            "id": row["id"],
            "source_domain": row["source_domain_id"],
            "target_domain": row["target_domain_id"],
            "created_by": row["created_by"],
            "goal_id": row["goal_id"],
            "title": row["summary"],
            "summary": row["summary"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _require_plannable(self, request: dict[str, Any], *, allow_in_progress: bool = False) -> None:
        if request["target_domain"] != "software":
            raise PolicyDeniedError(
                "work/scope workflow work planning is limited to software-domain requests",
                rule_id="software_work_only",
            )
        allowed = {FeatureRequestStatus.ROUTED.value}
        if allow_in_progress:
            allowed.add(FeatureRequestStatus.IN_PROGRESS.value)
        if request["status"] not in allowed:
            raise ValidationError(
                f"feature request {request['id']} must be routed before software work planning; current status is {request['status']}"
            )

    def _require_agent_in_domain(self, agent_id: str, domain: str, *, required_capability: str, role_label: str) -> None:
        row = self.connection.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise ValidationError(f"unknown {role_label} agent {agent_id}")
        if row["domain_id"] != domain:
            raise PolicyDeniedError(
                f"{role_label} agent must belong to the {domain} domain",
                rule_id="work_assignment_domain_bound",
            )
        capability = self.connection.execute(
            "SELECT 1 FROM agent_capabilities WHERE agent_id = ? AND capability_id = ?",
            (agent_id, required_capability),
        ).fetchone()
        if capability is None:
            raise PolicyDeniedError(
                f"{role_label} agent {agent_id} lacks {required_capability}",
                rule_id="work_assignment_capability_bound",
            )

    def _github_issue_for_request(self, feature_request_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT l.*, r.owner, r.name
            FROM github_issue_links l
            JOIN github_repositories r ON r.id = l.repository_id
            WHERE l.feature_request_id = ?
            ORDER BY l.synced_at DESC, l.id DESC
            LIMIT 1
            """,
            (feature_request_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "repository_id": row["repository_id"],
            "repository": f"{row['owner']}/{row['name']}",
            "issue_number": row["issue_number"],
            "url": row["url"],
            "synced_at": row["synced_at"],
        }
