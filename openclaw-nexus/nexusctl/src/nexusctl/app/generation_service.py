"""OpenClaw runtime artifact generation service for OpenClaw generation."""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

import yaml

from nexusctl.adapters.github.webhooks import SUPPORTED_WEBHOOK_EVENTS
from nexusctl.adapters.openclaw.agent_writer import OpenClawAgentWriter
from nexusctl.adapters.openclaw.config_writer import DriftResult, OpenClawConfigWriter, WriteResult
from nexusctl.adapters.openclaw.schedule_writer import OpenClawScheduleWriter
from nexusctl.adapters.openclaw.skill_writer import OpenClawSkillWriter
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import ValidationError
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.migrations import MIGRATIONS, applied_versions
from nexusctl.storage.sqlite.schema import MVP_TABLES, table_exists


GITHUB_WEBHOOK_FIXTURE_CONTRACT: dict[str, str] = {
    "issues": "issues_labeled.json",
    "pull_request": "pull_request_closed_merged.json",
    "pull_request_review": "pull_request_review_submitted.json",
    "check_run": "check_run_completed_failure.json",
}

GITHUB_WEBHOOK_PROCESSING_STATUSES: tuple[str, ...] = ("pending", "processed", "alerted", "ignored", "dead_letter")

GITHUB_LIVE_SANDBOX_EVIDENCE_FIELDS: tuple[str, ...] = (
    "run_id",
    "timestamp_utc",
    "environment",
    "github_app_installation_id_hash",
    "repository_slug_hash",
    "webhook_delivery_ids",
    "nexus_doctor_status_code",
    "projection_issue_number",
    "projection_work_item_id",
    "review_signal_status",
    "check_run_signal_status",
    "label_drift_status",
    "unauthorized_merge_alert_id",
    "negative_signature_result",
    "operator_result",
    "redactions_applied",
)

OPERATIONAL_MONITORING_RUNBOOK_FRAGMENTS: tuple[str, ...] = (
    "## Monitoring- und Alert-Reaktion",
    "Doctor-/Readiness-Alarm",
    "GitHub-Reconciliation-Alert",
    "Restore-Drill-/Recovery-Evidence-Alarm",
    "operator_control_boundaries",
)

OPERATOR_MANAGED_CONTROL_FRAGMENTS: tuple[str, ...] = (
    "Produktbestandteil",
    "Betreiberpflicht",
    "Reverse Proxy/TLS",
    "Secret Management",
    "Offsite-Replikation",
    "WORM/Object-Lock",
    "externe Audit-Signaturen",
    "Monitoring-System",
)

INTERNAL_PRODUCTION_PREFLIGHT_JSON_FIELDS: tuple[str, ...] = (
    "status_code",
    "status_codes",
    "operational_readiness",
    "operational_warnings",
    "database",
    "event_integrity",
    "github_webhook_contract",
    "internal_production_preflight",
)

INTERNAL_PRODUCTION_PREFLIGHT_COMMAND_SEQUENCE: tuple[str, ...] = (
    "load_internal_production_env",
    "nexusctl_db_init_or_migrate",
    "nexusctl_doctor_json",
    "nexusctl_db_restore_drill_json_with_evidence_path",
    "operator_cutover_decision",
)

INTERNAL_PRODUCTION_PREFLIGHT_EXTERNAL_EVIDENCE: tuple[str, ...] = (
    "offsite_backup_copy",
    "retention_policy_enforcement",
    "monitoring_alert_routing",
    "secret_management_and_rotation",
    "tls_or_reverse_proxy_boundary",
    "worm_or_external_audit_evidence_if_required_by_operator",
    "github_live_sandbox_evidence_when_webhooks_are_enabled",
)

SECRET_FIXTURE_MARKERS: tuple[str, ...] = (
    "ghp_",
    "github_pat_",
    "-----BEGIN",
    "GITHUB_WEBHOOK_SECRET=",
    "real-secret",
    "private_key",
)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


