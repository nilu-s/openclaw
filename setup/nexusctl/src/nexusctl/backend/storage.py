from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nexusctl.errors import NexusError
from nexusctl.backend.integrations.github import (
    GitHubClient,
    assert_repo_matches,
    derive_checks_state,
    derive_review_state,
    evaluate_changed_files_policy,
    parse_github_pr_url,
)
from nexusctl.backend.integrations.github_models import GitHubRepository
from nexusctl.backend.integrations.github_templates import render_issue_body


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


_PBKDF2_ITERATIONS = 200_000
_RANDOM_ID_HEX_CHARS = 16
_REQUEST_RISK_CLASSES = {"low", "medium", "high", "critical"}
_REQUEST_PRIORITIES = {"P0", "P1", "P2", "P3"}
_SYSTEM_STATUSES = {"planned", "active", "paused", "retired"}
_SYSTEM_RISK_LEVELS = {"low", "medium", "high", "critical"}
_GOAL_STATUSES = {"proposed", "active", "blocked", "achieved", "deprecated"}
_RUNTIME_TOOL_STATUSES = {"planned", "in_progress", "available", "blocked", "deprecated"}
_RUNTIME_TOOL_KINDS = {"service", "cli", "script", "api", "job"}
_RUNTIME_TOOL_MODES = {"dev", "test", "paper", "live", "any"}
_RUNTIME_TOOL_SIDE_EFFECTS = {"read_only", "simulation", "paper_trade", "live_trade", "destructive"}
_REVIEW_VERDICTS = {"approved", "changes-requested", "rejected"}
_REQUEST_STATUSES = {
    "draft",
    "submitted",
    "gate-rejected",
    "accepted",
    "needs-planning",
    "ready-to-build",
    "in-build",
    "in-review",
    "approved",
    "review-failed",
    "state-update-needed",
    "done",
    "adoption-pending",
    "closed",
    "cancelled",
}
_OPEN_REQUEST_STATUSES = _REQUEST_STATUSES - {"closed", "cancelled"}
_REQUEST_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"accepted", "gate-rejected"},
    "gate-rejected": {"draft", "cancelled"},
    "accepted": {"needs-planning"},
    "needs-planning": {"ready-to-build", "cancelled"},
    "ready-to-build": {"in-build"},
    "in-build": {"in-review", "cancelled"},
    "in-review": {"approved", "review-failed", "state-update-needed"},
    "approved": {"done", "state-update-needed"},
    "review-failed": {"in-build"},
    "state-update-needed": {"in-review"},
    "done": {"adoption-pending", "closed"},
    "adoption-pending": {"closed", "needs-planning"},
    "closed": set(),
    "cancelled": set(),
}

# Server-side source of truth for default role scopes. Explicit DB grants are stored in
# agent_scope_grants; this table is seeded from these defaults and can be changed by nexus.
_ROLE_SCOPE_DEFAULTS: dict[str, list[tuple[str, str]]] = {
    "main": [
        ("*", "context.read"), ("*", "systems.read"), ("*", "goals.read"),
        ("*", "capabilities.read"), ("*", "request.read"), ("*", "runtime_tools.read"),
        ("*", "work.read"), ("*", "repos.read"), ("*", "github.status.read"),
    ],
    "nexus": [
        ("*", "context.read"), ("*", "systems.read"), ("*", "systems.manage"),
        ("*", "goals.read"), ("*", "goals.create"), ("*", "goals.update-status"),
        ("*", "capabilities.read"), ("*", "request.read"), ("*", "request.transition"),
        ("*", "scopes.read"), ("*", "runtime_tools.read"),
        ("*", "runtime_tools.manage"), ("*", "work.read"), ("*", "work.plan"),
        ("*", "work.assign"), ("*", "work.implementation-context.set"), ("*", "work.plan.approve"),
        ("*", "work.transition"), ("*", "reviews.read"), ("*", "reviews.submit"),
        ("*", "repos.read"), ("*", "repos.manage"), ("*", "github.repos.read"),
        ("*", "github.issue.sync"), ("*", "github.pr.sync"), ("*", "github.status.read"),
        ("*", "github.evidence.create"), ("*", "github.webhook.receive"),
    ],
    "trading-strategist": [
        ("trading-system", "context.read"), ("trading-system", "systems.read"),
        ("trading-system", "goals.read"), ("trading-system", "capabilities.read"),
        ("trading-system", "request.read"), ("trading-system", "request.create"),
        ("trading-system", "request.submit-draft"), ("trading-system", "runtime_tools.read"),
        ("trading-system", "trade.intent.create.paper"),
    ],
    "trading-analyst": [
        ("trading-system", "context.read"), ("trading-system", "systems.read"),
        ("trading-system", "goals.read"), ("trading-system", "capabilities.read"),
        ("trading-system", "request.read"), ("trading-system", "evidence.create"),
        ("trading-system", "runtime_tools.read"), ("trading-system", "marketdata.read"),
    ],
    "trading-sentinel": [
        ("trading-system", "context.read"), ("trading-system", "systems.read"),
        ("trading-system", "goals.read"), ("trading-system", "capabilities.read"),
        ("trading-system", "request.read"), ("trading-system", "request.draft.create"),
        ("trading-system", "alert.create"), ("trading-system", "runtime_tools.read"),
        ("trading-system", "monitoring.read"),
    ],
    "sw-architect": [
        ("software-domain", "context.read"), ("software-domain", "systems.read"),
        ("software-domain", "capabilities.read"), ("software-domain", "request.read"),
        ("software-domain", "runtime_tools.read"), ("software-domain", "work.read"),
        ("software-domain", "work.plan"), ("software-domain", "work.assign"),
        ("software-domain", "work.implementation-context.set"), ("software-domain", "repos.read"),
        ("software-domain", "github.issue.create"), ("software-domain", "github.issue.sync"),
        ("software-domain", "github.status.read"), ("software-domain", "github.evidence.create"),
    ],
    "sw-builder": [
        ("software-domain", "context.read"), ("software-domain", "systems.read"),
        ("software-domain", "request.read"), ("software-domain", "work.read.assigned"),
        ("software-domain", "work.transition.build"), ("software-domain", "work.evidence.create"),
        ("software-domain", "repos.read.assigned"), ("software-domain", "github.status.read.assigned"),
        ("software-domain", "github.pr.link.assigned"), ("software-domain", "github.pr.sync.assigned"),
        ("software-domain", "github.evidence.create"),
    ],
    "sw-reviewer": [
        ("software-domain", "context.read"), ("software-domain", "systems.read"),
        ("software-domain", "request.read"), ("software-domain", "work.read.assigned"),
        ("software-domain", "reviews.read"), ("software-domain", "reviews.submit"),
        ("software-domain", "work.transition.review"), ("software-domain", "repos.read.assigned"),
        ("software-domain", "github.status.read.assigned"), ("software-domain", "github.pr.sync.assigned"),
    ],
    "sw-techlead": [
        ("software-domain", "context.read"), ("software-domain", "systems.read"),
        ("software-domain", "goals.read"), ("software-domain", "capabilities.read"),
        ("*", "capabilities.set-status"), ("software-domain", "request.read"),
        ("software-domain", "runtime_tools.read"), ("software-domain", "requirement.verify"),
        ("software-domain", "work.read"), ("software-domain", "work.plan"),
        ("software-domain", "work.assign"), ("software-domain", "work.transition"),
        ("software-domain", "work.implementation-context.set"), ("software-domain", "work.plan.approve"),
        ("software-domain", "reviews.read"), ("software-domain", "reviews.submit"),
        ("software-domain", "repos.read"), ("software-domain", "repos.manage"),
        ("software-domain", "github.issue.create"), ("software-domain", "github.issue.sync"),
        ("software-domain", "github.pr.link"), ("software-domain", "github.pr.sync"),
        ("software-domain", "github.repos.sync"), ("software-domain", "github.repos.read"),
        ("software-domain", "github.status.read"), ("software-domain", "github.evidence.create"),
        ("software-domain", "github.policy.override"),
    ],
    "platform-optimizer": [
        ("agent-platform", "context.read"), ("agent-platform", "systems.read"),
        ("agent-platform", "goals.read"), ("agent-platform", "capabilities.read"),
        ("agent-platform", "request.read"), ("agent-platform", "runtime_tools.read"),
        ("agent-platform", "process.optimize"),
    ],
}

def _random_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(_RANDOM_ID_HEX_CHARS // 2)}"


def _derive_token_material(token: str, *, salt: str | None = None) -> tuple[str, str]:
    salt_bytes = bytes.fromhex(salt) if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS)
    return salt_bytes.hex(), digest.hex()


def _verify_token(token: str, *, salt: str, digest_hex: str) -> bool:
    _, computed = _derive_token_material(token, salt=salt)
    return hmac.compare_digest(computed, digest_hex)


def _agent_seed_blueprint() -> list[tuple[str, str, str, str]]:
    return [
        ("main-01", "main", "trading-system", "Control"),
        ("nexus-01", "nexus", "trading-system", "Control"),
        ("sw-architect-01", "sw-architect", "software-domain", "Software"),
        ("trading-strategist-01", "trading-strategist", "trading-system", "Trading"),
        ("trading-analyst-01", "trading-analyst", "trading-system", "Trading"),
        ("trading-sentinel-01", "trading-sentinel", "trading-system", "Trading"),
        ("sw-techlead-01", "sw-techlead", "software-domain", "Software"),
        ("sw-builder-01", "sw-builder", "software-domain", "Software"),
        ("sw-reviewer-01", "sw-reviewer", "software-domain", "Software"),
        ("platform-optimizer-01", "platform-optimizer", "agent-platform", "Control"),
    ]


