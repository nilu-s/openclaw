"""SQLite migrations and blueprint seeding for Nexusctl."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any

import yaml

from nexusctl.storage.event_store import GENESIS_EVENT_HASH, EventStore, compute_hash_for_row
from nexusctl.storage.sqlite.schema import create_schema


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str = ""



FEATURE_REQUEST_DEDUPE_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_feature_requests_dedupe_key
ON feature_requests(dedupe_key)
WHERE dedupe_key IS NOT NULL;
"""


WORK_SCOPE_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_items_feature_request
ON work_items(feature_request_id);

CREATE INDEX IF NOT EXISTS idx_scope_leases_agent_status_expiry
ON scope_leases(agent_id, status, expires_at);

CREATE INDEX IF NOT EXISTS idx_scope_leases_work_item
ON scope_leases(work_item_id);
"""

POLICY_CHECKS_SQL = """
CREATE TABLE IF NOT EXISTS github_pull_states (
  id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pull_number INTEGER NOT NULL,
  head_sha TEXT NOT NULL,
  validated_patch_sha TEXT NOT NULL,
  synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (repository_id, pull_number),
  UNIQUE (patch_id, repository_id)
);

CREATE TABLE IF NOT EXISTS policy_checks (
  id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('passed','pending','failed')),
  conclusion TEXT NOT NULL CHECK (conclusion IN ('success','pending','failure')),
  required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0,1)),
  head_sha TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  checked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (patch_id, name)
);

CREATE TABLE IF NOT EXISTS github_check_runs (
  id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pull_number INTEGER NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  conclusion TEXT,
  head_sha TEXT NOT NULL,
  external_id TEXT,
  url TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (patch_id, repository_id, pull_number, name)
);

CREATE INDEX IF NOT EXISTS idx_policy_checks_patch
ON policy_checks(patch_id, status);

CREATE INDEX IF NOT EXISTS idx_github_check_runs_patch
ON github_check_runs(patch_id, conclusion);
"""


REVIEW_ACCEPTANCE_SQL = """
CREATE TABLE IF NOT EXISTS github_pr_review_links (
  id TEXT PRIMARY KEY,
  review_id TEXT NOT NULL REFERENCES reviews(id) ON UPDATE CASCADE ON DELETE CASCADE,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pull_number INTEGER NOT NULL,
  external_id TEXT,
  url TEXT,
  state TEXT NOT NULL,
  synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (review_id, repository_id, pull_number)
);

CREATE TABLE IF NOT EXISTS github_projection_labels (
  id TEXT PRIMARY KEY,
  entity_kind TEXT NOT NULL CHECK (entity_kind IN ('issue','pull_request')),
  nexus_entity_id TEXT NOT NULL,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  external_number INTEGER NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '[]',
  synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (entity_kind, nexus_entity_id, repository_id, external_number)
);

CREATE INDEX IF NOT EXISTS idx_github_pr_review_links_patch
ON github_pr_review_links(patch_id, state);

CREATE INDEX IF NOT EXISTS idx_github_projection_labels_entity
ON github_projection_labels(entity_kind, nexus_entity_id);
"""


MERGE_GATE_SQL = """
CREATE TABLE IF NOT EXISTS merge_records (
  id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  feature_request_id TEXT NOT NULL REFERENCES feature_requests(id) ON UPDATE CASCADE ON DELETE CASCADE,
  work_item_id TEXT NOT NULL REFERENCES work_items(id) ON UPDATE CASCADE ON DELETE CASCADE,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pull_number INTEGER NOT NULL,
  merged_by TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  merge_sha TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('merged','failed','blocked')),
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (patch_id, repository_id, pull_number)
);

