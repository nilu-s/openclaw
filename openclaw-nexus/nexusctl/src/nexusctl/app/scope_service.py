"""Scope lease service for work/scope workflow.

Scope leases are bounded, auditable authorizations that connect a routed
FeatureRequest to an assigned software builder, a narrow set of path globs, and
a short TTL.  Nexusctl remains the only authority that grants or revokes leases;
builders may use active leases but never grant them to themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
import json
import re
import sqlite3
from pathlib import PurePosixPath
from typing import Any, Iterable
from uuid import uuid4

from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.domain.states import ScopeLeaseStatus
from nexusctl.storage.event_store import EventStore


_DURATION_RE = re.compile(r"^\s*(?P<value>\d+)\s*(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)?\s*$", re.I)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat().replace("+00:00", "Z")


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored scope JSON is invalid: {exc}") from exc


def parse_duration(value: str) -> timedelta:
    """Parse compact TTL strings such as ``30m``, ``2h``, ``1d`` or ``900``.

    Bare integers are seconds.  Durations must be positive and are capped at
    seven days to keep work scopes leases short-lived.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValidationError("ttl must be a non-empty duration such as 30m, 2h, or 1d")
    match = _DURATION_RE.match(value)
    if not match:
        raise ValidationError(f"invalid ttl duration {value!r}; use seconds, m, h, d, or w")
    amount = int(match.group("value"))
    if amount <= 0:
        raise ValidationError("ttl must be positive")
    unit = (match.group("unit") or "s").lower()
    if unit.startswith("s"):
        delta = timedelta(seconds=amount)
    elif unit.startswith("m"):
        delta = timedelta(minutes=amount)
    elif unit.startswith("h"):
        delta = timedelta(hours=amount)
    elif unit.startswith("d"):
        delta = timedelta(days=amount)
    elif unit.startswith("w"):
        delta = timedelta(weeks=amount)
    else:  # pragma: no cover - guarded by regex
        raise ValidationError(f"unsupported ttl unit {unit!r}")
    if delta > timedelta(days=7):
        raise ValidationError("ttl must not exceed 7 days")
    return delta


@dataclass(frozen=True, slots=True)
class PathScope:
    """Relative repository path-scope represented as POSIX glob patterns."""

    patterns: tuple[str, ...]

    @classmethod
    def from_patterns(cls, values: Iterable[str]) -> "PathScope":
        patterns = tuple(_normalize_pattern(value) for value in values)
        if not patterns:
            raise ValidationError("at least one path scope glob is required")
        return cls(patterns=patterns)

    def allows(self, path: str) -> bool:
        normalized = _normalize_path(path)
        return any(fnmatchcase(normalized, pattern) for pattern in self.patterns)

    def to_json(self) -> list[str]:
        return list(self.patterns)