def _resolve_seed_tokens(seed_tokens: dict[str, str] | None) -> dict[str, str]:
    if seed_tokens is None:
        return {agent_id: secrets.token_urlsafe(24) for agent_id, _, _, _ in _agent_seed_blueprint()}
    return {
        agent_id: seed_tokens.get(agent_id, secrets.token_urlsafe(24))
        for agent_id, _, _, _ in _agent_seed_blueprint()
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _required_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise NexusError("NX-VAL-001", f"{field} must be a string")
    text = value.strip()
    if not text:
        raise NexusError("NX-VAL-001", f"missing {field}")
    return text


def _required_json_array(values: list[str] | None, *, field: str) -> str:
    if values is None:
        return "[]"
    if not isinstance(values, list):
        raise NexusError("NX-VAL-001", f"{field} must be an array")
    return json.dumps([_required_text(item, field=field) for item in values], ensure_ascii=True)


def _optional_text(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise NexusError("NX-VAL-001", f"{field} must be a string")
    text = value.strip()
    return text or None


def _optional_string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise NexusError("NX-VAL-001", f"{field} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise NexusError("NX-VAL-001", f"{field} items must be strings")
        text = item.strip()
        if text:
            result.append(text)
    return result


def _normalize_implementation_context(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise NexusError("NX-VAL-001", "implementation_context must be an object")
    interfaces_raw = value.get("interfaces", [])
    interfaces: list[dict[str, str]] = []
    if interfaces_raw is not None:
        if not isinstance(interfaces_raw, list):
            raise NexusError("NX-VAL-001", "interfaces must be an array")
        for item in interfaces_raw:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    interfaces.append({"name": text, "signature": text})
                continue
            if not isinstance(item, dict):
                raise NexusError("NX-VAL-001", "interfaces items must be objects or strings")
            name = _optional_text(item.get("name"), field="interfaces.name") or ""
            signature = _optional_text(item.get("signature"), field="interfaces.signature") or name
            if name or signature:
                interfaces.append({"name": name or signature, "signature": signature})
    normalized = {
        "component": _optional_text(value.get("component"), field="component"),
        "entrypoints": _optional_string_list(value.get("entrypoints"), field="entrypoints"),
        "likely_files": _optional_string_list(value.get("likely_files"), field="likely_files"),
        "do_not_touch": _optional_string_list(value.get("do_not_touch"), field="do_not_touch"),
        "interfaces": interfaces,
        "acceptance_criteria": _optional_string_list(value.get("acceptance_criteria"), field="acceptance_criteria"),
        "test_commands": _optional_string_list(value.get("test_commands"), field="test_commands"),
        "notes": _optional_text(value.get("notes"), field="notes"),
    }
    return {key: val for key, val in normalized.items() if val not in (None, [], {})}


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS systems (
                system_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT NOT NULL,
                owner_agent_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('planned', 'active', 'paused', 'retired')),
                risk_level TEXT NOT NULL CHECK(risk_level IN ('low', 'medium', 'high', 'critical')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS goals (
                goal_id TEXT PRIMARY KEY,
                system_id TEXT NOT NULL,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                success_metrics_json TEXT NOT NULL,
                constraints_json TEXT NOT NULL,
                risk_class TEXT NOT NULL CHECK(risk_class IN ('low', 'medium', 'high', 'critical')),
                priority TEXT NOT NULL CHECK(priority IN ('P0', 'P1', 'P2', 'P3')),
                owner_agent_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('proposed', 'active', 'blocked', 'achieved', 'deprecated')),
                parent_goal_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(system_id) REFERENCES systems(system_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS goal_events (
                event_id TEXT PRIMARY KEY,
                goal_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor_agent_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capabilities (
                capability_id TEXT PRIMARY KEY,
                system_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('planned', 'in_progress', 'available', 'blocked', 'deprecated'))
            );

            CREATE TABLE IF NOT EXISTS capability_goal_links (
                capability_id TEXT NOT NULL,
                goal_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (capability_id, goal_id),
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE,
                FOREIGN KEY(goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_details (
                capability_id TEXT PRIMARY KEY,
                subfunction_ids TEXT NOT NULL,
                requirement_ids TEXT NOT NULL,
                state_summary TEXT NOT NULL,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_requirements (
                capability_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('not-started', 'in-progress', 'implemented', 'verified')),
                PRIMARY KEY (capability_id, requirement_id),
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_evidence (
                capability_id TEXT PRIMARY KEY,
                issue_ref TEXT NOT NULL,
                pr_ref TEXT NOT NULL,
                test_ref TEXT NOT NULL,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_status_events (
                event_id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                default_system_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS runtime_tools (
                tool_id TEXT PRIMARY KEY,
                system_id TEXT NOT NULL,
                capability_id TEXT,
                kind TEXT NOT NULL CHECK(kind IN ('service', 'cli', 'script', 'api', 'job')),
                mode TEXT NOT NULL CHECK(mode IN ('dev', 'test', 'paper', 'live', 'any')),
                status TEXT NOT NULL CHECK(status IN ('planned', 'in_progress', 'available', 'blocked', 'deprecated')),
                side_effect_level TEXT NOT NULL CHECK(side_effect_level IN ('read_only', 'simulation', 'paper_trade', 'live_trade', 'destructive')),
                required_scope TEXT NOT NULL,
                requires_human_approval INTEGER NOT NULL CHECK(requires_human_approval IN (0, 1)),
                allowed_roles_json TEXT NOT NULL,
                input_schema_json TEXT NOT NULL,
                output_schema_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(system_id) REFERENCES systems(system_id) ON DELETE CASCADE,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS agent_scope_grants (
                grant_id TEXT PRIMARY KEY,
                agent_id TEXT,
                role TEXT,
                system_id TEXT NOT NULL DEFAULT '*',
                scope TEXT NOT NULL,
                resource_pattern TEXT NOT NULL DEFAULT '*',
                granted_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked_at TEXT,
                CHECK(agent_id IS NOT NULL OR role IS NOT NULL)
            );
            CREATE INDEX IF NOT EXISTS idx_agent_scope_grants_agent ON agent_scope_grants(agent_id, system_id, scope);
            CREATE INDEX IF NOT EXISTS idx_agent_scope_grants_role ON agent_scope_grants(role, system_id, scope);

            CREATE TABLE IF NOT EXISTS auth_log (
                auth_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                default_system_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                default_system_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'expired', 'revoked')),
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_registry (
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                default_system_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1)),
                agent_token_hash TEXT NOT NULL,
                agent_token_salt TEXT NOT NULL,
                PRIMARY KEY (agent_id, default_system_id)
            );

            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY,
                dedupe_key TEXT NOT NULL UNIQUE,
                objective TEXT NOT NULL,
                missing_capability TEXT NOT NULL,
                business_impact TEXT NOT NULL,
                expected_behavior TEXT NOT NULL,
                acceptance_criteria_json TEXT NOT NULL,
                risk_class TEXT NOT NULL CHECK(risk_class IN ('low', 'medium', 'high', 'critical')),
                priority TEXT NOT NULL CHECK(priority IN ('P0', 'P1', 'P2', 'P3')),
                goal_ref TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'draft','submitted','gate-rejected','accepted','needs-planning','ready-to-build',
                    'in-build','in-review','approved','review-failed','state-update-needed','done',
                    'adoption-pending','closed','cancelled'
                )),
                submitted_by_agent_id TEXT NOT NULL,
                default_system_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                source_system_id TEXT NOT NULL,
                target_system_id TEXT NOT NULL,
                target_repo_id TEXT,
                branch TEXT,
                assigned_agent_id TEXT,
                sanitized_summary TEXT,
                implementation_context_json TEXT NOT NULL DEFAULT '{}',
                implementation_context_updated_by TEXT,
                implementation_context_updated_at TEXT,
                implementation_context_approved_by TEXT,
                implementation_context_approved_at TEXT,
                last_reason TEXT,
                last_actor_agent_id TEXT,
                last_transition_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS request_status_events (
                event_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor_agent_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                default_system_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(request_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS repositories (
                repo_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                system_id TEXT NOT NULL,
                owner_agent_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'archived', 'planned')),
                default_branch TEXT NOT NULL,
                allowed_agent_roles_json TEXT NOT NULL,
                github_owner TEXT,
                github_repo TEXT,
                github_default_branch TEXT,
                github_installation_id TEXT,
                github_node_id TEXT,
                github_html_url TEXT,
                github_sync_enabled INTEGER NOT NULL DEFAULT 0,
                github_last_synced_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(system_id) REFERENCES systems(system_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS github_issues (
                request_id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                github_owner TEXT NOT NULL,
                github_repo TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                issue_node_id TEXT,
                title TEXT NOT NULL,
                state TEXT NOT NULL,
                html_url TEXT NOT NULL,
                api_url TEXT,
                labels_json TEXT NOT NULL DEFAULT '[]',
                assignees_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                closed_at TEXT,
                last_synced_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(request_id) ON DELETE CASCADE,
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS github_pull_requests (
                request_id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                github_owner TEXT NOT NULL,
                github_repo TEXT NOT NULL,
                pr_number INTEGER NOT NULL,
                pr_node_id TEXT,
                title TEXT NOT NULL,
                state TEXT NOT NULL,
                draft INTEGER NOT NULL DEFAULT 0,
                merged INTEGER NOT NULL DEFAULT 0,
                merge_commit_sha TEXT,
                head_ref TEXT,
                head_sha TEXT,
                base_ref TEXT,
                html_url TEXT NOT NULL,
                api_url TEXT,
                review_state TEXT NOT NULL DEFAULT 'unknown',
                checks_state TEXT NOT NULL DEFAULT 'unknown',
                policy_state TEXT NOT NULL DEFAULT 'unknown',
                changed_files_json TEXT NOT NULL DEFAULT '[]',
                commits_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                merged_at TEXT,
                last_synced_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(request_id) ON DELETE CASCADE,
                FOREIGN KEY(repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS github_events (
                event_id TEXT PRIMARY KEY,
                delivery_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                action TEXT,
                request_id TEXT,
                repo_id TEXT,
                github_owner TEXT,
                github_repo TEXT,
                payload_json TEXT NOT NULL,
                received_at TEXT NOT NULL,
                processed_at TEXT,
                processing_status TEXT NOT NULL DEFAULT 'received',
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS work_evidence (
                evidence_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                ref TEXT,
                summary TEXT NOT NULL,
                submitted_by_agent_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(request_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS work_reviews (
                review_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK(verdict IN ('approved', 'changes-requested', 'rejected')),
                summary TEXT NOT NULL,
                reviewer_agent_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(request_id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_registry_token_hash ON agent_registry(agent_token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_request_work_target ON requests(target_system_id, assigned_agent_id, target_repo_id)")
        conn.commit()
    finally:
        conn.close()


def seed_mvp_data(db_path: Path, *, seed_tokens: dict[str, str] | None = None) -> dict[str, str] | None:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0]
        if existing > 0:
            _seed_missing_scope_defaults(conn)
            return None
        timestamp = _iso(_utc_now())
        resolved_tokens = _resolve_seed_tokens(seed_tokens)
        agent_rows: list[tuple[str, str, str, str, int, str, str]] = []
        for agent_id, role, default_system_id, domain in _agent_seed_blueprint():
            salt_hex, digest_hex = _derive_token_material(resolved_tokens[agent_id])
            agent_rows.append((agent_id, role, default_system_id, domain, 1, digest_hex, salt_hex))
        conn.executemany(
            """
            INSERT INTO agent_registry(agent_id, role, default_system_id, domain, active, agent_token_hash, agent_token_salt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            agent_rows,
        )
        conn.executemany(
            """
            INSERT INTO systems(system_id, name, purpose, owner_agent_id, status, risk_level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "trading-system",
                    "Trading System",
                    "Agent-orchestrated trading system with deterministic market-data, risk, paper-trading and controlled execution services.",
                    "trading-strategist-01",
                    "active",
                    "critical",
                    timestamp,
                    timestamp,
                ),
                (
                    "software-domain",
                    "Software Domain",
                    "Capability delivery lane for requirements, implementation, review and release governance.",
                    "sw-techlead-01",
                    "active",
                    "medium",
                    timestamp,
                    timestamp,
                ),
                (
                    "research-system",
                    "Research System",
                    "Reusable research source-of-truth for questions, sources, claims, evidence and reports.",
                    "nexus-01",
                    "planned",
                    "medium",
                    timestamp,
                    timestamp,
                ),
                (
                    "agent-platform",
                    "Agent Platform",
                    "OpenClaw agent contracts, process optimization and runtime orchestration hygiene.",
                    "platform-optimizer-01",
                    "active",
                    "medium",
                    timestamp,
                    timestamp,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO goals(
                goal_id, system_id, title, objective, success_metrics_json, constraints_json,
                risk_class, priority, owner_agent_id, status, parent_goal_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "TG-001", "trading-system", "Paper-Trading sicher bereitstellen",
                    "Paper-Trading muss reproduzierbar, auditierbar und ohne Live-Exchange-Seiteneffekte funktionieren.",
                    json.dumps(["paper orders are persisted", "no live credentials required", "deterministic replay available"]),
                    json.dumps(["no live order execution", "risk events must be logged"]),
                    "high", "P1", "trading-strategist-01", "active", None, timestamp, timestamp,
                ),
                (
                    "TG-002", "trading-system", "Marktdaten reproduzierbar erfassen",
                    "Market-data ingestion must provide timestamped, source-bound and replayable datasets.",
                    json.dumps(["fetch jobs record source and time", "normalization is deterministic"]),
                    json.dumps(["read-only external access", "source metadata required"]),
                    "medium", "P2", "trading-analyst-01", "active", None, timestamp, timestamp,
                ),
                (
                    "TG-003", "trading-system", "Risk-Limits deterministisch prüfen",
                    "Every trade intent must pass deterministic risk validation before any paper or live execution adapter can act.",
                    json.dumps(["risk verdict persisted", "failed checks block execution"]),
                    json.dumps(["LLM may create intents only", "live execution requires explicit approval"]),
                    "critical", "P0", "trading-sentinel-01", "active", None, timestamp, timestamp,
                ),
                (
                    "RG-001", "research-system", "Recherche nachvollziehbar machen",
                    "Research outputs must cite sources, capture retrieval timestamps and expose uncertainty.",
                    json.dumps(["source records include URL/ref and timestamp", "reports cite evidence ids"]),
                    json.dumps(["no uncited factual conclusions", "primary sources preferred"]),
                    "medium", "P2", "nexus-01", "proposed", None, timestamp, timestamp,
                ),
            ],
        )
        conn.executemany(
            "INSERT INTO capabilities(capability_id, system_id, domain, title, status) VALUES (?, ?, ?, ?, ?)",
            [
                ("F-001", "trading-system", "Trading", "Paper Trading", "planned"),
                ("F-002", "trading-system", "Trading", "Kraken API Integration", "planned"),
                ("F-003", "trading-system", "Trading", "Historical Market Data Ingestion", "planned"),
                ("R-001", "research-system", "Research", "Source Ingestion", "planned"),
                ("R-002", "research-system", "Research", "Evidence-Bound Report Generation", "planned"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO capability_goal_links(capability_id, goal_id, created_at)
            VALUES (?, ?, ?)
            """,
            [("F-001", "TG-001", timestamp), ("F-002", "TG-003", timestamp), ("F-003", "TG-002", timestamp), ("R-001", "RG-001", timestamp), ("R-002", "RG-001", timestamp)],
        )
        conn.executemany(
            """
            INSERT INTO capability_details(capability_id, subfunction_ids, requirement_ids, state_summary)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("F-001", json.dumps(["SF-001.1", "SF-001.2"]), json.dumps(["FR-001.1.1", "FR-001.2.1"]), "planned"),
                ("F-002", json.dumps(["SF-002.1"]), json.dumps(["FR-002.1.1", "FR-002.1.2"]), "planned"),
                ("F-003", json.dumps(["SF-003.1"]), json.dumps(["FR-003.1.1"]), "planned"),
                ("R-001", json.dumps(["SR-001.1"]), json.dumps(["RR-001.1.1"]), "planned"),
                ("R-002", json.dumps(["SR-002.1"]), json.dumps(["RR-002.1.1"]), "planned"),
            ],
        )
        conn.executemany(
            "INSERT INTO capability_requirements(capability_id, requirement_id, status) VALUES (?, ?, ?)",
            [
                ("F-001", "FR-001.1.1", "not-started"), ("F-001", "FR-001.2.1", "not-started"),
                ("F-002", "FR-002.1.1", "not-started"), ("F-002", "FR-002.1.2", "not-started"),
                ("F-003", "FR-003.1.1", "not-started"), ("R-001", "RR-001.1.1", "not-started"),
                ("R-002", "RR-002.1.1", "not-started"),
            ],
        )
        conn.executemany(
            "INSERT INTO capability_evidence(capability_id, issue_ref, pr_ref, test_ref) VALUES (?, ?, ?, ?)",
            [(cap, "none", "none", "none") for cap in ("F-001", "F-002", "F-003", "R-001", "R-002")],
        )
        conn.executemany(
            """
            INSERT INTO runtime_tools(
                tool_id, system_id, capability_id, kind, mode, status, side_effect_level,
                required_scope, requires_human_approval, allowed_roles_json,
                input_schema_json, output_schema_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "trading.marketdata.fetch", "trading-system", "F-003", "service", "any", "planned", "read_only",
                    "marketdata.read", 0, json.dumps(["trading-analyst", "trading-strategist", "trading-sentinel"]),
                    json.dumps({"type": "object", "required": ["symbol", "timeframe"]}),
                    json.dumps({"type": "object", "required": ["dataset_ref"]}), timestamp, timestamp,
                ),
                (
                    "trading.backtest.run", "trading-system", "F-001", "job", "test", "planned", "simulation",
                    "backtest.run", 0, json.dumps(["trading-strategist", "trading-analyst"]),
                    json.dumps({"type": "object", "required": ["strategy_ref", "dataset_ref"]}),
                    json.dumps({"type": "object", "required": ["report_ref"]}), timestamp, timestamp,
                ),
                (
                    "trading.risk.evaluate_order", "trading-system", "F-002", "service", "any", "planned", "read_only",
                    "risk.evaluate", 0, json.dumps(["trading-sentinel", "trading-strategist"]),
                    json.dumps({"type": "object", "required": ["trade_intent_ref"]}),
                    json.dumps({"type": "object", "required": ["verdict"]}), timestamp, timestamp,
                ),
                (
                    "trading.order.submit_live", "trading-system", "F-002", "service", "live", "blocked", "live_trade",
                    "trade.execute.live", 1, json.dumps([]),
                    json.dumps({"type": "object", "required": ["approved_trade_intent_ref"]}),
                    json.dumps({"type": "object", "required": ["exchange_order_ref"]}), timestamp, timestamp,
                ),
                (
                    "research.source.ingest", "research-system", "R-001", "service", "any", "planned", "read_only",
                    "source.create", 0, json.dumps(["researcher", "nexus"]),
                    json.dumps({"type": "object", "required": ["source_ref"]}),
                    json.dumps({"type": "object", "required": ["evidence_ref"]}), timestamp, timestamp,
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO repositories(
                repo_id, name, url, system_id, owner_agent_id, status, default_branch, allowed_agent_roles_json,
                github_owner, github_repo, github_default_branch, github_html_url, github_sync_enabled,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("nexusctl", "nexusctl", "https://github.com/local/nexusctl", "software-domain", "sw-techlead-01", "active", "main", json.dumps(["sw-architect", "sw-builder", "sw-reviewer", "sw-techlead"]), "local", "nexusctl", "main", "https://github.com/local/nexusctl", 1, timestamp, timestamp),
                ("trading-engine", "trading-engine", "https://github.com/local/trading-engine", "trading-system", "sw-techlead-01", "planned", "main", json.dumps(["sw-architect", "sw-builder", "sw-reviewer", "sw-techlead"]), "local", "trading-engine", "main", "https://github.com/local/trading-engine", 1, timestamp, timestamp),
                ("research-pipeline", "research-pipeline", "https://github.com/local/research-pipeline", "research-system", "sw-techlead-01", "planned", "main", json.dumps(["sw-architect", "sw-builder", "sw-reviewer", "sw-techlead"]), "local", "research-pipeline", "main", "https://github.com/local/research-pipeline", 1, timestamp, timestamp),
                ("openclaw-agent-config", "openclaw-agent-config", "https://github.com/local/openclaw-agent-config", "agent-platform", "platform-optimizer-01", "active", "main", json.dumps(["sw-architect", "sw-builder", "sw-reviewer", "sw-techlead", "platform-optimizer"]), "local", "openclaw-agent-config", "main", "https://github.com/local/openclaw-agent-config", 1, timestamp, timestamp),
            ],
        )
        _seed_missing_scope_defaults(conn)
        conn.commit()
        return resolved_tokens
    finally:
        conn.close()


def _seed_missing_scope_defaults(conn: sqlite3.Connection) -> None:
    timestamp = _iso(_utc_now())
    rows: list[tuple[str, str | None, str | None, str, str, str, str, str, None, None]] = []
    for role, grants in sorted(_ROLE_SCOPE_DEFAULTS.items()):
        for system_id, scope in grants:
            existing = conn.execute(
                """
                SELECT 1 FROM agent_scope_grants
                WHERE role = ? AND agent_id IS NULL AND system_id = ? AND scope = ? AND revoked_at IS NULL
                """,
                (role, system_id, scope),
            ).fetchone()
            if existing:
                continue
            rows.append((_random_id("SCOPE-2026-"), None, role, system_id, scope, "*", "seed", timestamp, None, None))
    if rows:
        conn.executemany(
            """
            INSERT INTO agent_scope_grants(
                grant_id, agent_id, role, system_id, scope, resource_pattern, granted_by, created_at, expires_at, revoked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


@dataclass
class SessionContext:
    session_id: str
    agent_id: str
    role: str
    default_system_id: str
    domain: str


class Storage:
    def __init__(self, db_path: Path, github_client: Any | None = None):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._github_client = github_client

    def _github_client_or_default(self) -> Any:
        if self._github_client is None:
            self._github_client = GitHubClient(env=os.environ)
        return self._github_client

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.row_factory = sqlite3.Row
        return conn

    def authenticate(self, *, agent_token: str) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT agent_id, role, default_system_id, domain, active, agent_token_hash, agent_token_salt
                    FROM agent_registry
                    WHERE active = 1
                    """,
                ).fetchall()
                row = next(
                    (
                        item
                        for item in rows
                        if item["agent_token_hash"]
                        and item["agent_token_salt"]
                        and _verify_token(
                            agent_token,
                            salt=item["agent_token_salt"],
                            digest_hex=item["agent_token_hash"],
                        )
                    ),
                    None,
                )
                if row is None:
                    raise NexusError("NX-PERM-001", "invalid or inactive token")
                auth_id = _random_id("AUTH-2026-")
                session_id = _random_id("S-2026-")
                timestamp = _utc_now()
                expires_at = timestamp + timedelta(minutes=60)
                resolved_domain = row["domain"]
                conn.execute(
                    """
                    INSERT INTO agent_sessions(session_id, agent_id, role, default_system_id, domain, status, issued_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        session_id,
                        row["agent_id"],
                        row["role"],
                        row["default_system_id"],
                        resolved_domain,
                        _iso(timestamp),
                        _iso(expires_at),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO auth_log(auth_id, session_id, agent_id, role, default_system_id, domain, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (auth_id, session_id, row["agent_id"], row["role"], row["default_system_id"], resolved_domain, _iso(timestamp)),
                )
                scopes = self._effective_scopes(conn, agent_id=row["agent_id"], role=row["role"])
                cap_systems = {item["system_id"] for item in scopes if item["scope"] == "capabilities.read"}
                if "*" in cap_systems:
                    capabilities = self._query_capabilities(conn, status_filter="all", system_ids=None)
                else:
                    capabilities = []
                    for item_system_id in sorted(cap_systems):
                        capabilities.extend(self._query_capabilities(conn, status_filter="all", system_ids=[item_system_id]))
                conn.commit()
                return {
                    "ok": True,
                    "auth_id": auth_id,
                    "session_id": session_id,
                    "agent_id": row["agent_id"],
                    "role": row["role"],
                    "default_system_id": row["default_system_id"],
                    "domain": resolved_domain,
                    "timestamp": _iso(timestamp),
                    "expires_at": _iso(expires_at),
                    "capabilities": capabilities,
                    "allowed_actions": sorted({item["scope"] for item in scopes}),
                }
            finally:
                conn.close()

    def validate_session(self, session_id: str) -> SessionContext:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, agent_id, role, default_system_id, domain, status, expires_at
                FROM agent_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None or row["status"] != "active":
                raise NexusError("NX-PRECONDITION-001", "no active session")
            if _parse_iso(row["expires_at"]) <= _utc_now():
                conn.execute("UPDATE agent_sessions SET status = 'expired' WHERE session_id = ?", (session_id,))
                conn.commit()
                raise NexusError("NX-PRECONDITION-002", "session expired")
            return SessionContext(
                session_id=row["session_id"], agent_id=row["agent_id"], role=row["role"],
                default_system_id=row["default_system_id"], domain=row["domain"],
            )
        finally:
            conn.close()

    # ----- Policy / scopes -----
    def _effective_scopes(self, conn: sqlite3.Connection, *, agent_id: str, role: str) -> list[dict[str, str]]:
        now = _iso(_utc_now())
        rows = conn.execute(
            """
            SELECT system_id, scope, resource_pattern
            FROM agent_scope_grants
            WHERE revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
              AND ((agent_id = ?) OR (agent_id IS NULL AND role = ?))
            ORDER BY system_id, scope
            """,
            (now, agent_id, role),
        ).fetchall()
        unique: dict[tuple[str, str, str], dict[str, str]] = {}
        for row in rows:
            key = (row["system_id"], row["scope"], row["resource_pattern"])
            unique[key] = {"system_id": row["system_id"], "scope": row["scope"], "resource_pattern": row["resource_pattern"]}
        return list(unique.values())

    def _has_scope(self, conn: sqlite3.Connection, *, actor: SessionContext, scope: str, system_id: str | None = None) -> bool:
        system_id = system_id or actor.default_system_id
        for grant in self._effective_scopes(conn, agent_id=actor.agent_id, role=actor.role):
            if grant["scope"] != scope:
                continue
            if grant["system_id"] in {"*", system_id}:
                return True
        return False

    def _require_scope(self, conn: sqlite3.Connection, *, actor: SessionContext, scope: str, system_id: str | None = None) -> None:
        if not self._has_scope(conn, actor=actor, scope=scope, system_id=system_id):
            target = f" for {system_id}" if system_id else ""
            raise NexusError("NX-PERM-001", f"missing scope {scope}{target}")

    def list_scopes(self, *, actor: SessionContext, target_agent_id: str | None = None) -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="scopes.read", system_id=actor.default_system_id)
            if target_agent_id:
                agent = conn.execute("SELECT agent_id, role FROM agent_registry WHERE agent_id = ?", (target_agent_id,)).fetchone()
                if agent is None:
                    raise NexusError("NX-NOTFOUND-001", "agent not found")
                scopes = self._effective_scopes(conn, agent_id=agent["agent_id"], role=agent["role"])
                return {"agent_id": agent["agent_id"], "role": agent["role"], "scopes": scopes}
            rows = conn.execute(
                """
                SELECT grant_id, agent_id, role, system_id, scope, resource_pattern, granted_by, created_at, expires_at, revoked_at
                FROM agent_scope_grants
                ORDER BY COALESCE(role, agent_id), system_id, scope
                """
            ).fetchall()
            return {"scopes": [dict(row) for row in rows]}
        finally:
            conn.close()

    def effective_scopes(self, *, actor: SessionContext) -> dict[str, Any]:
        conn = self._connect()
        try:
            scopes = self._effective_scopes(conn, agent_id=actor.agent_id, role=actor.role)
            return {"agent_id": actor.agent_id, "role": actor.role, "scopes": scopes}
        finally:
            conn.close()

    # ----- Systems -----
    def list_systems(self, *, actor: SessionContext, status_filter: str = "all") -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="systems.read", system_id=actor.default_system_id)
            if status_filter != "all" and status_filter not in _SYSTEM_STATUSES:
                raise NexusError("NX-VAL-001", "invalid system status filter")
            clauses: list[str] = []
            params: list[Any] = []
            if status_filter != "all":
                clauses.append("status = ?")
                params.append(status_filter)
            readable_systems = self._readable_systems(conn, actor=actor, scope="systems.read")
            if readable_systems is not None:
                clauses.append("system_id IN ({})".format(", ".join("?" for _ in readable_systems)))
                params.extend(sorted(readable_systems))
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                f"""
                SELECT system_id, name, purpose, owner_agent_id, status, risk_level, created_at, updated_at
                FROM systems
                {where}
                ORDER BY system_id ASC
                """,
                params,
            ).fetchall()
            return {"systems": [dict(row) for row in rows]}
        finally:
            conn.close()

    def show_system(self, *, actor: SessionContext, system_id: str) -> dict[str, Any]:
        # system_id may be omitted by single-system agents; Nexus resolves it from effective scopes.
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="systems.read", system_id=system_id)
            row = conn.execute(
                """
                SELECT system_id, name, purpose, owner_agent_id, status, risk_level, created_at, updated_at
                FROM systems WHERE system_id = ?
                """,
                (system_id,),
            ).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "system not found")
            goals = self._query_goals(conn, actor=actor, system_id=system_id, status_filter="all", limit=20)
            capabilities = self._query_capabilities(conn, status_filter="all", system_ids=[system_id])
            tools = self._query_runtime_tools(conn, actor=actor, system_id=system_id, status_filter="all")
            payload = dict(row)
            payload["goals"] = goals
            payload["capabilities"] = capabilities
            payload["runtime_tools"] = tools
            return payload
        finally:
            conn.close()

    def _readable_systems(self, conn: sqlite3.Connection, *, actor: SessionContext, scope: str) -> set[str] | None:
        grants = self._effective_scopes(conn, agent_id=actor.agent_id, role=actor.role)
        scope_grants = [grant for grant in grants if grant["scope"] == scope]
        if any(grant["system_id"] == "*" for grant in scope_grants):
            return None
        return {grant["system_id"] for grant in scope_grants}

    def _resolve_system_id_for_action(
        self,
        conn: sqlite3.Connection,
        *,
        actor: SessionContext,
        scope: str,
        system_id: str | None,
        field: str = "system_id",
    ) -> str:
        if system_id:
            resolved = _required_text(system_id, field=field)
            self._require_scope(conn, actor=actor, scope=scope, system_id=resolved)
            return resolved
        readable = self._readable_systems(conn, actor=actor, scope=scope)
        if readable is None:
            if actor.default_system_id:
                self._require_scope(conn, actor=actor, scope=scope, system_id=actor.default_system_id)
                return actor.default_system_id
            raise NexusError("NX-VAL-001", f"missing {field}")
        if len(readable) == 1:
            return next(iter(readable))
        if actor.default_system_id in readable:
            return actor.default_system_id
        raise NexusError("NX-VAL-001", f"multiple systems visible; provide --{field.replace('_', '-')} explicitly")

    # ----- Goals -----
    def list_goals(self, *, actor: SessionContext, system_id: str | None = None, status_filter: str = "all", limit: int = 100) -> dict[str, Any]:
        conn = self._connect()
        try:
            if system_id:
                self._require_scope(conn, actor=actor, scope="goals.read", system_id=system_id)
            else:
                self._require_scope(conn, actor=actor, scope="goals.read", system_id=actor.default_system_id)
            return {"goals": self._query_goals(conn, actor=actor, system_id=system_id, status_filter=status_filter, limit=limit)}
        finally:
            conn.close()

    def show_goal(self, *, actor: SessionContext, goal_id: str) -> dict[str, Any]:
        goal_id = _required_text(goal_id, field="goal_id")
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT goal_id, system_id, title, objective, success_metrics_json, constraints_json,
                       risk_class, priority, owner_agent_id, status, parent_goal_id, created_at, updated_at
                FROM goals WHERE goal_id = ?
                """,
                (goal_id,),
            ).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "goal not found")
            self._require_scope(conn, actor=actor, scope="goals.read", system_id=row["system_id"])
            payload = self._goal_row_to_dict(row)
            caps = conn.execute(
                """
                SELECT c.capability_id, c.title, c.status
                FROM capability_goal_links l
                JOIN capabilities c ON c.capability_id = l.capability_id
                WHERE l.goal_id = ?
                ORDER BY c.capability_id
                """,
                (goal_id,),
            ).fetchall()
            events = conn.execute(
                """
                SELECT event_id, old_status, new_status, reason, actor_agent_id, timestamp
                FROM goal_events WHERE goal_id = ? ORDER BY timestamp DESC LIMIT 20
                """,
                (goal_id,),
            ).fetchall()
            payload["capabilities"] = [dict(row) for row in caps]
            payload["events"] = [dict(row) for row in events]
            return payload
        finally:
            conn.close()

    def create_goal(
        self,
        *,
        actor: SessionContext,
        goal_id: str,
        system_id: str | None,
        title: str,
        objective: str,
        success_metrics: list[str] | None,
        constraints: list[str] | None,
        risk_class: str,
        priority: str,
        owner_agent_id: str | None,
        status: str = "proposed",
        parent_goal_id: str | None = None,
    ) -> dict[str, Any]:
        goal_id = _required_text(goal_id, field="goal_id")
        # system_id may be omitted by single-system agents; Nexus resolves it from effective scopes.
        title = _required_text(title, field="title")
        objective = _required_text(objective, field="objective")
        owner_agent_id = _required_text(owner_agent_id or actor.agent_id, field="owner_agent_id")
        if risk_class not in _REQUEST_RISK_CLASSES:
            raise NexusError("NX-VAL-001", "invalid risk_class")
        if priority not in _REQUEST_PRIORITIES:
            raise NexusError("NX-VAL-001", "invalid priority")
        if status not in _GOAL_STATUSES:
            raise NexusError("NX-VAL-001", "invalid goal status")
        with self._lock:
            conn = self._connect()
            try:
                system_id = self._resolve_system_id_for_action(conn, actor=actor, scope="goals.create", system_id=system_id)
                if conn.execute("SELECT 1 FROM systems WHERE system_id = ?", (system_id,)).fetchone() is None:
                    raise NexusError("NX-NOTFOUND-001", "system not found")
                if parent_goal_id and conn.execute("SELECT 1 FROM goals WHERE goal_id = ?", (parent_goal_id,)).fetchone() is None:
                    raise NexusError("NX-NOTFOUND-001", "parent goal not found")
                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    INSERT INTO goals(
                        goal_id, system_id, title, objective, success_metrics_json, constraints_json,
                        risk_class, priority, owner_agent_id, status, parent_goal_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        goal_id, system_id, title, objective,
                        _required_json_array(success_metrics, field="success_metrics"),
                        _required_json_array(constraints, field="constraints"),
                        risk_class, priority, owner_agent_id, status, parent_goal_id, timestamp, timestamp,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO goal_events(event_id, goal_id, old_status, new_status, reason, actor_agent_id, timestamp)
                    VALUES (?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (_random_id("GOAL-EVENT-2026-"), goal_id, status, "created", actor.agent_id, timestamp),
                )
                conn.commit()
                return self.show_goal(actor=actor, goal_id=goal_id)
            finally:
                conn.close()

    def update_goal_status(self, *, actor: SessionContext, goal_id: str, to_status: str, reason: str) -> dict[str, Any]:
        reason_text = _required_text(reason, field="reason")
        if to_status not in _GOAL_STATUSES:
            raise NexusError("NX-VAL-001", "invalid goal status")
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT status, system_id FROM goals WHERE goal_id = ?", (goal_id,)).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "goal not found")
                self._require_scope(conn, actor=actor, scope="goals.update-status", system_id=row["system_id"])
                old_status = row["status"]
                timestamp = _iso(_utc_now())
                conn.execute("UPDATE goals SET status = ?, updated_at = ? WHERE goal_id = ?", (to_status, timestamp, goal_id))
                event_id = _random_id("GOAL-EVENT-2026-")
                conn.execute(
                    """
                    INSERT INTO goal_events(event_id, goal_id, old_status, new_status, reason, actor_agent_id, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, goal_id, old_status, to_status, reason_text, actor.agent_id, timestamp),
                )
                conn.commit()
                return {
                    "ok": True, "event_id": event_id, "goal_id": goal_id, "from_status": old_status,
                    "to_status": to_status, "reason": reason_text, "agent_id": actor.agent_id, "timestamp": timestamp,
                }
            finally:
                conn.close()

    def _query_goals(
        self, conn: sqlite3.Connection, *, actor: SessionContext, system_id: str | None, status_filter: str, limit: int
    ) -> list[dict[str, Any]]:
        if status_filter != "all" and status_filter not in _GOAL_STATUSES:
            raise NexusError("NX-VAL-001", "invalid goal status filter")
        if limit <= 0 or limit > 1000:
            raise NexusError("NX-VAL-001", "invalid goal limit")
        clauses: list[str] = []
        params: list[Any] = []
        if system_id:
            clauses.append("system_id = ?")
            params.append(system_id)
        else:
            readable_systems = self._readable_systems(conn, actor=actor, scope="goals.read")
            if readable_systems is not None:
                clauses.append("system_id IN ({})".format(", ".join("?" for _ in readable_systems)))
                params.extend(sorted(readable_systems))
        if status_filter != "all":
            clauses.append("status = ?")
            params.append(status_filter)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT goal_id, system_id, title, objective, success_metrics_json, constraints_json,
                   risk_class, priority, owner_agent_id, status, parent_goal_id, created_at, updated_at
            FROM goals
            {where}
            ORDER BY priority ASC, goal_id ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [self._goal_row_to_dict(row) for row in rows]

    @staticmethod
    def _goal_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "goal_id": row["goal_id"], "system_id": row["system_id"], "title": row["title"],
            "objective": row["objective"], "success_metrics": json.loads(row["success_metrics_json"]),
            "constraints": json.loads(row["constraints_json"]), "risk_class": row["risk_class"],
            "priority": row["priority"], "owner_agent_id": row["owner_agent_id"], "status": row["status"],
            "parent_goal_id": row["parent_goal_id"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    # ----- Capabilities -----
    def list_capabilities(self, *, actor: SessionContext | None = None, status_filter: str = "all", system_id: str | None = None) -> dict[str, Any]:
        conn = self._connect()
        try:
            system_ids: list[str] | None = None
            if actor is not None:
                if system_id:
                    self._require_scope(conn, actor=actor, scope="capabilities.read", system_id=system_id)
                    system_ids = [system_id]
                else:
                    readable = self._readable_systems(conn, actor=actor, scope="capabilities.read")
                    if readable is None:
                        system_ids = None
                    else:
                        system_ids = sorted(readable)
            elif system_id:
                system_ids = [system_id]
            return {"capabilities": self._query_capabilities(conn, status_filter=status_filter, system_ids=system_ids)}
        finally:
            conn.close()

    def show_capability(self, capability_id: str, *, actor: SessionContext | None = None) -> dict[str, Any]:
        conn = self._connect()
        try:
            base = conn.execute(
                "SELECT capability_id, system_id, domain, title, status FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            if base is None:
                raise NexusError("NX-NOTFOUND-001", "capability not found")
            if actor is not None:
                self._require_scope(conn, actor=actor, scope="capabilities.read", system_id=base["system_id"])
            detail = conn.execute(
                "SELECT subfunction_ids, requirement_ids FROM capability_details WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            subfunctions = json.loads(detail["subfunction_ids"]) if detail else []
            requirements = json.loads(detail["requirement_ids"]) if detail else []
            linked_goals = conn.execute(
                """
                SELECT g.goal_id, g.title, g.status
                FROM capability_goal_links l JOIN goals g ON g.goal_id = l.goal_id
                WHERE l.capability_id = ? ORDER BY g.goal_id
                """,
                (capability_id,),
            ).fetchall()
            return {
                "capability_id": base["capability_id"], "system_id": base["system_id"], "domain": base["domain"],
                "title": base["title"], "status": base["status"], "subfunctions": subfunctions,
                "requirements": requirements, "goals": [dict(row) for row in linked_goals],
            }
        finally:
            conn.close()

    def set_status(self, *, actor: SessionContext, capability_id: str, to_status: str, reason: str) -> dict[str, Any]:
        reason_text = _required_text(reason, field="reason")
        if to_status != "available":
            raise NexusError("NX-PRECONDITION-003", "MVP allows only planned -> available")

        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT status, system_id FROM capabilities WHERE capability_id = ?", (capability_id,)).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "capability not found")
                self._require_scope(conn, actor=actor, scope="capabilities.set-status", system_id=row["system_id"])
                old_status = row["status"]
                if old_status != "planned":
                    raise NexusError("NX-PRECONDITION-003", "invalid transition")

                req_rows = conn.execute("SELECT status FROM capability_requirements WHERE capability_id = ?", (capability_id,)).fetchall()
                if not req_rows or any(r["status"] != "verified" for r in req_rows):
                    raise NexusError("NX-PRECONDITION-003", "requirements not fully verified")

                evidence = conn.execute(
                    "SELECT issue_ref, pr_ref, test_ref FROM capability_evidence WHERE capability_id = ?", (capability_id,)
                ).fetchone()
                if evidence is None:
                    raise NexusError("NX-PRECONDITION-003", "missing evidence")
                if evidence["issue_ref"] == "none" or evidence["pr_ref"] == "none" or evidence["test_ref"] == "none":
                    raise NexusError("NX-PRECONDITION-003", "evidence incomplete")

                event_id = _random_id("CAP-STATUS-2026-")
                timestamp = _iso(_utc_now())
                conn.execute("UPDATE capabilities SET status = ? WHERE capability_id = ?", (to_status, capability_id))
                conn.execute("UPDATE capability_details SET state_summary = 'available' WHERE capability_id = ?", (capability_id,))
                conn.execute(
                    """
                    INSERT INTO capability_status_events(event_id, capability_id, old_status, new_status, reason, agent_id, default_system_id, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, capability_id, old_status, to_status, reason_text, actor.agent_id, actor.default_system_id, timestamp),
                )
                conn.commit()
                return {
                    "ok": True, "event_id": event_id, "capability_id": capability_id, "old_status": old_status,
                    "new_status": to_status, "reason": reason_text, "agent_id": actor.agent_id,
                    "default_system_id": actor.default_system_id, "timestamp": timestamp,
                }
            finally:
                conn.close()

    # ----- Runtime tools -----
    def list_runtime_tools(self, *, actor: SessionContext, system_id: str | None = None, status_filter: str = "all") -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="runtime_tools.read", system_id=system_id or actor.default_system_id)
            return {"runtime_tools": self._query_runtime_tools(conn, actor=actor, system_id=system_id, status_filter=status_filter)}
        finally:
            conn.close()

    def show_runtime_tool(self, *, actor: SessionContext, tool_id: str) -> dict[str, Any]:
        tool_id = _required_text(tool_id, field="tool_id")
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT tool_id, system_id, capability_id, kind, mode, status, side_effect_level, required_scope,
                       requires_human_approval, allowed_roles_json, input_schema_json, output_schema_json, created_at, updated_at
                FROM runtime_tools WHERE tool_id = ?
                """,
                (tool_id,),
            ).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "runtime tool not found")
            self._require_scope(conn, actor=actor, scope="runtime_tools.read", system_id=row["system_id"])
            return self._runtime_tool_row_to_dict(row)
        finally:
            conn.close()

    def _query_runtime_tools(self, conn: sqlite3.Connection, *, actor: SessionContext, system_id: str | None, status_filter: str) -> list[dict[str, Any]]:
        if status_filter != "all" and status_filter not in _RUNTIME_TOOL_STATUSES:
            raise NexusError("NX-VAL-001", "invalid runtime tool status filter")
        clauses: list[str] = []
        params: list[Any] = []
        if system_id:
            clauses.append("system_id = ?")
            params.append(system_id)
        else:
            readable_systems = self._readable_systems(conn, actor=actor, scope="runtime_tools.read")
            if readable_systems is not None:
                clauses.append("system_id IN ({})".format(", ".join("?" for _ in readable_systems)))
                params.extend(sorted(readable_systems))
        if status_filter != "all":
            clauses.append("status = ?")
            params.append(status_filter)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT tool_id, system_id, capability_id, kind, mode, status, side_effect_level, required_scope,
                   requires_human_approval, allowed_roles_json, input_schema_json, output_schema_json, created_at, updated_at
            FROM runtime_tools
            {where}
            ORDER BY system_id, tool_id
            """,
            params,
        ).fetchall()
        return [self._runtime_tool_row_to_dict(row) for row in rows]

    @staticmethod
    def _runtime_tool_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "tool_id": row["tool_id"], "system_id": row["system_id"], "capability_id": row["capability_id"],
            "kind": row["kind"], "mode": row["mode"], "status": row["status"],
            "side_effect_level": row["side_effect_level"], "required_scope": row["required_scope"],
            "requires_human_approval": bool(row["requires_human_approval"]),
            "allowed_roles": json.loads(row["allowed_roles_json"]),
            "input_schema": json.loads(row["input_schema_json"]),
            "output_schema": json.loads(row["output_schema_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    # ----- Requests -----
    def create_request(
        self,
        *,
        actor: SessionContext,
        objective: str,
        missing_capability: str,
        business_impact: str,
        expected_behavior: str,
        acceptance_criteria: list[str],
        risk_class: str,
        priority: str,
        goal_ref: str,
    ) -> dict[str, Any]:
        objective = _required_text(objective, field="objective")
        missing_capability = _required_text(missing_capability, field="missing_capability")
        business_impact = _required_text(business_impact, field="business_impact")
        expected_behavior = _required_text(expected_behavior, field="expected_behavior")
        goal_ref = _required_text(goal_ref, field="goal_ref")
        if risk_class not in _REQUEST_RISK_CLASSES:
            raise NexusError("NX-VAL-001", "invalid risk_class")
        if priority not in _REQUEST_PRIORITIES:
            raise NexusError("NX-VAL-001", "invalid priority")
        if not acceptance_criteria:
            raise NexusError("NX-VAL-001", "missing acceptance_criteria")
        normalized_criteria = [_required_text(item, field="acceptance_criteria") for item in acceptance_criteria]
        initial_status = "draft" if actor.role == "trading-sentinel" else "submitted"
        required_scope = "request.draft.create" if initial_status == "draft" else "request.create"

        dedupe_payload = {
            "default_system_id": actor.default_system_id,
            "submitted_by_agent_id": actor.agent_id,
            "objective": objective,
            "missing_capability": missing_capability,
            "business_impact": business_impact,
            "expected_behavior": expected_behavior,
            "acceptance_criteria": normalized_criteria,
            "risk_class": risk_class,
            "priority": priority,
            "goal_ref": goal_ref,
        }
        dedupe_key = hashlib.sha256(
            json.dumps(dedupe_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()

        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope=required_scope, system_id=actor.default_system_id)
                timestamp = _iso(_utc_now())
                row = conn.execute(
                    """
                    SELECT request_id, created_at, status, submitted_by_agent_id
                    FROM requests
                    WHERE dedupe_key = ?
                    """,
                    (dedupe_key,),
                ).fetchone()
                updated_existing = row is not None
                if row is None:
                    request_id = _random_id("REQ-2026-")
                    created_at = timestamp
                    current_status = initial_status
                    conn.execute(
                        """
                        INSERT INTO requests(
                            request_id, dedupe_key, objective, missing_capability, business_impact,
                            expected_behavior, acceptance_criteria_json, risk_class, priority, goal_ref,
                            status, submitted_by_agent_id, default_system_id, domain, source_system_id, target_system_id,
                            last_reason, last_actor_agent_id, last_transition_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            request_id, dedupe_key, objective, missing_capability, business_impact,
                            expected_behavior, json.dumps(normalized_criteria, ensure_ascii=True), risk_class, priority,
                            goal_ref, initial_status, actor.agent_id, actor.default_system_id, actor.domain,
                            actor.default_system_id, "software-domain", initial_status, actor.agent_id,
                            timestamp, created_at, timestamp,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO request_status_events(
                            event_id, request_id, from_status, to_status, reason, actor_agent_id, actor_role, default_system_id, domain, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (_random_id("RS-2026-"), request_id, None, initial_status, initial_status, actor.agent_id, actor.role, actor.default_system_id, actor.domain, timestamp),
                    )
                else:
                    if row["submitted_by_agent_id"] != actor.agent_id:
                        raise NexusError("NX-PERM-001", "duplicate request belongs to another actor")
                    request_id = row["request_id"]
                    created_at = row["created_at"]
                    current_status = row["status"]
                    conn.execute(
                        """
                        UPDATE requests
                        SET objective = ?, missing_capability = ?, business_impact = ?, expected_behavior = ?,
                            acceptance_criteria_json = ?, risk_class = ?, priority = ?, goal_ref = ?,
                            domain = ?, updated_at = ?
                        WHERE request_id = ?
                        """,
                        (
                            objective, missing_capability, business_impact, expected_behavior,
                            json.dumps(normalized_criteria, ensure_ascii=True), risk_class, priority, goal_ref,
                            actor.domain, timestamp, request_id,
                        ),
                    )
                conn.commit()
                return {
                    "ok": True,
                    "request_id": request_id,
                    "status": current_status,
                    "objective": objective,
                    "missing_capability": missing_capability,
                    "business_impact": business_impact,
                    "expected_behavior": expected_behavior,
                    "acceptance_criteria": normalized_criteria,
                    "risk_class": risk_class,
                    "priority": priority,
                    "goal_ref": goal_ref,
                    "agent_id": actor.agent_id,
                    "default_system_id": actor.default_system_id,
                    "domain": actor.domain,
                    "timestamp": timestamp,
                    "created_at": created_at,
                    "updated_existing": updated_existing,
                }
            finally:
                conn.close()

    def list_requests(self, *, actor: SessionContext, status_filter: str = "submitted", limit: int = 100) -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="request.read", system_id=actor.default_system_id)
            if status_filter != "all" and status_filter not in _REQUEST_STATUSES:
                raise NexusError("NX-VAL-001", "invalid request status filter")
            if limit <= 0 or limit > 1000:
                raise NexusError("NX-VAL-001", "invalid request limit")
            where_clauses: list[str] = []
            params: list[Any] = []
            if status_filter == "draft" and actor.role not in {"trading-strategist", "trading-sentinel"}:
                raise NexusError("NX-PERM-001", "unauthorized to view draft requests")
            if status_filter != "all":
                where_clauses.append("status = ?")
                params.append(status_filter)
            elif actor.role not in {"trading-strategist", "trading-sentinel"}:
                where_clauses.append("status != 'draft'")
            if actor.role == "nexus":
                pass
            elif actor.role.startswith("trading-"):
                where_clauses.append("submitted_by_agent_id = ?")
                params.append(actor.agent_id)
            else:
                where_clauses.append("default_system_id = ?")
                params.append(actor.default_system_id)
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            rows = conn.execute(
                f"""
                SELECT request_id, status, objective, missing_capability, business_impact, expected_behavior,
                       acceptance_criteria_json, risk_class, priority, goal_ref, submitted_by_agent_id,
                       default_system_id, domain, source_system_id, target_system_id, target_repo_id, branch,
                       assigned_agent_id, sanitized_summary, created_at, updated_at
                FROM requests
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return {"requests": [self._request_row_to_dict(row) for row in rows]}
        finally:
            conn.close()

    def show_request(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="request.read", system_id=actor.default_system_id)
            row = conn.execute(
                """
                SELECT request_id, status, objective, missing_capability, business_impact, expected_behavior,
                       acceptance_criteria_json, risk_class, priority, goal_ref,
                       submitted_by_agent_id, default_system_id, domain, source_system_id, target_system_id,
                       target_repo_id, branch, assigned_agent_id, sanitized_summary, last_reason, last_actor_agent_id,
                       last_transition_at, created_at, updated_at
                FROM requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "request not found")
            if row["status"] == "draft" and actor.role not in {"trading-strategist", "trading-sentinel"}:
                raise NexusError("NX-PERM-001", "unauthorized to view draft requests")
            if actor.role != "nexus" and actor.role.startswith("trading-") and row["submitted_by_agent_id"] != actor.agent_id:
                raise NexusError("NX-PERM-001", "request is outside actor scope")
            if actor.role not in {"nexus"} and not actor.role.startswith("trading-") and row["default_system_id"] != actor.default_system_id:
                raise NexusError("NX-PERM-001", "request is outside actor scope")
            payload = self._request_row_to_dict(row)
            payload.update({
                "last_reason": row["last_reason"],
                "last_actor_agent_id": row["last_actor_agent_id"], "last_transition_at": row["last_transition_at"],
            })
            return payload
        finally:
            conn.close()

    @staticmethod
    def _request_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "request_id": row["request_id"], "status": row["status"],
            "objective": row["objective"], "missing_capability": row["missing_capability"],
            "business_impact": row["business_impact"], "expected_behavior": row["expected_behavior"],
            "acceptance_criteria": json.loads(row["acceptance_criteria_json"]), "risk_class": row["risk_class"],
            "priority": row["priority"], "goal_ref": row["goal_ref"],
            "submitted_by_agent_id": row["submitted_by_agent_id"], "default_system_id": row["default_system_id"],
            "domain": row["domain"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
        for key in ("source_system_id", "target_system_id", "target_repo_id", "branch", "assigned_agent_id", "sanitized_summary"):
            if key in row.keys():
                payload[key] = row[key]
        return payload

    def transition_request(self, *, actor: SessionContext, request_id: str, to_status: str, reason: str) -> dict[str, Any]:
        reason_text = _required_text(reason, field="reason")
        if to_status not in _REQUEST_STATUSES:
            raise NexusError("NX-VAL-001", "invalid request status")
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT status, default_system_id FROM requests WHERE request_id = ?", (request_id,)).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "request not found")
                from_status = row["status"]
                if to_status not in _REQUEST_TRANSITIONS.get(from_status, set()):
                    raise NexusError("NX-PRECONDITION-003", "invalid request transition")
                # Strategists may only submit/cancel their own drafts via a limited scope; software agents use work-scoped transitions.
                if actor.role == "trading-strategist" and from_status == "draft":
                    self._require_scope(conn, actor=actor, scope="request.submit-draft", system_id=row["default_system_id"])
                elif self._has_scope(conn, actor=actor, scope="request.transition", system_id=row["default_system_id"]):
                    pass
                elif self._has_scope(conn, actor=actor, scope="work.transition", system_id="software-domain"):
                    pass
                elif from_status in {"accepted", "needs-planning"}:
                    self._require_scope(conn, actor=actor, scope="work.plan", system_id="software-domain")
                elif from_status in {"ready-to-build", "in-build", "review-failed"}:
                    self._require_scope(conn, actor=actor, scope="work.transition.build", system_id="software-domain")
                elif from_status in {"in-review", "state-update-needed"}:
                    self._require_scope(conn, actor=actor, scope="work.transition.review", system_id="software-domain")
                else:
                    self._require_scope(conn, actor=actor, scope="work.transition", system_id="software-domain")

                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    UPDATE requests
                    SET status = ?, last_reason = ?, last_actor_agent_id = ?, last_transition_at = ?, updated_at = ?
                    WHERE request_id = ?
                    """,
                    (to_status, reason_text, actor.agent_id, timestamp, timestamp, request_id),
                )
                event_id = _random_id("RS-2026-")
                conn.execute(
                    """
                    INSERT INTO request_status_events(
                        event_id, request_id, from_status, to_status, reason, actor_agent_id, actor_role, default_system_id, domain, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, request_id, from_status, to_status, reason_text, actor.agent_id, actor.role, actor.default_system_id, actor.domain, timestamp),
                )
                conn.commit()
                return {
                    "ok": True, "request_id": request_id, "from_status": from_status,
                    "to_status": to_status, "reason": reason_text, "event_id": event_id,
                    "agent_id": actor.agent_id, "default_system_id": actor.default_system_id, "timestamp": timestamp,
                }
            finally:
                conn.close()

    # ----- Repositories / Work / Reviews -----
    def list_repositories(self, *, actor: SessionContext, assigned_only: bool = False) -> dict[str, Any]:
        conn = self._connect()
        try:
            if assigned_only:
                self._require_scope(conn, actor=actor, scope="repos.read.assigned", system_id="software-domain")
                rows = conn.execute(
                    """
                    SELECT DISTINCT r.repo_id, r.name, r.url, r.system_id, r.owner_agent_id, r.status, r.default_branch,
                           r.allowed_agent_roles_json, r.github_owner, r.github_repo, r.github_default_branch,
                           r.github_installation_id, r.github_node_id, r.github_html_url, r.github_sync_enabled,
                           r.github_last_synced_at, r.created_at, r.updated_at
                    FROM repositories r
                    JOIN requests h ON h.target_repo_id = r.repo_id
                    WHERE h.assigned_agent_id = ?
                    ORDER BY r.repo_id
                    """,
                    (actor.agent_id,),
                ).fetchall()
            else:
                self._require_scope(conn, actor=actor, scope="repos.read", system_id="software-domain")
                rows = conn.execute(
                    """
                    SELECT repo_id, name, url, system_id, owner_agent_id, status, default_branch,
                           allowed_agent_roles_json, github_owner, github_repo, github_default_branch,
                           github_installation_id, github_node_id, github_html_url, github_sync_enabled,
                           github_last_synced_at, created_at, updated_at
                    FROM repositories ORDER BY repo_id
                    """
                ).fetchall()
            repositories = [self._repo_row_to_dict(row) for row in rows]
            if actor.role in {"sw-builder", "sw-reviewer"}:
                for repo in repositories:
                    repo.pop("system_id", None)
                    repo.pop("owner_agent_id", None)
                    repo.pop("allowed_agent_roles", None)
            return {"repositories": repositories}
        finally:
            conn.close()

    def show_repository(self, *, actor: SessionContext, repo_id: str) -> dict[str, Any]:
        repo_id = _required_text(repo_id, field="repo_id")
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT repo_id, name, url, system_id, owner_agent_id, status, default_branch,
                       allowed_agent_roles_json, github_owner, github_repo, github_default_branch,
                       github_installation_id, github_node_id, github_html_url, github_sync_enabled,
                       github_last_synced_at, created_at, updated_at
                FROM repositories WHERE repo_id = ?
                """,
                (repo_id,),
            ).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "repository not found")
            if not self._has_scope(conn, actor=actor, scope="repos.read", system_id="software-domain"):
                if not self._has_scope(conn, actor=actor, scope="repos.read.assigned", system_id="software-domain"):
                    raise NexusError("NX-PERM-001", "missing scope repos.read")
                assigned = conn.execute(
                    "SELECT 1 FROM requests WHERE target_repo_id = ? AND assigned_agent_id = ? LIMIT 1",
                    (repo_id, actor.agent_id),
                ).fetchone()
                if assigned is None:
                    raise NexusError("NX-PERM-001", "repository is outside assigned work")
            return self._repo_row_to_dict(row)
        finally:
            conn.close()

    @staticmethod
    def _repo_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "repo_id": row["repo_id"], "name": row["name"], "url": row["url"],
            "system_id": row["system_id"], "owner_agent_id": row["owner_agent_id"],
            "status": row["status"], "default_branch": row["default_branch"],
            "allowed_agent_roles": json.loads(row["allowed_agent_roles_json"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }
        for key in ("github_owner", "github_repo", "github_default_branch", "github_installation_id", "github_node_id", "github_html_url", "github_sync_enabled", "github_last_synced_at"):
            if key in row.keys():
                payload[key] = row[key]
        if "github_sync_enabled" in payload:
            payload["github_sync_enabled"] = bool(payload["github_sync_enabled"])
        return payload

    def list_work(self, *, actor: SessionContext, status_filter: str = "all", limit: int = 100) -> dict[str, Any]:
        conn = self._connect()
        try:
            full_read = self._has_scope(conn, actor=actor, scope="work.read", system_id="software-domain")
            assigned_read = self._has_scope(conn, actor=actor, scope="work.read.assigned", system_id="software-domain")
            if not full_read and not assigned_read:
                raise NexusError("NX-PERM-001", "missing scope work.read")
            clauses = ["target_system_id = 'software-domain'"]
            params: list[Any] = []
            if status_filter != "all":
                if status_filter not in _REQUEST_STATUSES:
                    raise NexusError("NX-VAL-001", "invalid work status")
                clauses.append("status = ?")
                params.append(status_filter)
            if not full_read:
                clauses.append("assigned_agent_id = ?")
                params.append(actor.agent_id)
            where = " AND ".join(clauses)
            rows = conn.execute(
                f"""
                SELECT request_id, status, priority, risk_class, objective, missing_capability,
                       target_repo_id, assigned_agent_id, branch, sanitized_summary,
                       implementation_context_json, implementation_context_approved_by,
                       implementation_context_approved_at, updated_at
                FROM requests
                WHERE {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            work_items = []
            for row in rows:
                item = self._work_row_to_summary(row, include_implementation_context=actor.role in {"sw-builder", "sw-reviewer"}, require_approved_context=actor.role in {"sw-builder", "sw-reviewer"})
                item["github"] = self._github_status_for_request(conn, request_id=row["request_id"], include_changed_files=actor.role in {"sw-reviewer", "sw-techlead", "nexus"})["github"]
                work_items.append(item)
            if actor.role in {"sw-builder", "sw-reviewer"}:
                for item in work_items:
                    if item.get("sanitized_summary"):
                        item["objective"] = item["sanitized_summary"]
                        item["task"] = item["sanitized_summary"]
            return {"work": work_items}
        finally:
            conn.close()

    def show_work(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        conn = self._connect()
        try:
            self._authorize_work_read(conn, actor=actor, request_id=request_id)
            row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "work item not found")
            if actor.role in {"sw-builder", "sw-reviewer"}:
                payload = {
                    "request_id": row["request_id"],
                    "status": row["status"],
                    "task": row["sanitized_summary"] or row["missing_capability"],
                    "objective": row["sanitized_summary"] or row["objective"],
                    "missing_capability": row["missing_capability"],
                    "acceptance_criteria": json.loads(row["acceptance_criteria_json"]),
                    "priority": row["priority"],
                    "risk_class": row["risk_class"],
                    "target_system_id": row["target_system_id"],
                    "target_repo_id": row["target_repo_id"],
                    "assigned_agent_id": row["assigned_agent_id"],
                    "branch": row["branch"],
                    "sanitized_summary": row["sanitized_summary"],
                    "implementation_context_approved_by": row["implementation_context_approved_by"],
                    "implementation_context_approved_at": row["implementation_context_approved_at"],
                    "updated_at": row["updated_at"],
                }
                context = self._implementation_context_from_row(row, require_approved=True)
                if context:
                    payload["implementation_context"] = context
            else:
                payload = self._request_row_to_dict(row)
                payload.update({
                    "source_system_id": row["source_system_id"],
                    "target_system_id": row["target_system_id"],
                    "target_repo_id": row["target_repo_id"],
                    "assigned_agent_id": row["assigned_agent_id"],
                    "branch": row["branch"],
                    "sanitized_summary": row["sanitized_summary"],
                    "implementation_context": self._implementation_context_from_row(row, require_approved=False) or {},
                    "implementation_context_updated_by": row["implementation_context_updated_by"],
                    "implementation_context_updated_at": row["implementation_context_updated_at"],
                    "implementation_context_approved_by": row["implementation_context_approved_by"],
                    "implementation_context_approved_at": row["implementation_context_approved_at"],
                })
            payload.update(self._github_status_for_request(conn, request_id=request_id, include_changed_files=True))
            reviews = conn.execute(
                "SELECT review_id, verdict, summary, reviewer_agent_id, created_at FROM work_reviews WHERE request_id = ? ORDER BY created_at DESC",
                (request_id,),
            ).fetchall()
            evidence = conn.execute(
                "SELECT evidence_id, kind, ref, summary, submitted_by_agent_id, created_at FROM work_evidence WHERE request_id = ? ORDER BY created_at DESC",
                (request_id,),
            ).fetchall()
            payload["reviews"] = [dict(item) for item in reviews]
            payload["evidence"] = [dict(item) for item in evidence]
            return payload
        finally:
            conn.close()

    def plan_work(
        self,
        *,
        actor: SessionContext,
        request_id: str,
        repo_id: str,
        branch: str | None = None,
        assigned_agent_id: str | None = None,
        sanitized_summary: str | None = None,
    ) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        repo_id = _required_text(repo_id, field="repo_id")
        branch_value = branch.strip() if isinstance(branch, str) and branch.strip() else f"feature/{request_id.lower()}"
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="work.plan", system_id="software-domain")
                row = conn.execute("SELECT status FROM requests WHERE request_id = ?", (request_id,)).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "work item not found")
                if conn.execute("SELECT 1 FROM repositories WHERE repo_id = ?", (repo_id,)).fetchone() is None:
                    raise NexusError("NX-NOTFOUND-001", "repository not found")
                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    UPDATE requests
                    SET target_system_id = 'software-domain', target_repo_id = ?, branch = ?,
                        assigned_agent_id = COALESCE(?, assigned_agent_id), sanitized_summary = COALESCE(?, sanitized_summary),
                        updated_at = ?
                    WHERE request_id = ?
                    """,
                    (repo_id, branch_value, assigned_agent_id, sanitized_summary, timestamp, request_id),
                )
                conn.commit()
                return self.show_work(actor=actor, request_id=request_id)
            finally:
                conn.close()

    def set_implementation_context(
        self,
        *,
        actor: SessionContext,
        request_id: str,
        implementation_context: dict[str, Any],
    ) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        normalized = _normalize_implementation_context(implementation_context)
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="work.implementation-context.set", system_id="software-domain")
                self._authorize_work_read(conn, actor=actor, request_id=request_id)
                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    UPDATE requests
                    SET implementation_context_json = ?, implementation_context_updated_by = ?,
                        implementation_context_updated_at = ?, implementation_context_approved_by = NULL,
                        implementation_context_approved_at = NULL, updated_at = ?
                    WHERE request_id = ?
                    """,
                    (json.dumps(normalized, ensure_ascii=True, sort_keys=True), actor.agent_id, timestamp, timestamp, request_id),
                )
                conn.commit()
                return self.show_work(actor=actor, request_id=request_id)
            finally:
                conn.close()

    def approve_work_plan(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="work.plan.approve", system_id="software-domain")
                self._authorize_work_read(conn, actor=actor, request_id=request_id)
                row = conn.execute(
                    """
                    SELECT target_repo_id, branch, sanitized_summary, implementation_context_json
                    FROM requests WHERE request_id = ?
                    """,
                    (request_id,),
                ).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "work item not found")
                if not row["target_repo_id"] or not row["branch"]:
                    raise NexusError("NX-PRECONDITION-001", "work plan requires target repo and branch before approval")
                try:
                    context = json.loads(row["implementation_context_json"] or "{}")
                except json.JSONDecodeError:
                    context = {}
                if not isinstance(context, dict) or not context:
                    raise NexusError("NX-PRECONDITION-001", "implementation context must be set before approval")
                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    UPDATE requests
                    SET implementation_context_approved_by = ?, implementation_context_approved_at = ?, updated_at = ?
                    WHERE request_id = ?
                    """,
                    (actor.agent_id, timestamp, timestamp, request_id),
                )
                conn.commit()
                return self.show_work(actor=actor, request_id=request_id)
            finally:
                conn.close()

    def assign_work(self, *, actor: SessionContext, request_id: str, agent_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        agent_id = _required_text(agent_id, field="agent_id")
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="work.assign", system_id="software-domain")
                if conn.execute("SELECT 1 FROM requests WHERE request_id = ?", (request_id,)).fetchone() is None:
                    raise NexusError("NX-NOTFOUND-001", "work item not found")
                if conn.execute("SELECT 1 FROM agent_registry WHERE agent_id = ? AND active = 1", (agent_id,)).fetchone() is None:
                    raise NexusError("NX-NOTFOUND-001", "agent not found")
                timestamp = _iso(_utc_now())
                conn.execute("UPDATE requests SET assigned_agent_id = ?, updated_at = ? WHERE request_id = ?", (agent_id, timestamp, request_id))
                conn.commit()
                return self.show_work(actor=actor, request_id=request_id)
            finally:
                conn.close()

    # ----- GitHub Adapter -----
    def create_github_issue(
        self,
        *,
        actor: SessionContext,
        request_id: str,
        title: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        labels = labels or []
        assignees = assignees or []
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="github.issue.create", system_id="software-domain")
                self._require_scope(conn, actor=actor, scope="work.read", system_id="software-domain")
                request_row = self._load_work_request(conn, request_id=request_id)
                repo_row = self._load_request_repo(conn, request_row)
                if not request_row["target_repo_id"] or not request_row["branch"]:
                    raise NexusError("NX-PRECONDITION-001", "GitHub issue requires target repo and branch")
                if not request_row["implementation_context_approved_at"]:
                    raise NexusError("NX-PRECONDITION-001", "GitHub issue requires approved implementation context")
                context = self._implementation_context_from_row(request_row, require_approved=True) or {}
                request_payload = self._work_request_to_dict(request_row)
                repo_payload = self._repo_row_to_dict(repo_row)
                body = render_issue_body(request=request_payload, repo=repo_payload, implementation_context=context)
                issue_title = title.strip() if isinstance(title, str) and title.strip() else (request_row["sanitized_summary"] or request_row["objective"])
                if dry_run:
                    return {"ok": True, "request_id": request_id, "dry_run": True, "title": issue_title, "body": body, "labels": labels, "assignees": assignees}
                existing = conn.execute("SELECT 1 FROM github_issues WHERE request_id = ?", (request_id,)).fetchone()
                if existing:
                    raise NexusError("NX-PRECONDITION-003", "GitHub issue already exists for request")
                gh_repo = self._github_repo_from_row(repo_row)
                issue = self._github_client_or_default().create_issue(gh_repo.owner, gh_repo.repo, issue_title, body, labels, assignees)
                timestamp = _iso(_utc_now())
                self._upsert_github_issue(conn, request_id=request_id, repo_id=repo_row["repo_id"], owner=gh_repo.owner, repo=gh_repo.repo, issue=issue, timestamp=timestamp)
                self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_issue", ref=issue.get("html_url"), summary=f"GitHub issue #{issue.get('number')} created")
                conn.commit()
                return {"ok": True, "request_id": request_id, "issue": self._github_issue_payload_from_dict(issue), "body": body}
            finally:
                conn.close()

    def sync_github_issue(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="github.issue.sync", system_id="software-domain")
                self._authorize_work_read(conn, actor=actor, request_id=request_id)
                row = conn.execute("SELECT * FROM github_issues WHERE request_id = ?", (request_id,)).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "GitHub issue link not found")
                issue = self._github_client_or_default().get_issue(row["github_owner"], row["github_repo"], int(row["issue_number"]))
                timestamp = _iso(_utc_now())
                self._upsert_github_issue(conn, request_id=request_id, repo_id=row["repo_id"], owner=row["github_owner"], repo=row["github_repo"], issue=issue, timestamp=timestamp)
                self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_issue_sync", ref=issue.get("html_url"), summary=f"GitHub issue #{issue.get('number')} synced")
                conn.commit()
                return self.github_status(actor=actor, request_id=request_id)
            finally:
                conn.close()

    def link_github_pr(self, *, actor: SessionContext, request_id: str, url: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        url = _required_text(url, field="url")
        with self._lock:
            conn = self._connect()
            try:
                self._require_github_assigned_or_full(conn, actor=actor, request_id=request_id, full_scope="github.pr.link", assigned_scope="github.pr.link.assigned")
                request_row = self._load_work_request(conn, request_id=request_id)
                repo_row = self._load_request_repo(conn, request_row)
                ref = parse_github_pr_url(url)
                gh_repo = self._github_repo_from_row(repo_row)
                assert_repo_matches(ref, gh_repo)
                pr = self._github_client_or_default().get_pull_request(ref.owner, ref.repo, ref.number)
                timestamp = _iso(_utc_now())
                self._upsert_github_pr(conn, request_id=request_id, repo_id=repo_row["repo_id"], owner=ref.owner, repo=ref.repo, pr=pr, timestamp=timestamp, review_state="unknown", checks_state="unknown", policy_state="unknown", changed_files=[], commits=[])
                self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_pr_linked", ref=pr.get("html_url") or url, summary=f"GitHub PR #{ref.number} linked")
                conn.commit()
            finally:
                conn.close()
        synced = self.sync_github_pr(actor=actor, request_id=request_id)
        return synced

    def sync_github_pr(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        with self._lock:
            conn = self._connect()
            try:
                self._require_github_assigned_or_full(conn, actor=actor, request_id=request_id, full_scope="github.pr.sync", assigned_scope="github.pr.sync.assigned")
                request_row = self._load_work_request(conn, request_id=request_id)
                pr_row = conn.execute("SELECT * FROM github_pull_requests WHERE request_id = ?", (request_id,)).fetchone()
                if pr_row is None:
                    raise NexusError("NX-NOTFOUND-001", "GitHub PR link not found")
                owner, repo, number = pr_row["github_owner"], pr_row["github_repo"], int(pr_row["pr_number"])
                client = self._github_client_or_default()
                pr = client.get_pull_request(owner, repo, number)
                head_sha = ((pr.get("head") or {}).get("sha") or pr.get("head_sha") or pr_row["head_sha"] or "")
                files = client.list_pull_request_files(owner, repo, number)
                reviews = client.list_pull_request_reviews(owner, repo, number)
                commits = client.list_pull_request_commits(owner, repo, number)
                combined_status = client.get_combined_status(owner, repo, head_sha) if head_sha else {}
                check_runs = client.list_check_runs_for_ref(owner, repo, head_sha) if head_sha else {}
                review_state = derive_review_state(reviews)
                checks_state = derive_checks_state(check_runs, combined_status)
                changed_files = [item.get("filename") for item in files if item.get("filename")]
                context = self._implementation_context_from_row(request_row, require_approved=False) or {}
                policy = evaluate_changed_files_policy(changed_files, context.get("do_not_touch") or [])
                commit_payload = [
                    {"sha": item.get("sha"), "html_url": item.get("html_url")} for item in commits
                ]
                timestamp = _iso(_utc_now())
                self._upsert_github_pr(conn, request_id=request_id, repo_id=pr_row["repo_id"], owner=owner, repo=repo, pr=pr, timestamp=timestamp, review_state=review_state, checks_state=checks_state, policy_state=policy["policy_state"], changed_files=changed_files, commits=commit_payload)
                self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_pr_sync", ref=pr.get("html_url"), summary=f"GitHub PR #{number} synced")
                self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_reviews", ref=pr.get("html_url"), summary=f"GitHub review state: {review_state}")
                self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_checks", ref=pr.get("html_url"), summary=f"GitHub checks state: {checks_state}")
                if policy["policy_state"] == "violated":
                    self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_policy_violation", ref=pr.get("html_url"), summary="Do-not-touch policy violated: " + ", ".join(policy["violations"]))
                conn.commit()
                return self._github_status_for_request(conn, request_id=request_id, include_changed_files=True)
            finally:
                conn.close()

    def github_status(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        conn = self._connect()
        try:
            self._require_github_assigned_or_full(conn, actor=actor, request_id=request_id, full_scope="github.status.read", assigned_scope="github.status.read.assigned")
            return self._github_status_for_request(conn, request_id=request_id, include_changed_files=True)
        finally:
            conn.close()

    def sync_github(self, *, actor: SessionContext, request_id: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        issue_exists = False
        pr_exists = False
        conn = self._connect()
        try:
            issue_exists = conn.execute("SELECT 1 FROM github_issues WHERE request_id = ?", (request_id,)).fetchone() is not None
            pr_exists = conn.execute("SELECT 1 FROM github_pull_requests WHERE request_id = ?", (request_id,)).fetchone() is not None
        finally:
            conn.close()
        if issue_exists:
            self.sync_github_issue(actor=actor, request_id=request_id)
        if pr_exists:
            self.sync_github_pr(actor=actor, request_id=request_id)
        conn = self._connect()
        try:
            self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_sync", ref=None, summary="GitHub issue/PR sync completed")
            conn.commit()
        finally:
            conn.close()
        return self.github_status(actor=actor, request_id=request_id)

    def record_github_event(self, *, delivery_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        delivery_id = _required_text(delivery_id, field="delivery_id")
        event_type = _required_text(event_type, field="event_type")
        action = payload.get("action") if isinstance(payload.get("action"), str) else None
        repository = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
        owner = ((repository.get("owner") or {}) if isinstance(repository.get("owner"), dict) else {}).get("login")
        repo = repository.get("name")
        timestamp = _iso(_utc_now())
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute("SELECT * FROM github_events WHERE delivery_id = ?", (delivery_id,)).fetchone()
                if existing:
                    return {"ok": True, "event_id": existing["event_id"], "delivery_id": delivery_id, "processing_status": existing["processing_status"], "duplicate": True}
                request_id = None
                repo_id = None
                if owner and repo:
                    repo_row = conn.execute("SELECT repo_id FROM repositories WHERE github_owner = ? AND github_repo = ?", (owner, repo)).fetchone()
                    repo_id = repo_row["repo_id"] if repo_row else None
                    issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else None
                    pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else None
                    number = (pr or issue or {}).get("number") if (pr or issue) else None
                    if isinstance(number, int):
                        table = "github_pull_requests" if pr else "github_issues"
                        column = "pr_number" if pr else "issue_number"
                        linked = conn.execute(f"SELECT request_id FROM {table} WHERE github_owner = ? AND github_repo = ? AND {column} = ?", (owner, repo, number)).fetchone()
                        request_id = linked["request_id"] if linked else None
                event_id = _random_id("GH-EVT-2026-")
                conn.execute(
                    """
                    INSERT INTO github_events(event_id, delivery_id, event_type, action, request_id, repo_id, github_owner, github_repo, payload_json, received_at, processing_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received')
                    """,
                    (event_id, delivery_id, event_type, action, request_id, repo_id, owner, repo, json.dumps(payload, ensure_ascii=True, sort_keys=True), timestamp),
                )
                if request_id:
                    actor = SessionContext(session_id="webhook", agent_id="github-webhook", role="nexus", default_system_id="software-domain", domain="Software")
                    self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="github_webhook", ref=None, summary=f"GitHub webhook received: {event_type}/{action or 'unknown'}")
                conn.commit()
                return {"ok": True, "event_id": event_id, "delivery_id": delivery_id, "event_type": event_type, "request_id": request_id, "repo_id": repo_id, "processing_status": "received"}
            finally:
                conn.close()

    def list_github_repositories(self, *, actor: SessionContext) -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="github.repos.read", system_id="software-domain")
            rows = conn.execute(
                """
                SELECT repo_id, name, github_owner, github_repo, github_default_branch, github_html_url,
                       github_sync_enabled, github_last_synced_at
                FROM repositories
                WHERE github_owner IS NOT NULL AND github_repo IS NOT NULL
                ORDER BY repo_id
                """
            ).fetchall()
            return {"repositories": [dict(row) | {"github_sync_enabled": bool(row["github_sync_enabled"])} for row in rows]}
        finally:
            conn.close()

    def sync_github_repositories(self, *, actor: SessionContext) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="github.repos.sync", system_id="software-domain")
                rows = conn.execute("SELECT * FROM repositories WHERE github_owner IS NOT NULL AND github_repo IS NOT NULL AND github_sync_enabled = 1").fetchall()
                synced: list[dict[str, Any]] = []
                timestamp = _iso(_utc_now())
                for row in rows:
                    repo_data = self._github_client_or_default().get_repo(row["github_owner"], row["github_repo"])
                    conn.execute(
                        """
                        UPDATE repositories
                        SET github_default_branch = COALESCE(?, github_default_branch), github_node_id = COALESCE(?, github_node_id),
                            github_html_url = COALESCE(?, github_html_url), github_last_synced_at = ?, updated_at = ?
                        WHERE repo_id = ?
                        """,
                        (repo_data.get("default_branch"), repo_data.get("node_id"), repo_data.get("html_url"), timestamp, timestamp, row["repo_id"]),
                    )
                    synced.append({"repo_id": row["repo_id"], "github_owner": row["github_owner"], "github_repo": row["github_repo"]})
                conn.commit()
                return {"ok": True, "repositories": synced, "timestamp": timestamp}
            finally:
                conn.close()

    def submit_work_evidence(self, *, actor: SessionContext, request_id: str, kind: str, ref: str | None, summary: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        kind = _required_text(kind, field="kind")
        summary = _required_text(summary, field="summary")
        with self._lock:
            conn = self._connect()
            try:
                if not self._has_scope(conn, actor=actor, scope="work.evidence.create", system_id="software-domain") and not self._has_scope(conn, actor=actor, scope="work.transition", system_id="software-domain"):
                    raise NexusError("NX-PERM-001", "missing scope work.evidence.create")
                self._authorize_work_read(conn, actor=actor, request_id=request_id)
                evidence_id = _random_id("WEV-2026-")
                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    INSERT INTO work_evidence(evidence_id, request_id, kind, ref, summary, submitted_by_agent_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (evidence_id, request_id, kind, ref, summary, actor.agent_id, timestamp),
                )
                conn.commit()
                return {"ok": True, "evidence_id": evidence_id, "request_id": request_id, "kind": kind, "ref": ref, "summary": summary, "timestamp": timestamp}
            finally:
                conn.close()

    def submit_review(self, *, actor: SessionContext, request_id: str, verdict: str, summary: str) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        verdict = _required_text(verdict, field="verdict")
        summary = _required_text(summary, field="summary")
        if verdict not in _REVIEW_VERDICTS:
            raise NexusError("NX-VAL-001", "invalid review verdict")
        with self._lock:
            conn = self._connect()
            try:
                self._require_scope(conn, actor=actor, scope="reviews.submit", system_id="software-domain")
                self._authorize_work_read(conn, actor=actor, request_id=request_id)
                review_id = _random_id("REV-2026-")
                timestamp = _iso(_utc_now())
                conn.execute(
                    """
                    INSERT INTO work_reviews(review_id, request_id, verdict, summary, reviewer_agent_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (review_id, request_id, verdict, summary, actor.agent_id, timestamp),
                )
                conn.commit()
                return {"ok": True, "review_id": review_id, "request_id": request_id, "verdict": verdict, "summary": summary, "timestamp": timestamp}
            finally:
                conn.close()

    def list_reviews(self, *, actor: SessionContext, status_filter: str = "in-review", limit: int = 100) -> dict[str, Any]:
        conn = self._connect()
        try:
            self._require_scope(conn, actor=actor, scope="reviews.read", system_id="software-domain")
            work = self.list_work(actor=actor, status_filter=status_filter, limit=limit).get("work", [])
            return {"reviews": work}
        finally:
            conn.close()

    def transition_work(self, *, actor: SessionContext, request_id: str, to_status: str, reason: str, override: bool = False) -> dict[str, Any]:
        request_id = _required_text(request_id, field="request_id")
        reason_text = _required_text(reason, field="reason")
        if override:
            if actor.role not in {"sw-techlead", "nexus"}:
                raise NexusError("NX-PERM-001", "manual override requires sw-techlead or nexus")
            with self._lock:
                conn = self._connect()
                try:
                    self._require_scope(conn, actor=actor, scope="github.policy.override", system_id="software-domain")
                    row = conn.execute("SELECT status FROM requests WHERE request_id = ?", (request_id,)).fetchone()
                    if row is None:
                        raise NexusError("NX-NOTFOUND-001", "work item not found")
                    from_status = row["status"]
                    if to_status not in _REQUEST_STATUSES:
                        raise NexusError("NX-VAL-001", "invalid request status")
                    timestamp = _iso(_utc_now())
                    conn.execute(
                        "UPDATE requests SET status = ?, last_reason = ?, last_actor_agent_id = ?, last_transition_at = ?, updated_at = ? WHERE request_id = ?",
                        (to_status, reason_text, actor.agent_id, timestamp, timestamp, request_id),
                    )
                    event_id = _random_id("RS-2026-")
                    conn.execute(
                        """
                        INSERT INTO request_status_events(event_id, request_id, from_status, to_status, reason, actor_agent_id, actor_role, default_system_id, domain, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (event_id, request_id, from_status, to_status, reason_text, actor.agent_id, actor.role, actor.default_system_id, actor.domain, timestamp),
                    )
                    self._insert_work_evidence(conn, actor=actor, request_id=request_id, kind="manual_override", ref=None, summary=reason_text)
                    conn.commit()
                    return {"ok": True, "request_id": request_id, "from_status": from_status, "to_status": to_status, "reason": reason_text, "event_id": event_id, "override": True, "timestamp": timestamp}
                finally:
                    conn.close()

        conn = self._connect()
        try:
            self._authorize_work_read(conn, actor=actor, request_id=request_id)
            row = conn.execute("SELECT target_repo_id, branch, implementation_context_approved_at FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise NexusError("NX-NOTFOUND-001", "work item not found")
            if to_status == "ready-to-build":
                if not row["target_repo_id"] or not row["branch"] or not row["implementation_context_approved_at"]:
                    raise NexusError("NX-PRECONDITION-001", "ready-to-build requires target repo, branch and approved implementation context")
            if to_status == "in-review":
                if not row["implementation_context_approved_at"]:
                    raise NexusError("NX-PRECONDITION-001", "in-review requires approved implementation context")
                if conn.execute("SELECT 1 FROM github_pull_requests WHERE request_id = ?", (request_id,)).fetchone() is None:
                    raise NexusError("NX-PRECONDITION-001", "in-review requires linked GitHub PR")
            if to_status == "approved":
                pr = conn.execute("SELECT review_state, checks_state, policy_state FROM github_pull_requests WHERE request_id = ?", (request_id,)).fetchone()
                if pr is None:
                    raise NexusError("NX-PRECONDITION-001", "approved requires linked GitHub PR")
                if pr["review_state"] != "approved":
                    raise NexusError("NX-PRECONDITION-001", "approved requires GitHub review approval")
                if pr["checks_state"] != "passing":
                    raise NexusError("NX-PRECONDITION-001", "approved requires passing GitHub checks")
                if pr["policy_state"] != "ok":
                    raise NexusError("NX-PRECONDITION-001", "approved requires clean do-not-touch policy")
            if to_status == "done":
                pr = conn.execute("SELECT merged, merge_commit_sha, policy_state FROM github_pull_requests WHERE request_id = ?", (request_id,)).fetchone()
                if pr is None:
                    raise NexusError("NX-PRECONDITION-001", "done requires linked GitHub PR")
                if not pr["merged"] or not pr["merge_commit_sha"]:
                    raise NexusError("NX-PRECONDITION-001", "done requires merged GitHub PR")
                kinds = {item["kind"] for item in conn.execute("SELECT kind FROM work_evidence WHERE request_id = ?", (request_id,)).fetchall()}
                if "github_reviews" not in kinds:
                    raise NexusError("NX-PRECONDITION-001", "done requires GitHub review evidence")
                if "github_checks" not in kinds:
                    raise NexusError("NX-PRECONDITION-001", "done requires GitHub checks evidence")
                if pr["policy_state"] != "ok":
                    raise NexusError("NX-PRECONDITION-001", "done requires clean do-not-touch policy")
        finally:
            conn.close()
        return self.transition_request(actor=actor, request_id=request_id, to_status=to_status, reason=reason_text)

    def _authorize_work_read(self, conn: sqlite3.Connection, *, actor: SessionContext, request_id: str) -> None:
        row = conn.execute("SELECT assigned_agent_id, target_system_id FROM requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise NexusError("NX-NOTFOUND-001", "work item not found")
        if self._has_scope(conn, actor=actor, scope="work.read", system_id="software-domain"):
            return
        if self._has_scope(conn, actor=actor, scope="work.read.assigned", system_id="software-domain") and row["assigned_agent_id"] == actor.agent_id:
            return
        raise NexusError("NX-PERM-001", "work item is outside actor scope")

    def _insert_work_evidence(self, conn: sqlite3.Connection, *, actor: SessionContext, request_id: str, kind: str, ref: str | None, summary: str) -> str:
        evidence_id = _random_id("WEV-2026-")
        timestamp = _iso(_utc_now())
        conn.execute(
            """
            INSERT INTO work_evidence(evidence_id, request_id, kind, ref, summary, submitted_by_agent_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (evidence_id, request_id, kind, ref, summary, actor.agent_id, timestamp),
        )
        return evidence_id

    def _load_work_request(self, conn: sqlite3.Connection, *, request_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:
            raise NexusError("NX-NOTFOUND-001", "work item not found")
        if row["target_system_id"] != "software-domain":
            raise NexusError("NX-PRECONDITION-001", "request is not routed to software work")
        return row

    def _load_request_repo(self, conn: sqlite3.Connection, request_row: sqlite3.Row) -> sqlite3.Row:
        repo_id = request_row["target_repo_id"]
        if not repo_id:
            raise NexusError("NX-PRECONDITION-001", "request has no target repo")
        row = conn.execute("SELECT * FROM repositories WHERE repo_id = ?", (repo_id,)).fetchone()
        if row is None:
            raise NexusError("NX-NOTFOUND-001", "repository not found")
        if not row["github_owner"] or not row["github_repo"]:
            raise NexusError("NX-PRECONDITION-001", "repository has no GitHub mapping")
        return row

    @staticmethod
    def _work_request_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "request_id": row["request_id"],
            "objective": row["objective"],
            "task": row["sanitized_summary"] or row["objective"],
            "sanitized_summary": row["sanitized_summary"],
            "acceptance_criteria": json.loads(row["acceptance_criteria_json"]),
            "target_repo_id": row["target_repo_id"],
            "branch": row["branch"],
        }

    @staticmethod
    def _github_repo_from_row(row: sqlite3.Row) -> GitHubRepository:
        return GitHubRepository(
            repo_id=row["repo_id"],
            owner=row["github_owner"],
            repo=row["github_repo"],
            default_branch=row["github_default_branch"],
            installation_id=row["github_installation_id"],
            node_id=row["github_node_id"],
            html_url=row["github_html_url"],
        )

    def _require_github_assigned_or_full(self, conn: sqlite3.Connection, *, actor: SessionContext, request_id: str, full_scope: str, assigned_scope: str) -> None:
        if self._has_scope(conn, actor=actor, scope=full_scope, system_id="software-domain"):
            return
        if self._has_scope(conn, actor=actor, scope=assigned_scope, system_id="software-domain"):
            self._authorize_work_read(conn, actor=actor, request_id=request_id)
            return
        raise NexusError("NX-PERM-001", f"missing scope {full_scope}")

    def _upsert_github_issue(self, conn: sqlite3.Connection, *, request_id: str, repo_id: str, owner: str, repo: str, issue: dict[str, Any], timestamp: str) -> None:
        labels = [item.get("name") for item in issue.get("labels", []) if isinstance(item, dict) and item.get("name")]
        assignees = [item.get("login") for item in issue.get("assignees", []) if isinstance(item, dict) and item.get("login")]
        conn.execute(
            """
            INSERT INTO github_issues(
                request_id, repo_id, github_owner, github_repo, issue_number, issue_node_id, title, state,
                html_url, api_url, labels_json, assignees_json, created_at, updated_at, closed_at, last_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                repo_id=excluded.repo_id, github_owner=excluded.github_owner, github_repo=excluded.github_repo,
                issue_number=excluded.issue_number, issue_node_id=excluded.issue_node_id, title=excluded.title,
                state=excluded.state, html_url=excluded.html_url, api_url=excluded.api_url,
                labels_json=excluded.labels_json, assignees_json=excluded.assignees_json,
                created_at=excluded.created_at, updated_at=excluded.updated_at, closed_at=excluded.closed_at,
                last_synced_at=excluded.last_synced_at
            """,
            (
                request_id, repo_id, owner, repo, int(issue["number"]), issue.get("node_id"), issue.get("title") or "",
                issue.get("state") or "unknown", issue.get("html_url") or "", issue.get("url"),
                json.dumps(labels, ensure_ascii=True), json.dumps(assignees, ensure_ascii=True),
                issue.get("created_at") or timestamp, issue.get("updated_at") or timestamp, issue.get("closed_at"), timestamp,
            ),
        )

    def _upsert_github_pr(
        self,
        conn: sqlite3.Connection,
        *,
        request_id: str,
        repo_id: str,
        owner: str,
        repo: str,
        pr: dict[str, Any],
        timestamp: str,
        review_state: str,
        checks_state: str,
        policy_state: str,
        changed_files: list[str],
        commits: list[dict[str, Any]],
    ) -> None:
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        conn.execute(
            """
            INSERT INTO github_pull_requests(
                request_id, repo_id, github_owner, github_repo, pr_number, pr_node_id, title, state, draft, merged,
                merge_commit_sha, head_ref, head_sha, base_ref, html_url, api_url, review_state, checks_state,
                policy_state, changed_files_json, commits_json, created_at, updated_at, merged_at, last_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                repo_id=excluded.repo_id, github_owner=excluded.github_owner, github_repo=excluded.github_repo,
                pr_number=excluded.pr_number, pr_node_id=excluded.pr_node_id, title=excluded.title,
                state=excluded.state, draft=excluded.draft, merged=excluded.merged, merge_commit_sha=excluded.merge_commit_sha,
                head_ref=excluded.head_ref, head_sha=excluded.head_sha, base_ref=excluded.base_ref,
                html_url=excluded.html_url, api_url=excluded.api_url, review_state=excluded.review_state,
                checks_state=excluded.checks_state, policy_state=excluded.policy_state,
                changed_files_json=excluded.changed_files_json, commits_json=excluded.commits_json,
                created_at=excluded.created_at, updated_at=excluded.updated_at, merged_at=excluded.merged_at,
                last_synced_at=excluded.last_synced_at
            """,
            (
                request_id, repo_id, owner, repo, int(pr["number"]), pr.get("node_id"), pr.get("title") or "",
                pr.get("state") or "unknown", 1 if pr.get("draft") else 0, 1 if pr.get("merged") else 0,
                pr.get("merge_commit_sha"), head.get("ref") or pr.get("head_ref"), head.get("sha") or pr.get("head_sha"),
                base.get("ref") or pr.get("base_ref"), pr.get("html_url") or "", pr.get("url"),
                review_state, checks_state, policy_state, json.dumps(changed_files, ensure_ascii=True),
                json.dumps(commits, ensure_ascii=True), pr.get("created_at") or timestamp, pr.get("updated_at") or timestamp,
                pr.get("merged_at"), timestamp,
            ),
        )

    @staticmethod
    def _github_issue_payload_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "number": row["issue_number"],
            "state": row["state"],
            "url": row["html_url"],
        }

    @staticmethod
    def _github_issue_payload_from_dict(issue: dict[str, Any]) -> dict[str, Any]:
        return {"number": issue.get("number"), "state": issue.get("state"), "url": issue.get("html_url")}

    @staticmethod
    def _github_pr_payload_from_row(row: sqlite3.Row, *, include_changed_files: bool) -> dict[str, Any]:
        payload = {
            "number": row["pr_number"],
            "state": row["state"],
            "draft": bool(row["draft"]),
            "merged": bool(row["merged"]),
            "review_state": row["review_state"],
            "checks_state": row["checks_state"],
            "policy_state": row["policy_state"],
            "url": row["html_url"],
        }
        if include_changed_files:
            payload["changed_files"] = json.loads(row["changed_files_json"] or "[]")
        return payload

    def _github_status_for_request(self, conn: sqlite3.Connection, *, request_id: str, include_changed_files: bool) -> dict[str, Any]:
        issue = conn.execute("SELECT * FROM github_issues WHERE request_id = ?", (request_id,)).fetchone()
        pr = conn.execute("SELECT * FROM github_pull_requests WHERE request_id = ?", (request_id,)).fetchone()
        return {
            "request_id": request_id,
            "github": {
                "issue": self._github_issue_payload_from_row(issue) if issue else None,
                "pull_request": self._github_pr_payload_from_row(pr, include_changed_files=include_changed_files) if pr else None,
            },
        }

    @staticmethod
    def _implementation_context_from_row(row: sqlite3.Row, *, require_approved: bool) -> dict[str, Any] | None:
        if require_approved and not row["implementation_context_approved_at"]:
            return None
        raw = row["implementation_context_json"] if "implementation_context_json" in row.keys() else "{}"
        try:
            context = json.loads(raw or "{}")
        except json.JSONDecodeError:
            context = {}
        return context if isinstance(context, dict) and context else None

    @staticmethod
    def _work_row_to_summary(row: sqlite3.Row, *, include_implementation_context: bool = False, require_approved_context: bool = False) -> dict[str, Any]:
        item = {
            "request_id": row["request_id"], "status": row["status"], "priority": row["priority"],
            "risk_class": row["risk_class"], "objective": row["objective"],
            "task": row["objective"], "missing_capability": row["missing_capability"], "target_repo_id": row["target_repo_id"],
            "assigned_agent_id": row["assigned_agent_id"], "branch": row["branch"],
            "sanitized_summary": row["sanitized_summary"],
            "implementation_context_approved_by": row["implementation_context_approved_by"] if "implementation_context_approved_by" in row.keys() else None,
            "implementation_context_approved_at": row["implementation_context_approved_at"] if "implementation_context_approved_at" in row.keys() else None,
            "updated_at": row["updated_at"],
        }
        if include_implementation_context:
            context = Storage._implementation_context_from_row(row, require_approved=require_approved_context)
            if context:
                item["implementation_context"] = context
        return item

    def get_context(self, *, actor: SessionContext, request_limit: int = 20) -> dict[str, Any]:
        conn = self._connect()
        try:
            scopes = self._effective_scopes(conn, agent_id=actor.agent_id, role=actor.role)
            allowed_actions = sorted({item["scope"] for item in scopes})
            payload: dict[str, Any] = {
                "ok": True,
                "agent": {
                    "agent_id": actor.agent_id,
                    "role": actor.role,
                    "default_system_id": actor.default_system_id,
                    "default_system_id": actor.default_system_id,
                    "domain": actor.domain,
                },
                "allowed_actions": allowed_actions,
            }

            def add_domain_context() -> None:
                readable_systems = self._readable_systems(conn, actor=actor, scope="systems.read")
                system_filter = None if readable_systems is None else sorted(readable_systems)
                payload["systems"] = self._query_systems_for_context(conn, system_ids=system_filter)
                if self._has_any_system_scope(conn, actor=actor, scope="goals.read"):
                    payload["goals"] = self._query_goals(conn, actor=actor, system_id=None, status_filter="all", limit=20)
                if self._has_any_system_scope(conn, actor=actor, scope="capabilities.read"):
                    readable_capability_systems = self._readable_systems(conn, actor=actor, scope="capabilities.read")
                    if readable_capability_systems is None:
                        payload["capabilities"] = self._query_capabilities(conn, status_filter="all", system_ids=None)
                    else:
                        caps: list[dict[str, Any]] = []
                        for item_system_id in sorted(readable_capability_systems):
                            caps.extend(self._query_capabilities(conn, status_filter="all", system_ids=[item_system_id]))
                        payload["capabilities"] = caps
                if self._has_any_system_scope(conn, actor=actor, scope="runtime_tools.read"):
                    payload["runtime_tools"] = self._query_runtime_tools(conn, actor=actor, system_id=None, status_filter="all")
                if self._has_any_system_scope(conn, actor=actor, scope="request.read"):
                    payload["requests"] = self._query_relevant_requests(conn, actor=actor, limit=request_limit)

            if actor.role == "sw-builder":
                payload["assigned_work"] = self.list_work(actor=actor, status_filter="all", limit=request_limit).get("work", [])
                payload["assigned_repositories"] = self.list_repositories(actor=actor, assigned_only=True).get("repositories", [])
                return payload

            if actor.role == "sw-reviewer":
                payload["assigned_reviews"] = self.list_work(actor=actor, status_filter="all", limit=request_limit).get("work", [])
                payload["assigned_repositories"] = self.list_repositories(actor=actor, assigned_only=True).get("repositories", [])
                return payload

            if actor.role in {"sw-architect", "sw-techlead"}:
                readable_systems = self._readable_systems(conn, actor=actor, scope="systems.read")
                system_filter = None if readable_systems is None else sorted(readable_systems)
                payload["systems"] = self._query_systems_for_context(conn, system_ids=system_filter)
                if self._has_any_system_scope(conn, actor=actor, scope="goals.read"):
                    payload["goals"] = self._query_goals(conn, actor=actor, system_id=None, status_filter="all", limit=20)
                if self._has_any_system_scope(conn, actor=actor, scope="capabilities.read"):
                    payload["capabilities"] = self._query_capabilities(conn, status_filter="all", system_ids=["software-domain"])
                if self._has_any_system_scope(conn, actor=actor, scope="runtime_tools.read"):
                    payload["runtime_tools"] = self._query_runtime_tools(conn, actor=actor, system_id="software-domain", status_filter="all")
                if self._has_scope(conn, actor=actor, scope="work.read", system_id="software-domain"):
                    payload["work"] = self.list_work(actor=actor, status_filter="all", limit=request_limit).get("work", [])
                if self._has_scope(conn, actor=actor, scope="repos.read", system_id="software-domain"):
                    payload["repositories"] = self.list_repositories(actor=actor, assigned_only=False).get("repositories", [])
                if self._has_scope(conn, actor=actor, scope="reviews.read", system_id="software-domain"):
                    payload["reviews"] = self.list_reviews(actor=actor, status_filter="all", limit=request_limit).get("reviews", [])
                return payload

            add_domain_context()
            if actor.role in {"nexus", "main"}:
                payload["effective_scopes"] = scopes
                if self._has_scope(conn, actor=actor, scope="work.read", system_id="software-domain"):
                    payload["work"] = self.list_work(actor=actor, status_filter="all", limit=request_limit).get("work", [])
                if self._has_scope(conn, actor=actor, scope="repos.read", system_id="software-domain"):
                    payload["repositories"] = self.list_repositories(actor=actor, assigned_only=False).get("repositories", [])
                if self._has_scope(conn, actor=actor, scope="reviews.read", system_id="software-domain"):
                    payload["reviews"] = self.list_reviews(actor=actor, status_filter="all", limit=request_limit).get("reviews", [])
            return payload
        finally:
            conn.close()

    def _has_any_system_scope(self, conn: sqlite3.Connection, *, actor: SessionContext, scope: str) -> bool:
        systems = self._readable_systems(conn, actor=actor, scope=scope)
        return systems is None or bool(systems)

    def _query_systems_for_context(self, conn: sqlite3.Connection, *, system_ids: list[str] | None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if system_ids is not None:
            if not system_ids:
                return []
            clauses.append("system_id IN ({})".format(", ".join("?" for _ in system_ids)))
            params.extend(system_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT system_id, name, purpose, owner_agent_id, status, risk_level, created_at, updated_at
            FROM systems {where} ORDER BY system_id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _query_relevant_requests(conn: sqlite3.Connection, *, actor: SessionContext, limit: int) -> list[dict[str, Any]]:
        open_statuses = set(_OPEN_REQUEST_STATUSES)
        if actor.role not in {"trading-strategist", "trading-sentinel"}:
            open_statuses.discard("draft")
        sorted_statuses = sorted(open_statuses)
        clauses = ["status IN ({})".format(", ".join("?" for _ in sorted_statuses))]
        params: list[Any] = list(sorted_statuses)
        if actor.role == "nexus":
            pass
        elif actor.role.startswith("trading-"):
            clauses.append("submitted_by_agent_id = ?")
            params.append(actor.agent_id)
        else:
            clauses.append("default_system_id = ?")
            params.append(actor.default_system_id)
        where_sql = " AND ".join(clauses)
        rows = conn.execute(
            f"""
            SELECT request_id, status, priority, risk_class, updated_at
            FROM requests
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [
            {
                "request_id": row["request_id"], "status": row["status"],
                "priority": row["priority"], "risk_class": row["risk_class"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _query_capabilities(conn: sqlite3.Connection, *, status_filter: str, system_ids: list[str] | None) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status_filter in {"planned", "available", "in_progress", "blocked", "deprecated"}:
            clauses.append("status = ?")
            params.append(status_filter)
        elif status_filter != "all":
            raise NexusError("NX-VAL-001", "invalid status filter")
        if system_ids is not None:
            if not system_ids:
                return []
            clauses.append("system_id IN ({})".format(", ".join("?" for _ in system_ids)))
            params.extend(system_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT capability_id, system_id, title, status
            FROM capabilities
            {where}
            ORDER BY system_id ASC, capability_id ASC
            """,
            params,
        ).fetchall()
        return [
            {"capability_id": row["capability_id"], "system_id": row["system_id"], "title": row["title"], "status": row["status"]}
            for row in rows
        ]