CREATE TABLE IF NOT EXISTS github_alerts (
  id TEXT PRIMARY KEY,
  repository_id TEXT REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE SET NULL,
  pull_number INTEGER,
  patch_id TEXT REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE SET NULL,
  feature_request_id TEXT REFERENCES feature_requests(id) ON UPDATE CASCADE ON DELETE SET NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
  status TEXT NOT NULL CHECK (status IN ('open','resolved')),
  kind TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_merge_records_patch
ON merge_records(patch_id, status);

CREATE INDEX IF NOT EXISTS idx_github_alerts_open
ON github_alerts(status, severity, patch_id, feature_request_id);
"""


WEBHOOK_RECONCILIATION_SQL = """
CREATE TABLE IF NOT EXISTS github_webhook_events (
  id TEXT PRIMARY KEY,
  repository_id TEXT REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE SET NULL,
  delivery_id TEXT NOT NULL UNIQUE,
  event_name TEXT NOT NULL,
  action TEXT,
  payload_json TEXT NOT NULL,
  signature_verified INTEGER NOT NULL DEFAULT 1 CHECK (signature_verified IN (0,1)),
  processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('pending','processed','alerted','ignored','dead_letter')),
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  processed_at TEXT,
  alert_id TEXT REFERENCES github_alerts(id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_github_webhook_events_processing
ON github_webhook_events(processing_status, processed_at);
"""



EVENT_HASH_CHAIN_SQL = """
CREATE INDEX IF NOT EXISTS idx_events_chain ON events(id, prev_hash, event_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_hash ON events(event_hash);
"""

AUTH_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_tokens (
  token_id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  token_prefix TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_by TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  rotated_at TEXT,
  last_used_at TEXT,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_sessions (
  session_id TEXT PRIMARY KEY,
  token_id TEXT NOT NULL REFERENCES agent_tokens(token_id) ON UPDATE CASCADE ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE CASCADE,
  issued_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  expires_at TEXT NOT NULL,
  revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_tokens_agent_active ON agent_tokens(agent_id, active);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_expiry ON agent_sessions(agent_id, expires_at);
"""

MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="initial_storage_schema"),
    Migration(version=2, name="agent_auth_registry", sql=AUTH_TABLES_SQL),
    Migration(version=3, name="feature_request_dedupe", sql=FEATURE_REQUEST_DEDUPE_SQL),
    Migration(version=4, name="work_scope_indexes", sql=WORK_SCOPE_SQL),
    Migration(version=5, name="policy_checks_and_github_check_runs", sql=POLICY_CHECKS_SQL),
    Migration(version=6, name="review_acceptance_projection", sql=REVIEW_ACCEPTANCE_SQL),
    Migration(version=7, name="merge_gate_and_alerts", sql=MERGE_GATE_SQL),
    Migration(version=8, name="webhook_reconciliation", sql=WEBHOOK_RECONCILIATION_SQL),
    Migration(version=9, name="event_hash_chain", sql=EVENT_HASH_CHAIN_SQL),
)


def _ensure_webhook_reconciliation_columns(connection: sqlite3.Connection) -> None:
    """Backfill webhooks columns for databases initialized by older schema revisions."""

    rows = connection.execute("PRAGMA table_info(github_webhook_events)").fetchall()
    columns = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in rows}
    additions = {
        "action": "ALTER TABLE github_webhook_events ADD COLUMN action TEXT",
        "signature_verified": "ALTER TABLE github_webhook_events ADD COLUMN signature_verified INTEGER NOT NULL DEFAULT 1 CHECK (signature_verified IN (0,1))",
        "processing_status": "ALTER TABLE github_webhook_events ADD COLUMN processing_status TEXT NOT NULL DEFAULT 'pending' CHECK (processing_status IN ('pending','processed','alerted','ignored','dead_letter'))",
        "alert_id": "ALTER TABLE github_webhook_events ADD COLUMN alert_id TEXT REFERENCES github_alerts(id) ON UPDATE CASCADE ON DELETE SET NULL",
    }
    for column, sql in additions.items():
        if column not in columns:
            connection.execute(sql)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_github_webhook_events_processing ON github_webhook_events(processing_status, processed_at)"
    )


