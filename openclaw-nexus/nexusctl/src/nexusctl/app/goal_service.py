"""Goal, metric, evidence, measurement, and evaluation service for goal/evidence workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any, Mapping, Sequence
from uuid import uuid4

from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import UnknownDomainError, ValidationError
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.repositories import GoalRepository


EVALUATION_STATUSES = {"passing", "warning", "failing", "unknown"}


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"stored JSON payload is invalid: {exc}") from exc


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class GoalRecord:
    id: str
    domain: str
    owner_agent: str
    status: str
    window: str | None
    description: str
    metrics: tuple[dict[str, Any], ...]
    latest_evaluation: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        body = {
            "id": self.id,
            "domain": self.domain,
            "owner_agent": self.owner_agent,
            "status": self.status,
            "window": self.window,
            "description": self.description,
            "metrics": list(self.metrics),
        }
        body["latest_evaluation"] = self.latest_evaluation or {"status": "unknown", "summary": "not evaluated"}
        return body


class GoalService:
    """Authenticated goal management API backed by SQLite and append-only events."""

    def __init__(self, connection: sqlite3.Connection, policy: PolicyEngine) -> None:
        self.connection = connection
        self.policy = policy
        self.events = EventStore(connection)
        self.goals = GoalRepository(connection, self.events)

    def list_goals(self, subject: Subject, *, domain: str | None = None) -> list[dict[str, Any]]:
        visible_domain = domain or subject.domain
        self.policy.require(
            subject,
            "goal.read",
            resource_domain=visible_domain,
            requested_domain=domain,
        )
        return [goal.to_json() for goal in self._goal_records_for_domain(visible_domain)]

    def status(self, subject: Subject, *, domain: str | None = None) -> list[dict[str, Any]]:
        goals = self.list_goals(subject, domain=domain)
        return [
            {
                "id": goal["id"],
                "domain": goal["domain"],
                "owner_agent": goal["owner_agent"],
                "goal_status": goal["status"],
                "evaluation_status": (goal.get("latest_evaluation") or {}).get("status", "unknown"),
                "window": goal["window"],
                "description": goal["description"],
            }
            for goal in goals
        ]

    def show(self, subject: Subject, goal_id: str) -> dict[str, Any]:
        goal = self._goal_record(goal_id)
        self.policy.require(subject, "goal.read", resource_domain=goal.domain)
        body = goal.to_json()
        body["evidence"] = self._evidence_for_goal(goal_id)
        return body

    def add_evidence(self, subject: Subject, *, goal_id: str, file_path: str | Path, summary: str = "") -> dict[str, Any]:
        goal = self._goal_record(goal_id)
        self.policy.require(subject, "evidence.add", resource_domain=goal.domain)
        path = Path(file_path)
        if not path.is_file():
            raise ValidationError(f"evidence file does not exist: {path}")
        payload = self._read_evidence_payload(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        evidence_id = f"evi-{uuid4().hex}"
        created_at = _utcnow_iso()
        stored_payload = {
            "file": {
                "path": str(path),
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            },
            "content": payload,
        }
        measurements = _extract_measurement_values(payload)
        if measurements:
            stored_payload["measurements"] = measurements
        self.goals.add_file_evidence(
            evidence_id=evidence_id,
            domain_id=goal.domain,
            goal_id=goal_id,
            uri=str(path),
            summary=summary or f"evidence file {path.name}",
            payload_json=_json_dumps(stored_payload),
            added_by=subject.agent_id,
            created_at=created_at,
        )
        event = self.events.append(
            aggregate_type="evidence",
            aggregate_id=evidence_id,
            event_type="evidence.added",
            actor_id=subject.agent_id,
            payload={
                "id": evidence_id,
                "goal_id": goal_id,
                "domain": goal.domain,
                "uri": str(path),
                "sha256": digest,
                "measurement_keys": sorted(measurements),
            },
            metadata={"milestone": 5, "service": self.__class__.__name__},
        )
        self.events.append(
            aggregate_type="goal",
            aggregate_id=goal_id,
            event_type="goal.evidence_referenced",
            actor_id=subject.agent_id,
            payload={"goal_id": goal_id, "evidence_id": evidence_id},
            metadata={"milestone": 5, "service": self.__class__.__name__},
        )
        return {
            "id": evidence_id,
            "goal_id": goal_id,
            "domain": goal.domain,
            "uri": str(path),
            "kind": "file",
            "summary": summary or f"evidence file {path.name}",
            "sha256": digest,
            "created_at": created_at,
            "event_id": event.event_id,
            "measurement_keys": sorted(measurements),
        }

    def measure(
        self,
        subject: Subject,
        goal_id: str,
        *,
        values: Mapping[str, Any] | None = None,
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        goal = self._goal_record(goal_id)
        self.policy.require(subject, "goal.measure", resource_domain=goal.domain)
        metrics = {metric["id"]: metric for metric in goal.metrics}
        merged_values: dict[str, Any] = {}
        evidence = self._resolve_evidence(goal_id, evidence_id=evidence_id)
        if evidence is not None:
            payload = _json_loads(evidence["payload_json"], {})
            evidence_values = _extract_measurement_values(payload)
            merged_values.update({key: value for key, value in evidence_values.items() if key in metrics})
            evidence_id = evidence["id"]
        explicit_values = dict(values or {})
        unknown_values = sorted(set(explicit_values) - set(metrics))
        if unknown_values:
            raise ValidationError(f"unknown metric values for {goal_id}: {', '.join(unknown_values)}")
        merged_values.update(explicit_values)

        measured_at = _utcnow_iso()
        measurements: list[dict[str, Any]] = []
        for metric_id, metric in metrics.items():
            raw_value = merged_values.get(metric_id)
            value = _normalize_value(raw_value, metric.get("type")) if metric_id in merged_values else None
            measurement_id = f"msr-{uuid4().hex}"
            self.goals.add_measurement(
                measurement_id=measurement_id,
                goal_id=goal_id,
                metric_id=metric_id,
                measured_at=measured_at,
                value_json=_json_dumps(value),
                evidence_id=evidence_id,
                recorded_by=subject.agent_id,
            )
            measurements.append(
                {
                    "id": measurement_id,
                    "metric_id": metric_id,
                    "value": value,
                    "known": metric_id in merged_values,
                    "evidence_id": evidence_id,
                    "measured_at": measured_at,
                }
            )
        event = self.events.append(
            aggregate_type="goal",
            aggregate_id=goal_id,
            event_type="goal.measured",
            actor_id=subject.agent_id,
            payload={
                "goal_id": goal_id,
                "domain": goal.domain,
                "evidence_id": evidence_id,
                "measurements": [{"metric_id": item["metric_id"], "value": item["value"]} for item in measurements],
            },
            metadata={"milestone": 5, "service": self.__class__.__name__},
        )
        return {
            "goal_id": goal_id,
            "domain": goal.domain,
            "measured_at": measured_at,
            "evidence_id": evidence_id,
            "measurements": measurements,
            "event_id": event.event_id,
        }

    def evaluate(self, subject: Subject, goal_id: str) -> dict[str, Any]:
        goal = self._goal_record(goal_id)
        self.policy.require(subject, "goal.evaluate", resource_domain=goal.domain)
        latest = self._latest_measurements(goal_id)
        metric_results: list[dict[str, Any]] = []
        missing = []
        failures = []
        near_failures = []
        for metric in goal.metrics:
            metric_id = metric["id"]
            measurement = latest.get(metric_id)
            if measurement is None or measurement.get("value") is None:
                missing.append(metric_id)
                metric_results.append({"metric_id": metric_id, "status": "unknown", "reason": "missing measurement"})
                continue
            result = _compare_metric(metric, measurement["value"])
            result.update(
                {
                    "metric_id": metric_id,
                    "value": measurement["value"],
                    "target": metric["target"],
                    "operator": metric["operator"],
                    "evidence_id": measurement.get("evidence_id"),
                    "measured_at": measurement.get("measured_at"),
                }
            )
            metric_results.append(result)
            if result["status"] == "failing":
                failures.append(metric_id)
                if result.get("near_threshold"):
                    near_failures.append(metric_id)

        if missing:
            status = "unknown"
            summary = f"missing measurements for {', '.join(missing)}"
        elif failures:
            status = "warning" if set(failures) == set(near_failures) else "failing"
            summary = f"{status}: metrics outside target: {', '.join(failures)}"
        else:
            status = "passing"
            summary = "all metrics meet targets"
        evaluation_id = f"eval-{uuid4().hex}"
        evaluated_at = _utcnow_iso()
        details = {"metrics": metric_results, "missing_metrics": missing, "failed_metrics": failures}
        self.goals.add_evaluation(
            evaluation_id=evaluation_id,
            goal_id=goal_id,
            status=status,
            summary=summary,
            details_json=_json_dumps(details),
            evaluated_by=subject.agent_id,
            evaluated_at=evaluated_at,
        )
        self.goals.update_cached_evaluation(
            goal_id,
            _json_dumps({"last_evaluation_id": evaluation_id, "status": status, "summary": summary}),
        )
        event = self.events.append(
            aggregate_type="goal",
            aggregate_id=goal_id,
            event_type="goal.evaluated",
            actor_id=subject.agent_id,
            payload={"goal_id": goal_id, "domain": goal.domain, "evaluation_id": evaluation_id, "status": status},
            metadata={"milestone": 5, "service": self.__class__.__name__},
        )
        return {
            "id": evaluation_id,
            "goal_id": goal_id,
            "domain": goal.domain,
            "status": status,
            "summary": summary,
            "details": details,
            "evaluated_at": evaluated_at,
            "event_id": event.event_id,
        }

    def _goal_records_for_domain(self, domain_id: str) -> list[GoalRecord]:
        rows = self.goals.list_for_domain(domain_id)
        return [self._goal_from_row(row) for row in rows]

    def _goal_record(self, goal_id: str) -> GoalRecord:
        row = self.goals.get(goal_id)
        if row is None:
            raise UnknownDomainError(f"unknown goal {goal_id}")
        return self._goal_from_row(row)

    def _goal_from_row(self, row: sqlite3.Row) -> GoalRecord:
        metrics = tuple(self._metrics_for_goal(row["id"]))
        return GoalRecord(
            id=row["id"],
            domain=row["domain_id"],
            owner_agent=row["owner_agent_id"],
            status=row["status"],
            window=row["window"],
            description=row["description"],
            metrics=metrics,
            latest_evaluation=self._latest_evaluation(row["id"]),
        )

    def _metrics_for_goal(self, goal_id: str) -> list[dict[str, Any]]:
        rows = self.goals.metrics_for_goal(goal_id)
        return [
            {
                "id": row["metric_id"],
                "type": row["type"],
                "operator": row["operator"],
                "target": _json_loads(row["target_json"]),
                "unit": row["unit"],
            }
            for row in rows
        ]

    def _latest_evaluation(self, goal_id: str) -> dict[str, Any] | None:
        row = self.goals.latest_evaluation(goal_id)
        if row is None:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "summary": row["summary"],
            "details": _json_loads(row["details_json"], {}),
            "evaluated_by": row["evaluated_by"],
            "evaluated_at": row["evaluated_at"],
        }

    def _evidence_for_goal(self, goal_id: str) -> list[dict[str, Any]]:
        rows = self.goals.evidence_for_goal(goal_id)
        return [
            {
                "id": row["id"],
                "domain": row["domain_id"],
                "goal_id": row["goal_id"],
                "uri": row["uri"],
                "kind": row["kind"],
                "summary": row["summary"],
                "payload": _json_loads(row["payload_json"], {}),
                "added_by": row["added_by"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _resolve_evidence(self, goal_id: str, *, evidence_id: str | None) -> sqlite3.Row | None:
        if evidence_id:
            row = self.goals.get_evidence_for_goal(goal_id, evidence_id)
            if row is None:
                raise ValidationError(f"evidence {evidence_id} is not attached to goal {goal_id}")
            return row
        return self.goals.latest_evidence_for_goal(goal_id)

    def _latest_measurements(self, goal_id: str) -> dict[str, dict[str, Any]]:
        rows = self.goals.latest_measurements(goal_id)
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row["metric_id"] in latest:
                continue
            latest[row["metric_id"]] = {
                "id": row["id"],
                "metric_id": row["metric_id"],
                "value": _json_loads(row["value_json"], None),
                "evidence_id": row["evidence_id"],
                "recorded_by": row["recorded_by"],
                "measured_at": row["measured_at"],
            }
        return latest

    @staticmethod
    def _read_evidence_payload(path: Path) -> Any:
        if path.suffix.lower() == ".json":
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"evidence JSON is invalid: {exc}") from exc
        return {"text_excerpt": path.read_text(encoding="utf-8", errors="replace")[:4000]}


def _extract_measurement_values(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    if "measurements" in payload and isinstance(payload["measurements"], Mapping):
        return dict(payload["measurements"])
    if "content" in payload and isinstance(payload["content"], Mapping):
        return _extract_measurement_values(payload["content"])
    scalar_types = (str, int, float, bool, type(None))
    return {key: value for key, value in payload.items() if isinstance(key, str) and isinstance(value, scalar_types)}


def _normalize_value(value: Any, metric_type: str | None) -> Any:
    if value is None:
        return None
    if metric_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "on"}:
                return True
            if lowered in {"false", "0", "no", "n", "off"}:
                return False
        raise ValidationError(f"cannot parse boolean metric value {value!r}")
    if metric_type in {"percentage", "count", "number"}:
        if isinstance(value, bool):
            raise ValidationError(f"boolean is not a numeric metric value: {value!r}")
        if isinstance(value, (int, float)):
            return int(value) if metric_type == "count" and float(value).is_integer() else value
        if isinstance(value, str):
            cleaned = value.strip().rstrip("%")
            try:
                number = float(cleaned)
            except ValueError as exc:
                raise ValidationError(f"cannot parse numeric metric value {value!r}") from exc
            return int(number) if metric_type == "count" and number.is_integer() else number
    return value


def _compare_metric(metric: Mapping[str, Any], value: Any) -> dict[str, Any]:
    operator = metric["operator"]
    target = metric["target"]
    metric_type = metric.get("type")
    if metric_type == "boolean":
        passed = bool(value) == bool(target) if operator == "==" else bool(value) != bool(target)
        return {"status": "passing" if passed else "failing", "near_threshold": False}
    try:
        v = float(value)
        t = float(target)
    except (TypeError, ValueError):
        if operator == "==":
            passed = value == target
        elif operator == "!=":
            passed = value != target
        else:
            raise ValidationError(f"operator {operator!r} requires numeric metric values")
        return {"status": "passing" if passed else "failing", "near_threshold": False}

    if operator == ">=":
        passed = v >= t
        near = not passed and v >= t * 0.9
    elif operator == ">":
        passed = v > t
        near = not passed and v >= t * 0.9
    elif operator == "<=":
        passed = v <= t
        near = not passed and v <= t * 1.1
    elif operator == "<":
        passed = v < t
        near = not passed and v <= t * 1.1
    elif operator == "==":
        passed = v == t
        near = not passed and abs(v - t) <= max(abs(t) * 0.1, 1.0)
    elif operator == "!=":
        passed = v != t
        near = False
    else:
        raise ValidationError(f"unsupported metric operator {operator!r}")
    return {"status": "passing" if passed else "failing", "near_threshold": near}


def parse_metric_values(raw_values: Sequence[str] | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for raw in raw_values or []:
        if "=" not in raw:
            raise ValidationError(f"metric value must use metric=value syntax: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ValidationError("metric value has an empty metric id")
        values[key] = value.strip()
    return values