@dataclass(frozen=True, slots=True)
class ScopeLeaseRecord:
    id: str
    work_item_id: str
    feature_request_id: str
    agent_id: str
    domain: str
    capabilities: tuple[str, ...]
    paths: tuple[str, ...]
    granted_by: str
    status: ScopeLeaseStatus
    expires_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row, *, feature_request_id: str) -> "ScopeLeaseRecord":
        capabilities = _json_loads(row["capabilities_json"], [])
        paths = _json_loads(row["paths_json"], [])
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            raise ValidationError("stored lease capabilities must be a list of strings")
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ValidationError("stored lease paths must be a list of strings")
        return cls(
            id=row["id"],
            work_item_id=row["work_item_id"],
            feature_request_id=feature_request_id,
            agent_id=row["agent_id"],
            domain=row["domain_id"],
            capabilities=tuple(capabilities),
            paths=tuple(paths),
            granted_by=row["granted_by"],
            status=ScopeLeaseStatus(row["status"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "work_item_id": self.work_item_id,
            "feature_request_id": self.feature_request_id,
            "agent_id": self.agent_id,
            "domain": self.domain,
            "capabilities": list(self.capabilities),
            "paths": list(self.paths),
            "granted_by": self.granted_by,
            "status": self.status.value,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ScopeService:
    """Grant, revoke, and validate bounded path-scope leases."""

    def __init__(self, connection: sqlite3.Connection, policy: PolicyEngine) -> None:
        self.connection = connection
        self.policy = policy
        self.events = EventStore(connection)

    def lease(
        self,
        subject: Subject,
        *,
        agent_id: str,
        feature_request_id: str,
        paths: Iterable[str],
        ttl: str,
        capabilities: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        work = self._work_for_request(feature_request_id)
        self.policy.require(subject, "scope.lease.grant", target_domain=work["domain_id"], resource_domain=work["domain_id"])
        target_agent = self._agent(agent_id)
        self._require_agent_eligible_for_work(target_agent, work)
        path_scope = PathScope.from_patterns(paths)
        lease_capabilities = tuple(capabilities or self._default_capabilities_for_agent(agent_id))
        self._require_lease_capabilities_allowed(target_agent, lease_capabilities)

        lease_id = f"lease-{uuid4().hex}"
        now = _utcnow()
        created_at = _iso(now)
        expires_at = _iso(now + parse_duration(ttl))
        self.connection.execute(
            """
            INSERT INTO scope_leases(
              id, work_item_id, agent_id, domain_id, capabilities_json, paths_json,
              granted_by, status, expires_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease_id,
                work["id"],
                agent_id,
                work["domain_id"],
                _json_dumps(list(lease_capabilities)),
                _json_dumps(path_scope.to_json()),
                subject.agent_id,
                ScopeLeaseStatus.ACTIVE.value,
                expires_at,
                created_at,
                created_at,
            ),
        )
        self.connection.execute(
            "UPDATE work_items SET scope_lease_id = ?, updated_at = ? WHERE id = ?",
            (lease_id, created_at, work["id"]),
        )
        event = self.events.append(
            aggregate_type="scope_lease",
            aggregate_id=lease_id,
            event_type="scope_lease.granted",
            actor_id=subject.agent_id,
            payload={
                "id": lease_id,
                "work_item_id": work["id"],
                "feature_request_id": feature_request_id,
                "agent_id": agent_id,
                "domain": work["domain_id"],
                "capabilities": list(lease_capabilities),
                "paths": path_scope.to_json(),
                "expires_at": expires_at,
            },
            metadata={"milestone": 8, "service": self.__class__.__name__},
        )
        record = self._get_record(lease_id)
        body = record.to_json()
        body["event_id"] = event.event_id
        body["path_scope"] = {"type": "glob", "root": "repository", "patterns": list(record.paths)}
        return body

    def revoke(self, subject: Subject, lease_id: str) -> dict[str, Any]:
        record = self._get_record(lease_id)
        self.policy.require(subject, "scope.lease.revoke", target_domain=record.domain, resource_domain=record.domain)
        if record.status is ScopeLeaseStatus.REVOKED:
            body = record.to_json()
            body["already_revoked"] = True
            return body
        now = _utcnow_iso()
        self.connection.execute(
            "UPDATE scope_leases SET status = ?, updated_at = ? WHERE id = ?",
            (ScopeLeaseStatus.REVOKED.value, now, lease_id),
        )
        self.connection.execute(
            "UPDATE work_items SET scope_lease_id = NULL, updated_at = ? WHERE scope_lease_id = ?",
            (now, lease_id),
        )
        event = self.events.append(
            aggregate_type="scope_lease",
            aggregate_id=lease_id,
            event_type="scope_lease.revoked",
            actor_id=subject.agent_id,
            payload={"id": lease_id, "previous_status": record.status.value, "status": ScopeLeaseStatus.REVOKED.value},
            metadata={"milestone": 8, "service": self.__class__.__name__},
        )
        body = self._get_record(lease_id).to_json()
        body["event_id"] = event.event_id
        return body

    def show(self, subject: Subject, lease_id: str) -> dict[str, Any]:
        record = self._get_record(lease_id)
        self._require_visible(subject, record)
        body = record.to_json()
        body["usable"] = self._is_usable(record, subject=subject)
        return body

    def assert_usable(self, subject: Subject, *, lease_id: str, capability_id: str, path: str) -> dict[str, Any]:
        """Validate that ``subject`` may exercise ``capability_id`` for ``path`` via an active lease."""

        record = self._get_record(lease_id)
        if record.agent_id != subject.agent_id:
            raise PolicyDeniedError("scope lease belongs to a different agent", rule_id="scope_lease_agent_bound")
        if record.domain != subject.domain:
            raise PolicyDeniedError("scope lease domain must match authenticated agent domain", rule_id="scope_domain_bound")
        if record.status is not ScopeLeaseStatus.ACTIVE:
            raise PolicyDeniedError("scope lease is not active", rule_id="scope_lease_not_active")
        expires_at = _parse_iso(record.expires_at)
        if expires_at is not None and expires_at <= _utcnow():
            self._mark_expired(record)
            raise PolicyDeniedError("scope lease has expired", rule_id="scope_lease_expired")
        if capability_id not in record.capabilities:
            raise PolicyDeniedError("scope lease does not include requested capability", rule_id="scope_capability_bound")
        if not PathScope(record.paths).allows(path):
            raise PolicyDeniedError("path is outside the leased scope", rule_id="scope_path_bound")
        self.policy.require(subject, capability_id, resource_domain=record.domain)
        return {"ok": True, "lease": record.to_json(), "capability": capability_id, "path": _normalize_path(path)}

    def _get_record(self, lease_id: str) -> ScopeLeaseRecord:
        row = self.connection.execute(
            """
            SELECT l.*, w.feature_request_id
            FROM scope_leases l
            JOIN work_items w ON w.id = l.work_item_id
            WHERE l.id = ?
            """,
            (lease_id,),
        ).fetchone()
        if row is None:
            raise ValidationError(f"unknown scope lease {lease_id}")
        record = ScopeLeaseRecord.from_row(row, feature_request_id=row["feature_request_id"])
        if record.status is ScopeLeaseStatus.ACTIVE:
            expires_at = _parse_iso(record.expires_at)
            if expires_at is not None and expires_at <= _utcnow():
                self._mark_expired(record)
                return self._get_record(lease_id)
        return record

    def _mark_expired(self, record: ScopeLeaseRecord) -> None:
        now = _utcnow_iso()
        self.connection.execute(
            "UPDATE scope_leases SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (ScopeLeaseStatus.EXPIRED.value, now, record.id, ScopeLeaseStatus.ACTIVE.value),
        )
        self.connection.execute(
            "UPDATE work_items SET scope_lease_id = NULL, updated_at = ? WHERE scope_lease_id = ?",
            (now, record.id),
        )
        self.events.append(
            aggregate_type="scope_lease",
            aggregate_id=record.id,
            event_type="scope_lease.expired",
            actor_id="nexusctl",
            payload={"id": record.id, "expires_at": record.expires_at, "status": ScopeLeaseStatus.EXPIRED.value},
            metadata={"milestone": 8, "service": self.__class__.__name__},
        )

    def _work_for_request(self, feature_request_id: str) -> sqlite3.Row:
        row = self.connection.execute(
            """
            SELECT * FROM work_items
            WHERE feature_request_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (feature_request_id,),
        ).fetchone()
        if row is None:
            raise ValidationError(f"feature request {feature_request_id} has no planned work item")
        return row

    def _agent(self, agent_id: str) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise ValidationError(f"unknown agent {agent_id}")
        return row

    def _require_agent_eligible_for_work(self, agent: sqlite3.Row, work: sqlite3.Row) -> None:
        if agent["domain_id"] != work["domain_id"]:
            rule_id = (
                "trading_cannot_receive_software_lease"
                if work["domain_id"] == "software" and agent["domain_id"] == "trading"
                else "scope_lease_recipient_domain_bound"
            )
            raise PolicyDeniedError(
                "scope lease recipient must belong to the work item's target domain",
                rule_id=rule_id,
            )
        if work["domain_id"] == "software" and not self._agent_has_capability(agent["id"], "patch.submit"):
            raise PolicyDeniedError(
                "software scope leases may be granted only to software implementation agents",
                rule_id="trading_cannot_receive_software_lease",
            )

    def _require_lease_capabilities_allowed(self, agent: sqlite3.Row, capabilities: tuple[str, ...]) -> None:
        if not capabilities:
            raise ValidationError("scope lease must include at least one capability")
        for capability_id in capabilities:
            if not self._capability_exists(capability_id):
                raise ValidationError(f"unknown capability {capability_id}")
            if not self._agent_has_capability(agent["id"], capability_id):
                raise PolicyDeniedError(
                    f"{agent['id']} cannot receive lease capability {capability_id}",
                    rule_id="scope_lease_capability_must_match_agent",
                )

    def _default_capabilities_for_agent(self, agent_id: str) -> tuple[str, ...]:
        if self._agent_has_capability(agent_id, "patch.submit"):
            return ("patch.submit",)
        if self._agent_has_capability(agent_id, "work.read"):
            return ("work.read",)
        raise PolicyDeniedError(
            f"{agent_id} has no usable default capability for a scope lease",
            rule_id="scope_lease_recipient_not_eligible",
        )

    def _capability_exists(self, capability_id: str) -> bool:
        row = self.connection.execute("SELECT id FROM capabilities WHERE id = ?", (capability_id,)).fetchone()
        return row is not None

    def _agent_has_capability(self, agent_id: str, capability_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM agent_capabilities WHERE agent_id = ? AND capability_id = ?",
            (agent_id, capability_id),
        ).fetchone()
        return row is not None

    def _require_visible(self, subject: Subject, record: ScopeLeaseRecord) -> None:
        if subject.agent_id == record.agent_id:
            return
        self.policy.require(subject, "scope.lease.grant", target_domain=record.domain, resource_domain=record.domain)

    @staticmethod
    def _is_usable(record: ScopeLeaseRecord, *, subject: Subject) -> bool:
        if record.agent_id != subject.agent_id or record.domain != subject.domain:
            return False
        if record.status is not ScopeLeaseStatus.ACTIVE:
            return False
        expires_at = _parse_iso(record.expires_at)
        return expires_at is None or expires_at > _utcnow()


def _normalize_pattern(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("path scope globs must be non-empty strings")
    text = value.strip().replace("\\", "/")
    if text.startswith("/"):
        raise ValidationError("path scope globs must be repository-relative")
    if "\x00" in text:
        raise ValidationError("path scope globs cannot contain null bytes")
    parts = PurePosixPath(text).parts
    if any(part == ".." for part in parts):
        raise ValidationError("path scope globs cannot traverse outside the repository")
    normalized = PurePosixPath(text).as_posix()
    if normalized in {".", ""}:
        raise ValidationError("path scope globs must name at least one path")
    return normalized


def _normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("path must be a non-empty string")
    text = value.strip().replace("\\", "/")
    if text.startswith("/"):
        raise ValidationError("path must be repository-relative")
    if "\x00" in text:
        raise ValidationError("path cannot contain null bytes")
    parts = PurePosixPath(text).parts
    if any(part == ".." for part in parts):
        raise ValidationError("path cannot traverse outside the repository")
    normalized = PurePosixPath(text).as_posix()
    if normalized in {".", ""}:
        raise ValidationError("path must name at least one file or directory")
    return normalized