class GenerationService:
    """Generate and validate derived OpenClaw artifacts from ``nexus/*.yml``."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        connection: sqlite3.Connection | None = None,
        policy: PolicyEngine | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.connection = connection
        self.policy = policy
        self.config_writer = OpenClawConfigWriter(self.project_root)
        self.agent_writer = OpenClawAgentWriter(self.project_root)
        self.skill_writer = OpenClawSkillWriter(self.project_root)
        self.schedule_writer = OpenClawScheduleWriter(self.project_root)

    def generate_openclaw(self, subject: Subject) -> dict[str, Any]:
        self._require_generate(subject)
        data = self._load_design()
        result = self.config_writer.write(
            agents=data["agents"],
            schedules=data["schedules"],
            guardrails=data.get("schedule_guardrails", {}),
        )
        event_id = self._append_event(subject, "runtime.openclaw_config.generated", [result])
        return self._payload("openclaw", [result], event_id=event_id)

    def generate_agents(self, subject: Subject) -> dict[str, Any]:
        self._require_generate(subject)
        data = self._load_design()
        results = self.agent_writer.write_agents(
            agents=data["agents"],
            standing_orders=data["standing_orders"],
            skill_descriptions=data["skill_descriptions"],
        )
        event_id = self._append_event(subject, "runtime.agent_markdown.generated", results)
        return self._payload("agents", results, event_id=event_id)

    def generate_skills(self, subject: Subject) -> dict[str, Any]:
        self._require_generate(subject)
        data = self._load_design()
        results = self.skill_writer.write_skills(
            agents=data["agents"],
            skills=data["skills"],
            capabilities_by_id=data["capabilities_by_id"],
        )
        event_id = self._append_event(subject, "runtime.skills.generated", results)
        return self._payload("skills", results, event_id=event_id)

    def generate_all(self, subject: Subject) -> dict[str, Any]:
        self._require_generate(subject)
        data = self._load_design()
        results: list[WriteResult] = []
        results.append(
            self.config_writer.write(
                agents=data["agents"],
                schedules=data["schedules"],
                guardrails=data.get("schedule_guardrails", {}),
            )
        )
        results.extend(
            self.agent_writer.write_agents(
                agents=data["agents"],
                standing_orders=data["standing_orders"],
                skill_descriptions=data["skill_descriptions"],
            )
        )
        results.extend(
            self.skill_writer.write_skills(
                agents=data["agents"],
                skills=data["skills"],
                capabilities_by_id=data["capabilities_by_id"],
            )
        )
        results.extend(
            self.schedule_writer.write(
                schedules=data["schedules"],
                standing_orders=data["standing_orders"],
            )
        )
        event_id = self._append_event(subject, "runtime.generated", results)
        return self._payload("all", results, event_id=event_id)

    def doctor(self) -> dict[str, Any]:
        """Return a structured operational health report for generated runtime and projections.

        The doctor output is the stable target-version machine contract. The
        machine-readable fields (``ok``, ``status_code``, ``drift_count``, ``drift``
        and ``checks``) stay stable while doctor reports layer status codes,
        actionable summaries, GitHub projection health, open alerts and an audit
        chain on top so the report explains what to do next instead of only saying
        that drift exists.
        """

        data = self._load_design()
        checks = []
        checks.extend(self.config_writer.check())
        checks.extend(self.agent_writer.check(data["agents"]))
        checks.extend(self.skill_writer.check(agents=data["agents"], skills=data["skills"]))
        checks.extend(self.schedule_writer.check(data["schedules"]))
        check_dicts = [self._doctor_check_payload(asdict(check)) for check in checks]
        drift = [item for item in check_dicts if item["status"] != "ok"]

        alerts = self._doctor_open_alerts()
        critical_alerts = [alert for alert in alerts if alert["severity"] == "critical"]
        github_projection = self._doctor_github_projection()
        audit_chains = self._doctor_audit_chains()
        event_integrity = self._doctor_event_integrity()
        database = self._doctor_database_status()
        github_webhook_contract = self._doctor_github_webhook_contract()
        operational_readiness = self._doctor_operational_readiness(
            event_integrity=event_integrity,
            github_webhook_contract=github_webhook_contract,
        )
        internal_production_preflight = self._doctor_internal_production_preflight(
            operational_readiness=operational_readiness,
            event_integrity=event_integrity,
            database=database,
        )
        operational_warnings = [item for item in operational_readiness if item["severity"] in {"warning", "critical"}]
        critical_operational_warnings = [warning for warning in operational_warnings if warning["severity"] == "critical"]
        status_codes = {
            "generated_artifacts": "drift" if drift else "ok",
            "github_projection": github_projection["status_code"],
            "alerts": "critical" if critical_alerts else ("warning" if alerts else "ok"),
            "audit_chains": "ok" if audit_chains else "empty",
            "event_integrity": event_integrity["status_code"],
            "database": database["status_code"],
            "operations": "critical" if critical_operational_warnings else ("warning" if operational_warnings else "ok"),
            "github_webhook_contract": github_webhook_contract["status_code"],
            "internal_production_preflight": internal_production_preflight["status_code"],
        }
        ok = (
            not drift
            and not critical_alerts
            and github_projection["status_code"] != "drift"
            and event_integrity["status_code"] == "ok"
            and database["status_code"] == "ok"
            and not critical_operational_warnings
        )
        summary = self._doctor_summary(
            drift_count=len(drift),
            open_alert_count=len(alerts),
            critical_alert_count=len(critical_alerts),
            github_projection=github_projection,
            event_integrity=event_integrity,
            database=database,
            operational_warnings=operational_warnings,
        )
        return {
            "ok": ok,
            "status_code": "ok" if ok else ("critical" if critical_alerts else "drift"),
            "status_codes": status_codes,
            "summary": summary,
            "generated_artifact_count": len(checks),
            "drift_count": len(drift),
            "drift": drift,
            "checks": check_dicts,
            "open_alert_count": len(alerts),
            "critical_alert_count": len(critical_alerts),
            "alerts": alerts,
            "github_projection": github_projection,
            "audit_chains": audit_chains,
            "event_integrity": event_integrity,
            "database": database,
            "operational_warnings": operational_warnings,
            "operational_readiness": operational_readiness,
            "github_webhook_contract": github_webhook_contract,
            "internal_production_preflight": internal_production_preflight,
        }

    def _doctor_check_payload(self, check: dict[str, Any]) -> dict[str, Any]:
        if check.get("status") == "ok":
            return {**check, "status_code": "ok", "action": "none"}
        path = check.get("path", "generated artifact")
        return {
            **check,
            "status_code": "generated_artifact_drift",
            "action": f"Re-run `nexusctl generate all` and review {path} before committing.",
        }

    def _doctor_open_alerts(self) -> list[dict[str, Any]]:
        if self.connection is None:
            return []
        try:
            rows = self.connection.execute(
                """
                SELECT id, severity, kind, summary, patch_id, feature_request_id, repository_id, pull_number, created_at
                FROM github_alerts
                WHERE status = 'open'
                ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, created_at DESC, id
                """
            ).fetchall()
        except sqlite3.Error:
            return []
        return [
            {
                "id": row["id"],
                "severity": row["severity"],
                "kind": row["kind"],
                "summary": row["summary"],
                "patch_id": row["patch_id"],
                "feature_request_id": row["feature_request_id"],
                "repository_id": row["repository_id"],
                "pull_number": row["pull_number"],
                "created_at": row["created_at"],
                "blocks_merge": row["severity"] == "critical",
                "action": "Resolve or explicitly close this alert before merging." if row["severity"] == "critical" else "Review the projection drift and reconcile if needed.",
            }
            for row in rows
        ]

    def _doctor_github_projection(self) -> dict[str, Any]:
        empty = {
            "status_code": "ok",
            "pull_request_count": 0,
            "required_check_count": 0,
            "green_required_check_count": 0,
            "drift": [],
        }
        if self.connection is None:
            return empty
        try:
            pull_request_count = int(self.connection.execute("SELECT COUNT(*) AS count FROM github_pull_links").fetchone()["count"])
            policy_rows = self.connection.execute(
                """
                SELECT pc.patch_id, pc.name, pc.status AS policy_status, pc.conclusion AS policy_conclusion, pc.head_sha AS policy_head_sha,
                       gcr.status AS github_status, gcr.conclusion AS github_conclusion, gcr.head_sha AS github_head_sha, gcr.pull_number
                FROM policy_checks pc
                LEFT JOIN github_check_runs gcr
                  ON gcr.patch_id = pc.patch_id AND gcr.name = 'nexus/policy/' || pc.name
                WHERE pc.required = 1
                ORDER BY pc.patch_id, pc.name
                """
            ).fetchall()
        except sqlite3.Error:
            return empty

        drift: list[dict[str, Any]] = []
        green = 0
        for row in policy_rows:
            github_ok = row["github_status"] == "completed" and row["github_conclusion"] == "success"
            policy_ok = row["policy_status"] == "passed" and row["policy_conclusion"] == "success"
            same_head = bool(row["github_head_sha"]) and row["github_head_sha"] == row["policy_head_sha"]
            if github_ok and policy_ok and same_head:
                green += 1
                continue
            reasons = []
            if row["github_status"] is None:
                reasons.append("missing GitHub check projection")
            if row["github_status"] is not None and not github_ok:
                reasons.append("GitHub check projection is not green")
            if not policy_ok:
                reasons.append("Nexus policy check is not passing")
            if row["github_status"] is not None and not same_head:
                reasons.append("GitHub check head SHA differs from Nexus policy head SHA")
            drift.append(
                {
                    "patch_id": row["patch_id"],
                    "pull_number": row["pull_number"],
                    "check": row["name"],
                    "status_code": "github_projection_drift",
                    "reasons": reasons,
                    "action": "Run policy check sync/reconciliation and keep GitHub as a projection of Nexus state.",
                }
            )
        return {
            "status_code": "drift" if drift else "ok",
            "pull_request_count": pull_request_count,
            "required_check_count": len(policy_rows),
            "green_required_check_count": green,
            "drift": drift,
        }

    def _doctor_audit_chains(self) -> list[dict[str, Any]]:
        if self.connection is None:
            return []
        try:
            rows = self.connection.execute(
                """
                SELECT fr.id AS feature_request_id, fr.goal_id, fr.status AS feature_request_status,
                       wi.id AS work_item_id, wi.status AS work_status,
                       pp.id AS patch_id, pp.status AS patch_status,
                       gpl.pull_number,
                       mr.id AS merge_id, mr.status AS merge_status
                FROM feature_requests fr
                LEFT JOIN work_items wi ON wi.feature_request_id = fr.id
                LEFT JOIN patch_proposals pp ON pp.work_item_id = wi.id
                LEFT JOIN github_pull_links gpl ON gpl.patch_id = pp.id
                LEFT JOIN merge_records mr ON mr.patch_id = pp.id
                ORDER BY fr.created_at DESC, wi.created_at DESC, pp.created_at DESC
                LIMIT 25
                """
            ).fetchall()
        except sqlite3.Error:
            return []
        chains: list[dict[str, Any]] = []
        for row in rows:
            steps = [
                {"step": "goal", "id": row["goal_id"], "present": row["goal_id"] is not None},
                {"step": "feature_request", "id": row["feature_request_id"], "status": row["feature_request_status"], "present": True},
                {"step": "work", "id": row["work_item_id"], "status": row["work_status"], "present": row["work_item_id"] is not None},
                {"step": "patch", "id": row["patch_id"], "status": row["patch_status"], "present": row["patch_id"] is not None},
                {"step": "github_pr", "id": row["pull_number"], "present": row["pull_number"] is not None},
                {"step": "merge", "id": row["merge_id"], "status": row["merge_status"], "present": row["merge_id"] is not None},
            ]
            chains.append(
                {
                    "feature_request_id": row["feature_request_id"],
                    "patch_id": row["patch_id"],
                    "status_code": "complete" if all(step["present"] for step in steps[:-1]) else "in_progress",
                    "steps": steps,
                }
            )
        return chains

    def _doctor_event_integrity(self) -> dict[str, Any]:
        if self.connection is None:
            return {
                "status_code": "not_checked",
                "valid": None,
                "checked_events": 0,
                "first_error": "no database connection supplied",
                "last_event_hash": None,
                "action": "Run doctor with a local database connection.",
            }
        try:
            report = EventStore(self.connection).verify_integrity()
        except sqlite3.Error as exc:
            return {
                "status_code": "invalid",
                "valid": False,
                "checked_events": 0,
                "first_error": str(exc),
                "last_event_hash": None,
                "action": "Inspect the events table, apply migrations, or restore from a known-good backup.",
            }
        return {
            "status_code": "ok" if report.valid else "invalid",
            "valid": report.valid,
            "checked_events": report.checked_events,
            "first_error": report.first_error,
            "last_event_hash": report.last_event_hash,
            "action": "none" if report.valid else "Restore from a known-good backup or investigate the first mismatching event before trusting audit history.",
        }

    def _doctor_database_status(self) -> dict[str, Any]:
        if self.connection is None:
            return {"status_code": "not_checked", "schema_version": None, "latest_schema_version": self._latest_schema_version(), "missing_tables": [], "pending_migrations": []}
        try:
            applied = applied_versions(self.connection)
            missing_tables = [table for table in MVP_TABLES if not table_exists(self.connection, table)]
        except sqlite3.Error as exc:
            return {
                "status_code": "invalid",
                "schema_version": None,
                "latest_schema_version": self._latest_schema_version(),
                "missing_tables": [],
                "pending_migrations": [],
                "error": str(exc),
                "action": "Run `nexusctl db init` or restore a valid Nexus database.",
            }
        latest = self._latest_schema_version()
        pending = [migration.version for migration in MIGRATIONS if migration.version not in applied]
        status_code = "ok" if not missing_tables and not pending and (max(applied) if applied else 0) >= latest else "migration_pending"
        return {
            "status_code": status_code,
            "schema_version": max(applied) if applied else 0,
            "latest_schema_version": latest,
            "applied_migrations": sorted(applied),
            "pending_migrations": pending,
            "missing_tables": missing_tables,
            "action": "none" if status_code == "ok" else "Run `nexusctl db init` or the current command against this database to apply migrations.",
        }

    def _latest_schema_version(self) -> int:
        return max(migration.version for migration in MIGRATIONS)

    def _doctor_github_webhook_contract(self) -> dict[str, Any]:
        """Return the machine-readable GitHub webhook/reconciliation contract.

        This check is intentionally local and secret-free. It confirms that the
        repository still contains the representative payload fixtures backing the
        supported production path and exposes the negative webhook and authority
        contract that operators need before enabling GitHub webhooks.
        """

        fixtures_dir = self.project_root / "tests" / "fixtures" / "github"
        fixture_files: list[dict[str, Any]] = []
        missing: list[str] = []
        secret_marker_hits: list[dict[str, str]] = []
        for event_name, filename in GITHUB_WEBHOOK_FIXTURE_CONTRACT.items():
            path = fixtures_dir / filename
            if not path.exists():
                missing.append(filename)
                fixture_files.append({"event_name": event_name, "path": str(path.relative_to(self.project_root)), "present": False})
                continue
            text = path.read_text(encoding="utf-8")
            for marker in SECRET_FIXTURE_MARKERS:
                if marker in text:
                    secret_marker_hits.append({"path": str(path.relative_to(self.project_root)), "marker": marker})
            fixture_files.append({"event_name": event_name, "path": str(path.relative_to(self.project_root)), "present": True})

        ok = not missing and not secret_marker_hits
        status_code = "ok" if ok else ("fixture_secret_risk" if secret_marker_hits else "fixture_missing")
        return {
            "status_code": status_code,
            "supported_events": list(SUPPORTED_WEBHOOK_EVENTS),
            "fixture_backed_events": sorted(GITHUB_WEBHOOK_FIXTURE_CONTRACT),
            "fixtures": fixture_files,
            "missing_fixtures": missing,
            "secret_marker_hits": secret_marker_hits,
            "processing_statuses": list(GITHUB_WEBHOOK_PROCESSING_STATUSES),
            "negative_webhook_contracts": [
                "missing_delivery_rejected_before_persist",
                "missing_event_rejected_before_persist",
                "invalid_signature_rejected_before_payload_parse",
                "invalid_json_rejected_without_secret_rendering",
                "unsupported_event_signature_verified_then_ignored",
                "duplicate_delivery_idempotent_for_same_payload",
                "conflicting_duplicate_delivery_rejected",
            ],
            "authority": {
                "nexusctl_lifecycle_authority": True,
                "github_lifecycle_authority": False,
                "github_role": "projection_and_collaboration_surface",
            },
            "live_sandbox_verification": {
                "required_before_internal_production_cutover": True,
                "fixture_green_is_not_live_green": True,
                "runbook": "docs/operations/internal-production.md#github-live-sandbox-verifikation",
                "evidence_fields": list(GITHUB_LIVE_SANDBOX_EVIDENCE_FIELDS),
                "secret_free": True,
            },
            "action": "none" if ok else "Restore the missing/unsafe GitHub fixtures and keep payload examples secret-free before enabling internal-production webhook reconciliation.",
        }

    def _doctor_operational_readiness(self, *, event_integrity: dict[str, Any], github_webhook_contract: dict[str, Any]) -> list[dict[str, Any]]:
        """Return explicit operator-facing readiness checks for internal deployments.

        The checks deliberately report both green and non-green conditions so a
        local development profile can remain usable while internal-production
        mode makes unsafe or incomplete settings visible in the doctor contract.
        Secret values are never included in the payload.
        """

        deployment_mode = os.environ.get("NEXUSCTL_DEPLOYMENT_MODE", "development").strip().lower() or "development"
        production_mode = deployment_mode in {"production", "prod", "internal-production", "internal_production"}
        readiness: list[dict[str, Any]] = []

        def add(
            check_id: str,
            *,
            severity: str,
            status_code: str,
            summary: str,
            action: str,
            required_for_internal_production: bool = True,
        ) -> None:
            readiness.append(
                {
                    "id": check_id,
                    "severity": severity,
                    "status_code": status_code,
                    "summary": summary,
                    "action": action,
                    "required_for_internal_production": required_for_internal_production,
                    "deployment_mode": deployment_mode,
                }
            )

        host = os.environ.get("NEXUSCTL_API_HOST", "127.0.0.1")
        tls_enabled = _env_truthy("NEXUSCTL_API_TLS_ENABLED")
        allow_insecure_bind = _env_truthy("NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND")
        remote_binding = host not in {"127.0.0.1", "localhost", "::1"}
        if remote_binding and not tls_enabled and allow_insecure_bind:
            add(
                "api_insecure_remote_binding_opt_in",
                severity="critical" if production_mode else "warning",
                status_code="insecure_remote_binding",
                summary="API is bound remotely without TLS via explicit insecure opt-in.",
                action="Use TLS behind a reverse proxy for internal production; keep the insecure opt-in for local development only.",
            )
        elif remote_binding and not tls_enabled:
            add(
                "api_remote_binding_without_tls",
                severity="critical",
                status_code="remote_binding_without_tls",
                summary="API is configured for remote binding without TLS and without explicit insecure opt-in.",
                action="Bind to loopback, enable TLS behind a reverse proxy, or set the explicit development-only opt-in.",
            )
        else:
            add(
                "api_binding",
                severity="ok",
                status_code="ok",
                summary="API binding is loopback-only or protected by an asserted TLS boundary.",
                action="none",
            )

        webhook_reconciliation_active = os.environ.get("NEXUSCTL_GITHUB_MODE", "").strip().lower() in {"github", "real", "app"} or _env_truthy(
            "NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED"
        )
        webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
        placeholder_secret = webhook_secret is not None and webhook_secret.strip() in {"", "change-me", "changeme", "placeholder"}
        if webhook_reconciliation_active and (webhook_secret is None or placeholder_secret):
            add(
                "github_webhook_secret_required",
                severity="critical",
                status_code="webhook_secret_missing",
                summary="GitHub webhook reconciliation is active but no real webhook secret is configured.",
                action="Set GITHUB_WEBHOOK_SECRET from secret management before enabling webhook reconciliation.",
            )
        elif placeholder_secret:
            add(
                "github_webhook_secret_placeholder",
                severity="warning",
                status_code="placeholder_secret",
                summary="GitHub webhook secret is unset or still the placeholder value.",
                action="Set a real webhook secret before enabling GitHub webhook reconciliation.",
                required_for_internal_production=False,
            )
        else:
            add(
                "github_webhook_secret",
                severity="ok",
                status_code="ok",
                summary="Webhook secret is absent in inactive mode or configured without exposing its value.",
                action="none",
                required_for_internal_production=webhook_reconciliation_active,
            )


        contract_status = github_webhook_contract.get("status_code")
        if contract_status == "ok":
            add(
                "github_webhook_contract",
                severity="ok",
                status_code="ok",
                summary="GitHub webhook fixtures, supported event classes, idempotency, authority boundary and live-sandbox evidence contract are present.",
                action="Run the secret-free GitHub live-sandbox verification before internal-production cutover; fixture-green alone is not live-green.",
                required_for_internal_production=webhook_reconciliation_active or production_mode,
            )
        else:
            add(
                "github_webhook_contract",
                severity="critical" if production_mode else "warning",
                status_code="github_webhook_contract_incomplete",
                summary="GitHub webhook reconciliation contract is incomplete or unsafe.",
                action=str(github_webhook_contract.get("action") or "Restore fixture-backed webhook contract coverage."),
                required_for_internal_production=webhook_reconciliation_active or production_mode,
            )

        path_checks = {
            "sqlite_data_path": os.environ.get("NEXUSCTL_DB"),
            "backup_path": os.environ.get("NEXUSCTL_BACKUP_DIR"),
            "workspaces_path": os.environ.get("NEXUSCTL_WORKSPACES_DIR"),
            "repo_worktrees_path": os.environ.get("NEXUSCTL_REPO_WORKTREES_DIR"),
        }
        for check_id, raw_path in path_checks.items():
            if not raw_path:
                if production_mode:
                    add(
                        check_id,
                        severity="critical",
                        status_code="persistent_path_missing",
                        summary=f"{check_id} is not configured for persistent internal production storage.",
                        action="Set the corresponding NEXUSCTL_* path to a persistent mounted directory.",
                    )
                continue
            path = Path(raw_path)
            directory = path if check_id != "sqlite_data_path" else path.parent
            if directory.exists():
                add(
                    check_id,
                    severity="ok",
                    status_code="ok",
                    summary=f"{check_id} points to an existing persistent path boundary.",
                    action="none",
                )
            else:
                add(
                    check_id,
                    severity="critical" if production_mode else "warning",
                    status_code="persistent_path_unavailable",
                    summary=f"{check_id} points to a path whose directory is not present.",
                    action="Create or mount the directory before starting internal production services.",
                )

        evidence_dir = os.environ.get("NEXUSCTL_RECOVERY_EVIDENCE_DIR")
        if not evidence_dir:
            if production_mode:
                add(
                    "recovery_evidence_path",
                    severity="critical",
                    status_code="recovery_evidence_path_missing",
                    summary="Recovery-evidence manifest storage is not configured for internal production.",
                    action="Set NEXUSCTL_RECOVERY_EVIDENCE_DIR to a persistent directory for restore-drill evidence manifests.",
                )
        else:
            evidence_path = Path(evidence_dir)
            if evidence_path.exists() and evidence_path.is_dir():
                add(
                    "recovery_evidence_path",
                    severity="ok",
                    status_code="ok",
                    summary="Recovery-evidence manifests have a configured persistent directory boundary.",
                    action="none",
                )
            else:
                add(
                    "recovery_evidence_path",
                    severity="critical" if production_mode else "warning",
                    status_code="recovery_evidence_path_unavailable",
                    summary="Recovery-evidence manifest directory is configured but not available.",
                    action="Create or mount NEXUSCTL_RECOVERY_EVIDENCE_DIR before relying on evidence archiving.",
                )

        retention_days = _env_int("NEXUSCTL_BACKUP_RETENTION_DAYS")
        retention_min_copies = _env_int("NEXUSCTL_BACKUP_RETENTION_MIN_COPIES")
        retention_configured = retention_days is not None and retention_days > 0 and retention_min_copies is not None and retention_min_copies > 0
        if retention_configured:
            add(
                "backup_retention_policy",
                severity="ok",
                status_code="ok",
                summary="Backup retention policy is configured with positive day and copy thresholds.",
                action="none",
            )
        elif production_mode:
            add(
                "backup_retention_policy",
                severity="critical",
                status_code="backup_retention_policy_missing",
                summary="Backup retention policy is missing or incomplete for internal production.",
                action="Set NEXUSCTL_BACKUP_RETENTION_DAYS and NEXUSCTL_BACKUP_RETENTION_MIN_COPIES to positive integers.",
            )
        elif retention_days is not None or retention_min_copies is not None:
            add(
                "backup_retention_policy",
                severity="warning",
                status_code="backup_retention_policy_incomplete",
                summary="Backup retention policy is partially configured.",
                action="Set both NEXUSCTL_BACKUP_RETENTION_DAYS and NEXUSCTL_BACKUP_RETENTION_MIN_COPIES to positive integers.",
                required_for_internal_production=False,
            )

        offsite_enabled = _env_truthy("NEXUSCTL_OFFSITE_BACKUP_ENABLED")
        offsite_target = os.environ.get("NEXUSCTL_OFFSITE_BACKUP_TARGET", "").strip()
        offsite_schedule = os.environ.get("NEXUSCTL_OFFSITE_BACKUP_SCHEDULE", "").strip()
        if offsite_enabled and offsite_target and offsite_schedule:
            add(
                "offsite_backup_control",
                severity="ok",
                status_code="ok",
                summary="Offsite backup control is asserted with target and schedule metadata.",
                action="none",
            )
        elif production_mode:
            add(
                "offsite_backup_control",
                severity="critical",
                status_code="offsite_backup_control_missing",
                summary="Offsite backup control is not fully asserted for internal production.",
                action="Set NEXUSCTL_OFFSITE_BACKUP_ENABLED=1 plus NEXUSCTL_OFFSITE_BACKUP_TARGET and NEXUSCTL_OFFSITE_BACKUP_SCHEDULE metadata.",
            )
        elif offsite_enabled or offsite_target or offsite_schedule:
            add(
                "offsite_backup_control",
                severity="warning",
                status_code="offsite_backup_control_incomplete",
                summary="Offsite backup control metadata is partially configured.",
                action="Set enabled flag, target and schedule together before relying on offsite backup evidence.",
                required_for_internal_production=False,
            )

        runbook_candidates = [
            self.project_root / "README.md",
            self.project_root / "docs" / "operations" / "internal-production.md",
        ]
        runbook_text = "\n".join(path.read_text(encoding="utf-8") for path in runbook_candidates if path.exists())
        docs_ready = all(fragment in runbook_text for fragment in ["db backup", "restore-check", "nexusctl doctor"])
        add(
            "backup_restore_runbook",
            severity="ok" if docs_ready else ("critical" if production_mode else "warning"),
            status_code="ok" if docs_ready else "runbook_missing",
            summary="Backup, restore-check, restore and post-restore doctor flow are documented." if docs_ready else "Backup/restore runbook is incomplete.",
            action="none" if docs_ready else "Document db backup, restore-check, restore and post-restore doctor commands.",
        )

        operations_docs_candidates = [
            self.project_root / "docs" / "operations" / "internal-production.md",
            self.project_root / "docs" / "operations" / "deployment-strategy.md",
        ]
        operations_docs_text = "\n".join(path.read_text(encoding="utf-8") for path in operations_docs_candidates if path.exists())
        monitoring_runbook_ready = all(fragment in operations_docs_text for fragment in OPERATIONAL_MONITORING_RUNBOOK_FRAGMENTS)
        add(
            "monitoring_alert_runbook",
            severity="ok" if monitoring_runbook_ready else ("critical" if production_mode else "warning"),
            status_code="ok" if monitoring_runbook_ready else "monitoring_runbook_missing",
            summary=(
                "Monitoring and alert-response runbook covers doctor readiness, GitHub reconciliation alerts and restore-drill evidence incidents."
                if monitoring_runbook_ready
                else "Monitoring and alert-response runbook is incomplete for doctor, GitHub reconciliation or restore-drill evidence incidents."
            ),
            action="none" if monitoring_runbook_ready else "Document concrete monitoring signals, alert triggers, owner actions and closure criteria.",
        )

        operator_controls_ready = all(fragment in operations_docs_text for fragment in OPERATOR_MANAGED_CONTROL_FRAGMENTS)
        add(
            "operator_managed_controls",
            severity="ok" if operator_controls_ready else ("critical" if production_mode else "warning"),
            status_code="ok" if operator_controls_ready else "operator_controls_boundary_missing",
            summary=(
                "Operator-managed controls are explicitly separated from product-local evidence."
                if operator_controls_ready
                else "Operator-managed controls are not explicitly separated from product-local evidence."
            ),
            action="none" if operator_controls_ready else "Document that TLS, reverse proxy, secret management, offsite replication, WORM, external audit signatures and monitoring remain operator-managed controls.",
        )

        event_status = event_integrity.get("status_code")
        add(
            "audit_integrity_check",
            severity="ok" if event_status == "ok" else ("critical" if production_mode else "warning"),
            status_code="ok" if event_status == "ok" else "audit_integrity_not_green",
            summary="Audit event integrity check is executable and green." if event_status == "ok" else "Audit event integrity check is not green.",
            action="none" if event_status == "ok" else "Run doctor with a migrated local database and investigate event-chain errors before production use.",
        )
        return readiness

    def _doctor_internal_production_preflight(
        self,
        *,
        operational_readiness: list[dict[str, Any]],
        event_integrity: dict[str, Any],
        database: dict[str, Any],
    ) -> dict[str, Any]:
        deployment_mode = os.environ.get("NEXUSCTL_DEPLOYMENT_MODE", "development").strip().lower() or "development"
        production_mode = deployment_mode in {"production", "prod", "internal-production", "internal_production"}
        blockers = [
            {
                "id": item["id"],
                "status_code": item["status_code"],
                "severity": item["severity"],
                "action": item["action"],
            }
            for item in operational_readiness
            if item.get("required_for_internal_production") and item.get("severity") == "critical"
        ]
        if database.get("status_code") != "ok":
            blockers.append(
                {
                    "id": "database",
                    "status_code": str(database.get("status_code") or "unknown"),
                    "severity": "critical",
                    "action": str(database.get("action") or "Run `nexusctl db init` or restore a valid Nexus database."),
                }
            )
        if event_integrity.get("status_code") not in {"ok"} and not any(item["id"] == "audit_integrity_check" for item in blockers):
            blockers.append(
                {
                    "id": "event_integrity",
                    "status_code": str(event_integrity.get("status_code") or "unknown"),
                    "severity": "critical",
                    "action": str(event_integrity.get("action") or "Run doctor with a migrated local database and investigate audit integrity."),
                }
            )
        status_code = "blocked" if blockers else ("ok" if production_mode else "not_applicable")
        return {
            "status_code": status_code,
            "deployment_mode": deployment_mode,
            "required_before_internal_production_cutover": True,
            "command_sequence": list(INTERNAL_PRODUCTION_PREFLIGHT_COMMAND_SEQUENCE),
            "commands": {
                "load_internal_production_env": "Load the reviewed internal-production environment from the deployment bundle or operator secret manager.",
                "nexusctl_db_init_or_migrate": 'nexusctl db init --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json',
                "nexusctl_doctor_json": 'nexusctl doctor --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json',
                "nexusctl_db_restore_drill_json_with_evidence_path": 'nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --evidence-path "$NEXUSCTL_RECOVERY_EVIDENCE_DIR/restore-drill-evidence.json" --json',
                "operator_cutover_decision": "Approve cutover only when doctor, restore-drill evidence, retention, offsite and operator controls are green or formally accepted.",
            },
            "expected_json_fields": list(INTERNAL_PRODUCTION_PREFLIGHT_JSON_FIELDS),
            "required_readiness_ids": [
                item["id"]
                for item in operational_readiness
                if item.get("required_for_internal_production")
            ],
            "cutover_blockers": blockers,
            "recovery_evidence": {
                "manifest_required": True,
                "evidence_path_env": "NEXUSCTL_RECOVERY_EVIDENCE_DIR",
                "command": 'nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --evidence-path "$NEXUSCTL_RECOVERY_EVIDENCE_DIR/restore-drill-evidence.json" --json',
                "green_when": "ok=true, doctor_status=ok, failed_checks=[], event_chain_status.status_code=ok and manifest archived by the operator.",
            },
            "external_operator_evidence_required": list(INTERNAL_PRODUCTION_PREFLIGHT_EXTERNAL_EVIDENCE),
            "cutover_decision": "blocked" if blockers else "operator_review_required",
            "action": (
                "Resolve cutover_blockers before internal-production cutover."
                if blockers
                else "Archive the secret-free restore-drill evidence and operator-control evidence before cutover."
            ),
        }

    def _doctor_summary(
        self,
        *,
        drift_count: int,
        open_alert_count: int,
        critical_alert_count: int,
        github_projection: dict[str, Any],
        event_integrity: dict[str, Any],
        database: dict[str, Any],
        operational_warnings: list[dict[str, Any]],
    ) -> str:
        findings: list[str] = []
        if drift_count:
            findings.append(f"{drift_count} generated artifact(s) drifted")
        if github_projection.get("drift"):
            findings.append(f"{len(github_projection['drift'])} GitHub projection drift item(s)")
        if event_integrity.get("status_code") == "invalid":
            findings.append(f"event integrity invalid: {event_integrity.get('first_error')}")
        if database.get("status_code") != "ok":
            findings.append(f"database status {database.get('status_code')}")
        if critical_alert_count:
            findings.append(f"{critical_alert_count} critical open alert(s) block merge gates")
        elif open_alert_count:
            findings.append(f"{open_alert_count} non-critical open alert(s)")
        critical_ops = [warning for warning in operational_warnings if warning.get("severity") == "critical"]
        if critical_ops:
            findings.append(f"{len(critical_ops)} critical operational warning(s)")
        if not findings:
            return "doctor ok: generated artifacts, GitHub projections, audit integrity, database migrations and open alerts are healthy"
        return "doctor found " + "; ".join(findings)

    def _require_generate(self, subject: Subject) -> None:
        if self.policy is None:
            raise ValidationError("GenerationService requires a PolicyEngine for mutating generation")
        self.policy.require(subject, "runtime.generate", resource_domain=subject.domain)

    def _append_event(self, subject: Subject, event_type: str, results: list[WriteResult]) -> str | None:
        if self.connection is None:
            return None
        event = EventStore(self.connection).append(
            aggregate_type="runtime",
            aggregate_id="openclaw",
            event_type=event_type,
            actor_id=subject.agent_id,
            payload={
                "artifact_count": len(results),
                "changed_count": sum(1 for result in results if result.changed),
                "paths": [result.path for result in results],
            },
            metadata={"source": "nexus/*.yml"},
        )
        return event.event_id

    def _payload(self, kind: str, results: list[WriteResult], *, event_id: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": True,
            "kind": kind,
            "artifact_count": len(results),
            "changed_count": sum(1 for result in results if result.changed),
            "artifacts": [asdict(result) for result in results],
        }
        if event_id is not None:
            payload["event_id"] = event_id
        return payload

    def _load_design(self) -> dict[str, Any]:
        agents_yml = self._load_yaml("nexus/agents.yml")
        capabilities_yml = self._load_yaml("nexus/capabilities.yml")
        schedules_yml = self._load_yaml("nexus/schedules.yml")
        standing_orders_yml = self._load_yaml("nexus/standing-orders.yml")
        agents = agents_yml.get("agents") or []
        skills = capabilities_yml.get("skills") or []
        capabilities = capabilities_yml.get("capabilities") or []
        schedules = schedules_yml.get("schedules") or []
        if not isinstance(agents, list) or not isinstance(skills, list) or not isinstance(capabilities, list):
            raise ValidationError("nexus agent/capability definitions must use lists")
        if not isinstance(schedules, list):
            raise ValidationError("nexus/schedules.yml schedules must be a list")
        return {
            "agents": agents,
            "skills": skills,
            "capabilities_by_id": {str(item.get("id")): item for item in capabilities if isinstance(item, dict)},
            "schedules": schedules,
            "schedule_guardrails": schedules_yml.get("guardrails") or {},
            "standing_orders": standing_orders_yml,
            "skill_descriptions": {
                str(item.get("id")): str(item.get("description", "")) for item in skills if isinstance(item, dict)
            },
        }

    def _load_yaml(self, rel_path: str) -> dict[str, Any]:
        path = self.project_root / rel_path
        if not path.is_file():
            raise ValidationError(f"missing design file: {rel_path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValidationError(f"{rel_path} must contain a mapping")
        return data