def _ensure_event_hash_chain(connection: sqlite3.Connection) -> None:
    """Add and backfill deterministic event-chain columns for existing databases."""

    rows = connection.execute("PRAGMA table_info(events)").fetchall()
    columns = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in rows}
    if "prev_hash" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT NOT NULL DEFAULT ''")
    if "event_hash" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN event_hash TEXT NOT NULL DEFAULT ''")

    connection.execute("DROP TRIGGER IF EXISTS events_append_only_no_update")
    connection.execute("DROP TRIGGER IF EXISTS events_append_only_no_delete")

    previous = GENESIS_EVENT_HASH
    event_rows = connection.execute("SELECT * FROM events ORDER BY id ASC").fetchall()
    for row in event_rows:
        expected = compute_hash_for_row(row, prev_hash=previous)
        if row["prev_hash"] != previous or row["event_hash"] != expected:
            connection.execute(
                "UPDATE events SET prev_hash = ?, event_hash = ? WHERE id = ?",
                (previous, expected, row["id"]),
            )
        previous = expected

    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_events_chain ON events(id, prev_hash, event_hash);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_hash ON events(event_hash) WHERE event_hash != '';

        CREATE TRIGGER IF NOT EXISTS events_append_only_no_update
        BEFORE UPDATE ON events
        BEGIN
          SELECT RAISE(ABORT, 'events are append-only and cannot be updated');
        END;

        CREATE TRIGGER IF NOT EXISTS events_append_only_no_delete
        BEFORE DELETE ON events
        BEGIN
          SELECT RAISE(ABORT, 'events are append-only and cannot be deleted');
        END;
        """
    )


def applied_versions(connection: sqlite3.Connection) -> set[int]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
        """
    )
    rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row["version"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows}


def apply_migrations(connection: sqlite3.Connection) -> list[Migration]:
    """Apply pending migrations and return the migrations applied in this call."""

    done = applied_versions(connection)
    applied: list[Migration] = []
    for migration in MIGRATIONS:
        if migration.version in done:
            continue
        if migration.version == 1:
            create_schema(connection)
        elif migration.sql:
            if migration.version == 9:
                _ensure_event_hash_chain(connection)
            else:
                connection.executescript(migration.sql)
                if migration.version == 8:
                    _ensure_webhook_reconciliation_columns(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )
        applied.append(migration)
    return applied


def init_database(connection: sqlite3.Connection, project_root: str | Path, *, seed_blueprint: bool = True) -> None:
    """Apply migrations and optionally seed declarative Nexus design data."""

    apply_migrations(connection)
    if seed_blueprint:
        seed_from_blueprint(connection, project_root)


