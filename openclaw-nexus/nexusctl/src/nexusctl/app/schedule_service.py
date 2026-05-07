"""Schedule service for schedule runtime."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from uuid import uuid4
import yaml
from nexusctl.adapters.openclaw.schedule_writer import OpenClawScheduleWriter
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import ValidationError
from nexusctl.storage.event_store import EventStore

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class ScheduleService:
    """Validate, render, reconcile, and dry-run scheduled Nexus tasks."""
    MVP_SCHEDULE_IDS = {
        "control_router_domain_inbox_triage", "control_router_scope_expiry_guard",
        "software_review_queue_check", "software_release_readiness",
        "trading_goal_daily_evaluation", "trading_risk_daily_audit", "trading_feature_need_detection",
        "platform_generated_runtime_drift", "platform_db_backup",
    }
    def __init__(self, project_root: str | Path, *, connection: sqlite3.Connection | None = None, policy: PolicyEngine | None = None) -> None:
        self.project_root = Path(project_root)
        self.connection = connection
        self.policy = policy
        self.writer = OpenClawScheduleWriter(self.project_root)

    def list(self, subject: Subject | None = None) -> dict[str, Any]:
        if subject is not None:
            self._require(subject, "schedule.read", resource_domain=subject.domain)
        data = self._load_design()
        return {"ok": True, "schedule_count": len(data["schedules"]), "schedules": data["schedules"]}

    def validate(self, subject: Subject | None = None) -> dict[str, Any]:
        if subject is not None:
            self._require(subject, "schedule.read", resource_domain=subject.domain)
        data = self._load_design()
        errors = self._validation_errors(data)
        return {"ok": not errors, "schedule_count": len(data["schedules"]), "mvp_schedule_count": len(self.MVP_SCHEDULE_IDS), "errors": errors}

    def render_openclaw(self, subject: Subject) -> dict[str, Any]:
        self._require(subject, "runtime.generate", resource_domain=subject.domain)
        data = self._load_design()
        errors = self._validation_errors(data)
        if errors:
            raise ValidationError("schedule validation failed: " + "; ".join(errors))
        results = self.writer.write(schedules=data["schedules"], standing_orders=data["standing_orders"])
        event_id = self._append_event(subject, "schedule.openclaw.rendered", payload={"artifact_count": len(results), "changed_count": sum(1 for result in results if result.changed), "paths": [result.path for result in results]})
        return {"ok": True, "artifact_count": len(results), "changed_count": sum(1 for result in results if result.changed), "artifacts": [asdict(result) for result in results], **({"event_id": event_id} if event_id else {})}

    def reconcile_openclaw(self, subject: Subject | None = None) -> dict[str, Any]:
        if subject is not None:
            self._require(subject, "runtime.validate", resource_domain=subject.domain)
        data = self._load_design()
        checks = self.writer.check(data["schedules"])
        check_dicts = [asdict(check) for check in checks]
        drift = [item for item in check_dicts if item["status"] != "ok"]
        return {"ok": not drift, "artifact_count": len(checks), "drift_count": len(drift), "drift": drift, "checks": check_dicts}

    def run(self, subject: Subject, schedule_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        data = self._load_design()
        schedule = next((item for item in data["schedules"] if item["id"] == schedule_id), None)
        if schedule is None:
            raise ValidationError(f"unknown schedule: {schedule_id}")
        self._require(subject, "schedule.run", resource_domain=str(schedule["domain"]))
        if str(schedule["agent"]) == "software-builder":
            raise ValidationError("software-builder schedules are forbidden; no autonomous builder cronjobs")
        standing_order_text = data["standing_orders"].get("schedules", {}).get(schedule["standing_order"])
        if not standing_order_text:
            raise ValidationError(f"schedule {schedule_id} has no standing order text")
        run_id = f"schedrun-{uuid4().hex}"
        status = "dry_run" if dry_run else "queued"
        output = {"dry_run": dry_run, "schedule": schedule, "standing_order_ref": schedule["standing_order"], "standing_order_summary": standing_order_text, "allowed_effects": self._allowed_effects(schedule)}
        event_id = self._record_run(subject, run_id=run_id, schedule=schedule, status=status, output=output)
        return {"ok": True, "run_id": run_id, "status": status, "event_id": event_id, **output}

    def _allowed_effects(self, schedule: Mapping[str, Any]) -> list[str]:
        domain = str(schedule.get("domain"))
        if domain == "trading": return ["goal.measure", "goal.evaluate", "feature_request.create"]
        if domain == "software": return ["work.read", "review.queue", "policy.check"]
        if domain == "platform": return ["runtime.validate", "runtime.generate", "backup.create"]
        return ["feature_request.route", "scope.lease.revoke", "policy.check"]

    def _record_run(self, subject: Subject, *, run_id: str, schedule: Mapping[str, Any], status: str, output: Mapping[str, Any]) -> str | None:
        if self.connection is None:
            return None
        now = _utcnow_iso()
        self.connection.execute("""INSERT INTO schedule_runs(id, schedule_id, agent_id, domain_id, status, started_at, finished_at, output_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (run_id, str(schedule["id"]), str(schedule["agent"]), str(schedule["domain"]), status, now, now, json.dumps(dict(output), sort_keys=True)))
        event = EventStore(self.connection).append(aggregate_type="schedule", aggregate_id=str(schedule["id"]), event_type="schedule.run.dry_run" if status == "dry_run" else "schedule.run.queued", actor_id=subject.agent_id, payload={"run_id": run_id, "status": status, "schedule_id": str(schedule["id"])}, metadata={"milestone": 15, "standing_order": str(schedule.get("standing_order"))})
        return event.event_id

    def _validation_errors(self, data: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        schedules = data["schedules"]
        agents_by_id = {str(item.get("id")): item for item in data["agents"]}
        standing_schedule_orders = data["standing_orders"].get("schedules") or {}
        seen: set[str] = set()
        for schedule in schedules:
            schedule_id = str(schedule.get("id") or "")
            if not schedule_id:
                errors.append("schedule without id"); continue
            if schedule_id in seen: errors.append(f"duplicate schedule id: {schedule_id}")
            seen.add(schedule_id)
            if schedule_id not in self.MVP_SCHEDULE_IDS: errors.append(f"non-MVP schedule present: {schedule_id}")
            agent_id = str(schedule.get("agent") or "")
            agent = agents_by_id.get(agent_id)
            if agent is None:
                errors.append(f"{schedule_id}: unknown agent {agent_id!r}"); continue
            if agent_id == "software-builder": errors.append(f"{schedule_id}: autonomous software-builder cronjobs are forbidden")
            if str(agent.get("domain")) != str(schedule.get("domain")): errors.append(f"{schedule_id}: agent domain does not match schedule domain")
            if not str(schedule.get("cron") or "").strip(): errors.append(f"{schedule_id}: cron expression is required")
            standing_ref = str(schedule.get("standing_order") or "")
            if standing_ref not in standing_schedule_orders: errors.append(f"{schedule_id}: standing_order {standing_ref!r} is missing")
        missing_mvp = sorted(self.MVP_SCHEDULE_IDS - seen)
        if missing_mvp: errors.append("missing MVP schedules: " + ", ".join(missing_mvp))
        guardrails = data.get("guardrails") or {}
        if guardrails.get("autonomous_builder_cronjobs_allowed") is not False: errors.append("guardrail autonomous_builder_cronjobs_allowed must be false")
        if guardrails.get("cron_prompts_duplicate_standing_orders") is not False: errors.append("guardrail cron_prompts_duplicate_standing_orders must be false")
        if guardrails.get("schedule_source_of_truth") != "nexusctl": errors.append("guardrail schedule_source_of_truth must be nexusctl")
        if guardrails.get("cronjobs_mutated_by") != "nexusctl_schedule_control_flow": errors.append("guardrail cronjobs_mutated_by must be nexusctl_schedule_control_flow")
        if guardrails.get("agents_may_edit_runtime_cronjobs_directly") is not False: errors.append("guardrail agents_may_edit_runtime_cronjobs_directly must be false")
        return errors

    def _require(self, subject: Subject, capability_id: str, *, resource_domain: str | None = None) -> None:
        if self.policy is not None:
            self.policy.require(subject, capability_id, resource_domain=resource_domain)

    def _append_event(self, subject: Subject, event_type: str, *, payload: Mapping[str, Any]) -> str | None:
        if self.connection is None: return None
        event = EventStore(self.connection).append(aggregate_type="schedule", aggregate_id="openclaw", event_type=event_type, actor_id=subject.agent_id, payload=dict(payload), metadata={"milestone": 15, "source": "nexus/schedules.yml"})
        return event.event_id

    def _load_design(self) -> dict[str, Any]:
        agents_yml = self._load_yaml("nexus/agents.yml")
        schedules_yml = self._load_yaml("nexus/schedules.yml")
        standing_orders_yml = self._load_yaml("nexus/standing-orders.yml")
        agents = agents_yml.get("agents") or []
        schedules = schedules_yml.get("schedules") or []
        if not isinstance(agents, list): raise ValidationError("nexus/agents.yml agents must be a list")
        if not isinstance(schedules, list): raise ValidationError("nexus/schedules.yml schedules must be a list")
        normalized = []
        for item in schedules:
            if not isinstance(item, dict): raise ValidationError("each schedule must be a mapping")
            normalized.append({"id": str(item.get("id") or ""), "domain": str(item.get("domain") or ""), "agent": str(item.get("agent") or ""), "cron": str(item.get("cron") or ""), "standing_order": str(item.get("standing_order") or ""), "enabled": bool(item.get("enabled", True))})
        return {"agents": agents, "schedules": normalized, "standing_orders": standing_orders_yml, "guardrails": schedules_yml.get("guardrails") or {}}

    def _load_yaml(self, rel_path: str) -> dict[str, Any]:
        path = self.project_root / rel_path
        if not path.is_file(): raise ValidationError(f"missing design file: {rel_path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict): raise ValidationError(f"{rel_path} must contain a mapping")
        return data
