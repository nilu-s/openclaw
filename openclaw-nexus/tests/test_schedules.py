from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.app.schedule_service import ScheduleService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database


pytestmark = [pytest.mark.integration, pytest.mark.slow]



def subject(project: Path, agent_id: str) -> Subject:
    matrix = CapabilityMatrix.from_project_root(project)
    agent = matrix.agent(agent_id)
    return Subject.create(
        agent_id=agent.id,
        domain=agent.domain,
        role=agent.role,
        capabilities=agent.capabilities,
        normal_agent=agent.normal_agent,
    )


def test_schedules_schedules_validate_render_run_events_and_guardrails(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    schedule_service = ScheduleService(project)

    validated = schedule_service.validate()
    assert validated["ok"] is True
    assert validated["schedule_count"] == 9

    design = schedule_service._load_design()
    rendered = schedule_service.writer.write(
        schedules=design["schedules"],
        standing_orders=design["standing_orders"],
    )
    assert len(rendered) == 9
    assert "generated/openclaw/schedules/trading_goal_daily_evaluation.json" in {item.path for item in rendered}

    schedule_doc = json.loads((project / "generated/openclaw/schedules/trading_goal_daily_evaluation.json").read_text())
    assert schedule_doc["cron"] == "30 6 * * *"
    assert schedule_doc["standing_order"] == "trading.trading_goal_daily_evaluation"
    assert "Read the standing order from nexus/standing-orders.yml" in schedule_doc["prompt"]
    assert "not a direct cron mutation" in schedule_doc["prompt"]
    assert schedule_doc["guards"]["source_of_truth"] == "nexusctl"
    assert schedule_doc["guards"]["mutation_boundary"] == "nexusctl_schedule_control_flow_only"
    assert schedule_doc["guards"]["agent_direct_cron_mutation_allowed"] is False
    assert "Measure and evaluate trading goals" not in schedule_doc["prompt"]

    reconciled = schedule_service.reconcile_openclaw()
    assert reconciled["ok"] is True
    assert reconciled["drift_count"] == 0

    db = tmp_path / "nexus.db"
    connection = connect_database(db)
    try:
        init_database(connection, project, seed_blueprint=True)
        connection.commit()
        secured_service = ScheduleService(
            project,
            connection=connection,
            policy=PolicyEngine(CapabilityMatrix.from_project_root(project)),
        )
        payload = secured_service.run(subject(project, "trading-analyst"), "trading_goal_daily_evaluation", dry_run=True)
        assert payload["status"] == "dry_run"
        assert "feature_request.create" in payload["allowed_effects"]
        assert all("software" not in effect for effect in payload["allowed_effects"])
        connection.commit()
    finally:
        connection.close()

    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT schedule_id, status FROM schedule_runs").fetchall()
        event_types = [row[0] for row in con.execute("SELECT event_type FROM events WHERE aggregate_type = 'schedule'").fetchall()]
    finally:
        con.close()
    assert rows == [("trading_goal_daily_evaluation", "dry_run")]
    assert "schedule.run.dry_run" in event_types

    schedules = project / "nexus" / "schedules.yml"
    data = yaml.safe_load(schedules.read_text(encoding="utf-8"))
    assert data["guardrails"]["schedule_source_of_truth"] == "nexusctl"
    assert data["guardrails"]["cronjobs_mutated_by"] == "nexusctl_schedule_control_flow"
    assert data["guardrails"]["agents_may_edit_runtime_cronjobs_directly"] is False
    data["schedules"].append(
        {
            "id": "illegal_builder_cron",
            "domain": "software",
            "agent": "software-builder",
            "cron": "* * * * *",
            "standing_order": "software.software_review_queue_check",
            "enabled": True,
        }
    )
    schedules.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    invalid = ScheduleService(project).validate()
    assert invalid["ok"] is False
    assert any("software-builder" in error for error in invalid["errors"])
