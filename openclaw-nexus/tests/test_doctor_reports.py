from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3

import pytest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.interfaces.cli.main import main as cli_main


pytestmark = [pytest.mark.integration, pytest.mark.slow]


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def run_cli(args: list[str], *, env: dict[str, str] | None = None) -> CliResult:
    old_env = os.environ.copy()
    os.environ.update(env or {})
    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = cli_main(args)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    return CliResult(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())



def login(db: Path, project: Path, agent: str = "platform-maintainer") -> str:
    result = run_cli(["auth", "login", "--agent", agent, "--db", str(db), "--project-root", str(project), "--json"])
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["credential"]["token"]


def test_doctor_reports_doctor_json_reports_status_codes_alerts_and_audit_chain(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    login(db, project)

    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO feature_requests(id, source_domain_id, target_domain_id, created_by, goal_id, summary, status)
            VALUES ('fr-doctor-reports', 'trading', 'software', 'trading-analyst', NULL, 'doctor reports audit chain smoke', 'accepted')
            """
        )
        connection.execute(
            """
            INSERT INTO github_alerts(id, severity, status, kind, summary)
            VALUES ('alert-doctor-reports-critical', 'critical', 'open', 'manual_merge_or_security_alert', 'critical alert blocks merge')
            """
        )

    doctor = run_cli(["doctor", "--project-root", str(project), "--db", str(db), "--json"])
    assert doctor.returncode == 1, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    assert payload["status_code"] == "critical"
    assert payload["status_codes"]["alerts"] == "critical"
    assert payload["critical_alert_count"] == 1
    assert payload["alerts"][0]["blocks_merge"] is True
    assert "block merge gates" in payload["summary"]
    assert any(chain["feature_request_id"] == "fr-doctor-reports" for chain in payload["audit_chains"])


def test_doctor_reports_doctor_explains_generated_artifact_drift_and_human_summary(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    token = login(db, project)

    generated = run_cli(["generate", "all", "--db", str(db), "--project-root", str(project), "--json"], env={"NEXUSCTL_TOKEN": token})
    assert generated.returncode == 0, generated.stderr or generated.stdout

    tools_md = project / "generated" / "agents" / "software-builder" / "TOOLS.md"
    tools_md.write_text(tools_md.read_text(encoding="utf-8") + "\nmanual doctor reports drift\n", encoding="utf-8")

    doctor = run_cli(["doctor", "--project-root", str(project), "--db", str(db), "--json"])
    assert doctor.returncode == 1
    payload = json.loads(doctor.stdout)
    drift_item = next(item for item in payload["drift"] if item["path"] == "generated/agents/software-builder/TOOLS.md")
    assert drift_item["status_code"] == "generated_artifact_drift"
    assert "nexusctl generate all" in drift_item["action"]
    assert payload["status_codes"]["generated_artifacts"] == "drift"

    human = run_cli(["doctor", "--project-root", str(project), "--db", str(db)])
    assert human.returncode == 1
    assert "doctor: drift" in human.stdout
    assert "generated artifacts: drift" in human.stdout


def test_doctor_reports_event_integrity_and_database_status(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    token = login(db, project)

    generated = run_cli(["generate", "all", "--db", str(db), "--project-root", str(project), "--json"], env={"NEXUSCTL_TOKEN": token})
    assert generated.returncode == 0, generated.stderr or generated.stdout

    doctor = run_cli(["doctor", "--project-root", str(project), "--db", str(db), "--json"])
    assert doctor.returncode == 0, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    assert payload["status_codes"]["event_integrity"] == "ok"
    assert payload["event_integrity"]["valid"] is True
    assert payload["event_integrity"]["checked_events"] >= 1
    assert payload["database"]["status_code"] == "ok"
    assert payload["database"]["schema_version"] == payload["database"]["latest_schema_version"]


def test_doctor_reports_tampered_event_state_as_non_green(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    token = login(db, project)

    generated = run_cli(["generate", "all", "--db", str(db), "--project-root", str(project), "--json"], env={"NEXUSCTL_TOKEN": token})
    assert generated.returncode == 0, generated.stderr or generated.stdout

    with sqlite3.connect(db) as connection:
        connection.execute("DROP TRIGGER IF EXISTS events_append_only_no_update")
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            ('{"tampered":true}', json.loads(generated.stdout)["event_id"]),
        )

    doctor = run_cli(["doctor", "--project-root", str(project), "--db", str(db), "--json"])
    assert doctor.returncode == 1, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    assert payload["ok"] is False
    assert payload["status_codes"]["event_integrity"] == "invalid"
    assert payload["event_integrity"]["valid"] is False
    assert "event_hash mismatch" in payload["event_integrity"]["first_error"]
    assert "event integrity invalid" in payload["summary"]


def test_doctor_reports_operational_warnings_without_leaking_secrets(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    login(db, project)

    doctor = run_cli(
        ["doctor", "--project-root", str(project), "--db", str(db), "--json"],
        env={"NEXUSCTL_API_HOST": "0.0.0.0", "GITHUB_WEBHOOK_SECRET": "change-me"},
    )
    assert doctor.returncode == 1, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    assert payload["status_codes"]["operations"] == "critical"
    rendered = json.dumps(payload)
    assert "change-me" not in rendered
    assert any(warning["status_code"] == "remote_binding_without_tls" for warning in payload["operational_warnings"])
    assert any(warning["status_code"] == "placeholder_secret" for warning in payload["operational_warnings"])


def test_doctor_reports_internal_production_readiness_contract(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    backup_dir = tmp_path / "backups"
    evidence_dir = tmp_path / "recovery-evidence"
    workspaces_dir = tmp_path / "workspaces"
    worktrees_dir = tmp_path / "repo-worktrees"
    backup_dir.mkdir()
    evidence_dir.mkdir()
    workspaces_dir.mkdir()
    worktrees_dir.mkdir()
    login(db, project)

    doctor = run_cli(
        ["doctor", "--project-root", str(project), "--db", str(db), "--json"],
        env={
            "NEXUSCTL_DEPLOYMENT_MODE": "internal-production",
            "NEXUSCTL_API_HOST": "0.0.0.0",
            "NEXUSCTL_API_TLS_ENABLED": "1",
            "NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND": "0",
            "NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED": "1",
            "GITHUB_WEBHOOK_SECRET": "real-secret-not-rendered",
            "NEXUSCTL_DB": str(db),
            "NEXUSCTL_BACKUP_DIR": str(backup_dir),
            "NEXUSCTL_RECOVERY_EVIDENCE_DIR": str(evidence_dir),
            "NEXUSCTL_BACKUP_RETENTION_DAYS": "30",
            "NEXUSCTL_BACKUP_RETENTION_MIN_COPIES": "7",
            "NEXUSCTL_OFFSITE_BACKUP_ENABLED": "1",
            "NEXUSCTL_OFFSITE_BACKUP_TARGET": "internal-vault-metadata-only",
            "NEXUSCTL_OFFSITE_BACKUP_SCHEDULE": "daily",
            "NEXUSCTL_WORKSPACES_DIR": str(workspaces_dir),
            "NEXUSCTL_REPO_WORKTREES_DIR": str(worktrees_dir),
        },
    )
    assert doctor.returncode == 0, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    readiness = {item["id"]: item for item in payload["operational_readiness"]}

    assert payload["status_codes"]["operations"] == "ok"
    preflight = payload["internal_production_preflight"]
    assert preflight["required_before_internal_production_cutover"] is True
    assert preflight["status_code"] == "ok"
    assert preflight["cutover_blockers"] == []
    assert preflight["expected_json_fields"] == [
        "status_code",
        "status_codes",
        "operational_readiness",
        "operational_warnings",
        "database",
        "event_integrity",
        "github_webhook_contract",
        "internal_production_preflight",
    ]
    assert preflight["command_sequence"] == [
        "load_internal_production_env",
        "nexusctl_db_init_or_migrate",
        "nexusctl_doctor_json",
        "nexusctl_db_restore_drill_json_with_evidence_path",
        "operator_cutover_decision",
    ]
    assert "restore-drill" in preflight["recovery_evidence"]["command"]
    assert preflight["recovery_evidence"]["manifest_required"] is True
    assert preflight["external_operator_evidence_required"] == [
        "offsite_backup_copy",
        "retention_policy_enforcement",
        "monitoring_alert_routing",
        "secret_management_and_rotation",
        "tls_or_reverse_proxy_boundary",
        "worm_or_external_audit_evidence_if_required_by_operator",
        "github_live_sandbox_evidence_when_webhooks_are_enabled",
    ]
    assert readiness["api_binding"]["status_code"] == "ok"
    assert readiness["github_webhook_secret"]["status_code"] == "ok"
    assert readiness["backup_restore_runbook"]["status_code"] == "ok"
    assert readiness["audit_integrity_check"]["status_code"] == "ok"
    assert readiness["github_webhook_contract"]["status_code"] == "ok"
    assert readiness["recovery_evidence_path"]["status_code"] == "ok"
    assert readiness["backup_retention_policy"]["status_code"] == "ok"
    assert readiness["offsite_backup_control"]["status_code"] == "ok"
    assert readiness["monitoring_alert_runbook"]["status_code"] == "ok"
    assert readiness["operator_managed_controls"]["status_code"] == "ok"
    assert payload["status_codes"]["github_webhook_contract"] == "ok"
    assert payload["github_webhook_contract"]["authority"]["nexusctl_lifecycle_authority"] is True
    assert payload["github_webhook_contract"]["authority"]["github_lifecycle_authority"] is False
    assert {"issues", "pull_request", "pull_request_review", "check_run"}.issubset(set(payload["github_webhook_contract"]["fixture_backed_events"]))
    assert "duplicate_delivery_idempotent_for_same_payload" in payload["github_webhook_contract"]["negative_webhook_contracts"]
    live_contract = payload["github_webhook_contract"]["live_sandbox_verification"]
    assert live_contract["required_before_internal_production_cutover"] is True
    assert live_contract["fixture_green_is_not_live_green"] is True
    assert live_contract["secret_free"] is True
    assert live_contract["runbook"] == "docs/operations/internal-production.md#github-live-sandbox-verifikation"
    assert {
        "webhook_delivery_ids",
        "projection_work_item_id",
        "review_signal_status",
        "check_run_signal_status",
        "label_drift_status",
        "unauthorized_merge_alert_id",
        "negative_signature_result",
        "redactions_applied",
    }.issubset(set(live_contract["evidence_fields"]))
    assert readiness["github_webhook_contract"]["action"].startswith("Run the secret-free GitHub live-sandbox verification")
    assert "doctor readiness" in readiness["monitoring_alert_runbook"]["summary"].lower()
    assert "product-local evidence" in readiness["operator_managed_controls"]["summary"]
    assert "real-secret-not-rendered" not in json.dumps(payload)


def test_doctor_reports_internal_production_flags_missing_github_webhook_fixture(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    backup_dir = tmp_path / "backups"
    evidence_dir = tmp_path / "recovery-evidence"
    workspaces_dir = tmp_path / "workspaces"
    worktrees_dir = tmp_path / "repo-worktrees"
    backup_dir.mkdir()
    evidence_dir.mkdir()
    workspaces_dir.mkdir()
    worktrees_dir.mkdir()
    (project / "tests" / "fixtures" / "github" / "check_run_completed_failure.json").unlink()
    login(db, project)

    doctor = run_cli(
        ["doctor", "--project-root", str(project), "--db", str(db), "--json"],
        env={
            "NEXUSCTL_DEPLOYMENT_MODE": "internal-production",
            "NEXUSCTL_API_HOST": "0.0.0.0",
            "NEXUSCTL_API_TLS_ENABLED": "1",
            "NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND": "0",
            "NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED": "1",
            "GITHUB_WEBHOOK_SECRET": "real-secret-not-rendered",
            "NEXUSCTL_DB": str(db),
            "NEXUSCTL_BACKUP_DIR": str(backup_dir),
            "NEXUSCTL_RECOVERY_EVIDENCE_DIR": str(evidence_dir),
            "NEXUSCTL_BACKUP_RETENTION_DAYS": "30",
            "NEXUSCTL_BACKUP_RETENTION_MIN_COPIES": "7",
            "NEXUSCTL_OFFSITE_BACKUP_ENABLED": "1",
            "NEXUSCTL_OFFSITE_BACKUP_TARGET": "internal-vault-metadata-only",
            "NEXUSCTL_OFFSITE_BACKUP_SCHEDULE": "daily",
            "NEXUSCTL_WORKSPACES_DIR": str(workspaces_dir),
            "NEXUSCTL_REPO_WORKTREES_DIR": str(worktrees_dir),
        },
    )
    assert doctor.returncode == 1, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    readiness = {item["id"]: item for item in payload["operational_readiness"]}

    assert payload["status_codes"]["operations"] == "critical"
    assert payload["status_codes"]["github_webhook_contract"] == "fixture_missing"
    assert readiness["github_webhook_contract"]["status_code"] == "github_webhook_contract_incomplete"
    assert readiness["github_webhook_contract"]["severity"] == "critical"
    assert payload["github_webhook_contract"]["missing_fixtures"] == ["check_run_completed_failure.json"]
    assert "real-secret-not-rendered" not in json.dumps(payload)


def test_doctor_reports_development_opt_ins_are_not_internal_production_green(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    login(db, project)

    doctor = run_cli(
        ["doctor", "--project-root", str(project), "--db", str(db), "--json"],
        env={
            "NEXUSCTL_DEPLOYMENT_MODE": "internal-production",
            "NEXUSCTL_API_HOST": "0.0.0.0",
            "NEXUSCTL_API_TLS_ENABLED": "0",
            "NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND": "1",
            "NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED": "1",
            "GITHUB_WEBHOOK_SECRET": "change-me",
        },
    )
    assert doctor.returncode == 1, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    assert payload["status_codes"]["operations"] == "critical"
    preflight = payload["internal_production_preflight"]
    blocker_ids = {item["id"] for item in preflight["cutover_blockers"]}
    assert preflight["status_code"] == "blocked"
    assert {
        "api_insecure_remote_binding_opt_in",
        "github_webhook_secret_required",
        "sqlite_data_path",
        "backup_path",
        "workspaces_path",
        "repo_worktrees_path",
        "recovery_evidence_path",
        "backup_retention_policy",
        "offsite_backup_control",
    }.issubset(blocker_ids)
    assert any(item["status_code"] == "insecure_remote_binding" and item["severity"] == "critical" for item in payload["operational_readiness"])
    assert any(item["status_code"] == "webhook_secret_missing" for item in payload["operational_readiness"])
    assert any(item["status_code"] == "persistent_path_missing" for item in payload["operational_readiness"])
    assert any(item["status_code"] == "recovery_evidence_path_missing" for item in payload["operational_readiness"])
    assert any(item["status_code"] == "backup_retention_policy_missing" for item in payload["operational_readiness"])
    assert any(item["status_code"] == "offsite_backup_control_missing" for item in payload["operational_readiness"])
    assert any(item["id"] == "monitoring_alert_runbook" and item["status_code"] == "ok" for item in payload["operational_readiness"])
    assert any(item["id"] == "operator_managed_controls" and item["status_code"] == "ok" for item in payload["operational_readiness"])


def test_doctor_reports_internal_production_recovery_controls_are_secret_free(tmp_path: Path, repo_project_copy: Path) -> None:
    project = repo_project_copy
    db = tmp_path / "nexus.db"
    backup_dir = tmp_path / "backups"
    workspaces_dir = tmp_path / "workspaces"
    worktrees_dir = tmp_path / "repo-worktrees"
    backup_dir.mkdir()
    workspaces_dir.mkdir()
    worktrees_dir.mkdir()
    login(db, project)

    doctor = run_cli(
        ["doctor", "--project-root", str(project), "--db", str(db), "--json"],
        env={
            "NEXUSCTL_DEPLOYMENT_MODE": "internal-production",
            "NEXUSCTL_API_HOST": "0.0.0.0",
            "NEXUSCTL_API_TLS_ENABLED": "1",
            "NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED": "1",
            "GITHUB_WEBHOOK_SECRET": "real-secret-not-rendered",
            "NEXUSCTL_DB": str(db),
            "NEXUSCTL_BACKUP_DIR": str(backup_dir),
            "NEXUSCTL_WORKSPACES_DIR": str(workspaces_dir),
            "NEXUSCTL_REPO_WORKTREES_DIR": str(worktrees_dir),
            "NEXUSCTL_OFFSITE_BACKUP_TARGET": "s3://bucket-without-secret-value",
        },
    )

    assert doctor.returncode == 1, doctor.stderr or doctor.stdout
    payload = json.loads(doctor.stdout)
    readiness = {item["id"]: item for item in payload["operational_readiness"]}
    assert payload["status_codes"]["operations"] == "critical"
    assert readiness["recovery_evidence_path"]["status_code"] == "recovery_evidence_path_missing"
    assert readiness["backup_retention_policy"]["status_code"] == "backup_retention_policy_missing"
    assert readiness["offsite_backup_control"]["status_code"] == "offsite_backup_control_missing"
    rendered = json.dumps(payload)
    assert "real-secret-not-rendered" not in rendered
    assert "s3://bucket-without-secret-value" not in rendered