def seed_from_blueprint(connection: sqlite3.Connection, project_root: str | Path) -> None:
    """Idempotently seed domains, agents, capabilities, goals, and repositories."""

    root = Path(project_root)
    nexus = root / "nexus"
    domains_yml = _load_yaml(nexus / "domains.yml")
    agents_yml = _load_yaml(nexus / "agents.yml")
    capabilities_yml = _load_yaml(nexus / "capabilities.yml")
    goals_yml = _load_yaml(nexus / "goals.yml")
    github_yml = _load_yaml(nexus / "github.yml")

    for domain in domains_yml.get("domains", []):
        connection.execute(
            """
            INSERT INTO domains(id, name, status, description, source_of_truth, default_visibility)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              status=excluded.status,
              description=excluded.description,
              source_of_truth=excluded.source_of_truth,
              default_visibility=excluded.default_visibility,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (
                domain["id"],
                domain.get("name", domain["id"]),
                domain.get("status", "mvp"),
                domain.get("description", ""),
                domain.get("source_of_truth", "nexusctl"),
                domain.get("default_visibility", "own_domain"),
            ),
        )

    for capability in capabilities_yml.get("capabilities", []):
        connection.execute(
            """
            INSERT INTO capabilities(
              id, category, mutating, cross_domain_mutating, side_effect, target_domain_allowed, reserved_for
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              category=excluded.category,
              mutating=excluded.mutating,
              cross_domain_mutating=excluded.cross_domain_mutating,
              side_effect=excluded.side_effect,
              target_domain_allowed=excluded.target_domain_allowed,
              reserved_for=excluded.reserved_for
            """,
            (
                capability["id"],
                capability.get("category", "unknown"),
                int(bool(capability.get("mutating", False))),
                int(bool(capability.get("cross_domain_mutating", False))),
                capability.get("side_effect", "read_only"),
                int(bool(capability.get("target_domain_allowed", False))),
                capability.get("reserved_for"),
            ),
        )

    for agent in agents_yml.get("agents", []):
        connection.execute(
            """
            INSERT INTO agents(
              id, display_name, domain_id, role, normal_agent, description, github_direct_write, repo_direct_apply
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              display_name=excluded.display_name,
              domain_id=excluded.domain_id,
              role=excluded.role,
              normal_agent=excluded.normal_agent,
              description=excluded.description,
              github_direct_write=excluded.github_direct_write,
              repo_direct_apply=excluded.repo_direct_apply,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (
                agent["id"],
                agent.get("display_name", agent["id"]),
                agent["domain"],
                agent.get("role", agent["id"]),
                int(bool(agent.get("normal_agent", True))),
                agent.get("description", ""),
                int(bool((agent.get("github") or {}).get("direct_write", False))),
                int(bool((agent.get("repo") or {}).get("direct_apply", False))),
            ),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO domain_memberships(agent_id, domain_id, role, source)
            VALUES (?, ?, ?, 'auth_token')
            """,
            (agent["id"], agent["domain"], agent.get("role", agent["id"])),
        )
        connection.execute("DELETE FROM agent_capabilities WHERE agent_id = ?", (agent["id"],))
        for capability_id in agent.get("capabilities", []):
            connection.execute(
                "INSERT INTO agent_capabilities(agent_id, capability_id) VALUES (?, ?)",
                (agent["id"], capability_id),
            )

    for goal in goals_yml.get("goals", []):
        connection.execute(
            """
            INSERT INTO goals(
              id, domain_id, owner_agent_id, description, status, window, evaluation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              domain_id=excluded.domain_id,
              owner_agent_id=excluded.owner_agent_id,
              description=excluded.description,
              status=excluded.status,
              window=excluded.window,
              evaluation_json=excluded.evaluation_json,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (
                goal["id"],
                goal["domain"],
                goal["owner_agent"],
                goal.get("description", ""),
                goal.get("status", "active"),
                goal.get("window"),
                _json(goal.get("evaluation", {})),
            ),
        )
        connection.execute("DELETE FROM goal_metrics WHERE goal_id = ?", (goal["id"],))
        for metric in goal.get("metrics", []):
            connection.execute(
                """
                INSERT INTO goal_metrics(goal_id, metric_id, type, operator, target_json, unit)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    goal["id"],
                    metric["id"],
                    metric.get("type", "unknown"),
                    metric.get("operator", "=="),
                    _json(metric.get("target")),
                    metric.get("unit"),
                ),
            )

    github = github_yml.get("github") or {}
    for repository in github.get("repositories", []):
        connection.execute(
            """
            INSERT INTO github_repositories(id, owner, name, default_branch, visibility)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              owner=excluded.owner,
              name=excluded.name,
              default_branch=excluded.default_branch,
              visibility=excluded.visibility
            """,
            (
                repository["id"],
                repository.get("owner", ""),
                repository.get("name", repository["id"]),
                repository.get("default_branch", "main"),
                repository.get("visibility", "private_or_internal"),
            ),
        )

    EventStore(connection).append(
        aggregate_type="database",
        aggregate_id="nexus",
        event_type="database.blueprint_seeded",
        actor_id="nexusctl",
        payload={
            "domains": len(domains_yml.get("domains", [])),
            "agents": len(agents_yml.get("agents", [])),
            "capabilities": len(capabilities_yml.get("capabilities", [])),
            "goals": len(goals_yml.get("goals", [])),
            "repositories": len(github.get("repositories", [])),
        },
        metadata={"source": "nexus/*.yml"},
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a top-level mapping")
    return data


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
