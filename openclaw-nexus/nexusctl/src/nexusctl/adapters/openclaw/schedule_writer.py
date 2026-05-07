"""OpenClaw schedule writer for schedule runtime."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable, Mapping
from nexusctl.domain.errors import ValidationError
from .config_writer import DriftResult, ManagedArtifactWriter, WriteResult

class OpenClawScheduleWriter:
    """Render OpenClaw cronjob descriptors from Nexus schedules."""
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.writer = ManagedArtifactWriter(project_root)

    def render_payloads(self, *, schedules: Iterable[Mapping[str, Any]], standing_orders: Mapping[str, Any]) -> list[dict[str, Any]]:
        standing_order_ids = set((standing_orders.get("schedules") or {}).keys())
        payloads: list[dict[str, Any]] = []
        for schedule in sorted(schedules, key=lambda item: str(item.get("id", ""))):
            schedule_id = str(schedule.get("id") or "")
            standing_order_id = str(schedule.get("standing_order") or "")
            if not schedule_id:
                raise ValidationError("schedule id is required")
            if standing_order_id not in standing_order_ids:
                raise ValidationError(f"schedule {schedule_id} references missing standing order {standing_order_id!r}")
            payloads.append({
                "id": schedule_id,
                "agent": str(schedule.get("agent") or ""),
                "domain": str(schedule.get("domain") or ""),
                "cron": str(schedule.get("cron") or ""),
                "enabled": bool(schedule.get("enabled", True)),
                "standing_order": standing_order_id,
                "prompt": (
                    "Run Nexusctl schedule "
                    f"`{schedule_id}` for standing order `{standing_order_id}`. "
                    "Read the standing order from nexus/standing-orders.yml at runtime; "
                    "do not duplicate or reinterpret it in generated cron config. "
                    "Schedule execution is a Nexusctl-controlled run request, not a direct cron mutation."
                ),
                "command": ["nexusctl", "schedules", "run", schedule_id, "--json"],
                "guards": {
                    "domain_source": "auth_token",
                    "standing_order_source": "nexus/standing-orders.yml",
                    "no_manual_generated_edits": True,
                    "source_of_truth": "nexusctl",
                    "mutation_boundary": "nexusctl_schedule_control_flow_only",
                    "agent_direct_cron_mutation_allowed": False,
                },
            })
        return payloads

    def write(self, *, schedules: Iterable[Mapping[str, Any]], standing_orders: Mapping[str, Any]) -> list[WriteResult]:
        results: list[WriteResult] = []
        for payload in self.render_payloads(schedules=schedules, standing_orders=standing_orders):
            results.append(self.writer.write_json(f"generated/openclaw/schedules/{payload['id']}.json", payload, artifact_kind="openclaw_schedule"))
        return results

    def expected_paths(self, schedules: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
        return tuple(f"generated/openclaw/schedules/{str(item.get('id'))}.json" for item in sorted(schedules, key=lambda schedule: str(schedule.get("id", ""))))

    def check(self, schedules: Iterable[Mapping[str, Any]]) -> list[DriftResult]:
        return [self.writer.check_json(path) for path in self.expected_paths(schedules)]
