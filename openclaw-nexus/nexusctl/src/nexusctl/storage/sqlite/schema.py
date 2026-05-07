"""SQLite schema for the Nexusctl persistent kernel for the current persistent kernel."""

from __future__ import annotations

import sqlite3

MVP_TABLES: tuple[str, ...] = (
    "agents",
    "domains",
    "domain_memberships",
    "capabilities",
    "goals",
    "goal_metrics",
    "goal_measurements",
    "goal_evaluations",
    "feature_requests",
    "work_items",
    "scope_leases",
    "patch_proposals",
    "reviews",
    "acceptances",
    "evidence",
    "events",
    "github_repositories",
    "github_issue_links",
    "github_pull_links",
    "github_pull_states",
    "policy_checks",
    "github_check_runs",
    "github_pr_review_links",
    "github_projection_labels",
    "merge_records",
    "github_alerts",
    "github_webhook_events",
    "schedule_runs",
    "backups",
)

AUXILIARY_TABLES: tuple[str, ...] = (
    "schema_migrations",
    "agent_capabilities",
    "agent_tokens",
    "agent_sessions",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS domains (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  source_of_truth TEXT NOT NULL CHECK (source_of_truth = 'nexusctl'),
  default_visibility TEXT NOT NULL DEFAULT 'own_domain',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  role TEXT NOT NULL,
  normal_agent INTEGER NOT NULL CHECK (normal_agent IN (0,1)),
  description TEXT NOT NULL DEFAULT '',
  github_direct_write INTEGER NOT NULL DEFAULT 0 CHECK (github_direct_write = 0),
  repo_direct_apply INTEGER NOT NULL DEFAULT 0 CHECK (repo_direct_apply = 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS domain_memberships (
  agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE CASCADE,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  role TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'auth_token',
  PRIMARY KEY (agent_id, domain_id)
);

CREATE TABLE IF NOT EXISTS capabilities (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  mutating INTEGER NOT NULL CHECK (mutating IN (0,1)),
  cross_domain_mutating INTEGER NOT NULL CHECK (cross_domain_mutating IN (0,1)),
  side_effect TEXT NOT NULL,
  target_domain_allowed INTEGER NOT NULL DEFAULT 0 CHECK (target_domain_allowed IN (0,1)),
  reserved_for TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS agent_capabilities (
  agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE CASCADE,
  capability_id TEXT NOT NULL REFERENCES capabilities(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  PRIMARY KEY (agent_id, capability_id)
);

CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  owner_agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  window TEXT,
  evaluation_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS goal_metrics (
  goal_id TEXT NOT NULL REFERENCES goals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  metric_id TEXT NOT NULL,
  type TEXT NOT NULL,
  operator TEXT NOT NULL,
  target_json TEXT NOT NULL,
  unit TEXT,
  PRIMARY KEY (goal_id, metric_id)
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  goal_id TEXT REFERENCES goals(id) ON UPDATE CASCADE ON DELETE SET NULL,
  uri TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'file',
  summary TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  added_by TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS goal_measurements (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  metric_id TEXT NOT NULL,
  measured_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  value_json TEXT NOT NULL,
  evidence_id TEXT REFERENCES evidence(id) ON UPDATE CASCADE ON DELETE SET NULL,
  recorded_by TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  FOREIGN KEY (goal_id, metric_id) REFERENCES goal_metrics(goal_id, metric_id) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS goal_evaluations (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('passing','warning','failing','unknown')),
  summary TEXT NOT NULL DEFAULT '',
  details_json TEXT NOT NULL DEFAULT '{}',
  evaluated_by TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  evaluated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS feature_requests (
  id TEXT PRIMARY KEY,
  source_domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  target_domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  created_by TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  goal_id TEXT REFERENCES goals(id) ON UPDATE CASCADE ON DELETE SET NULL,
  summary TEXT NOT NULL,
  status TEXT NOT NULL,
  acceptance_contract TEXT,
  safety_contract TEXT,
  dedupe_key TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS work_items (
  id TEXT PRIMARY KEY,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  feature_request_id TEXT NOT NULL REFERENCES feature_requests(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  assigned_agent_id TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  reviewer_agent_id TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  status TEXT NOT NULL,
  scope_lease_id TEXT,
  summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS scope_leases (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL REFERENCES work_items(id) ON UPDATE CASCADE ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  capabilities_json TEXT NOT NULL,
  paths_json TEXT NOT NULL DEFAULT '[]',
  granted_by TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  status TEXT NOT NULL,
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS patch_proposals (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL REFERENCES work_items(id) ON UPDATE CASCADE ON DELETE CASCADE,
  submitted_by TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  scope_lease_id TEXT REFERENCES scope_leases(id) ON UPDATE CASCADE ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'submitted',
  diff_summary TEXT NOT NULL DEFAULT '',
  diff_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL REFERENCES work_items(id) ON UPDATE CASCADE ON DELETE CASCADE,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  reviewer_agent_id TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  status TEXT NOT NULL,
  verdict TEXT,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS acceptances (
  id TEXT PRIMARY KEY,
  feature_request_id TEXT NOT NULL REFERENCES feature_requests(id) ON UPDATE CASCADE ON DELETE CASCADE,
  submitted_by TEXT NOT NULL REFERENCES agents(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('accepted','rejected','pending','vetoed')),
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  prev_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS github_repositories (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  name TEXT NOT NULL,
  default_branch TEXT NOT NULL,
  visibility TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS github_issue_links (
  id TEXT PRIMARY KEY,
  feature_request_id TEXT NOT NULL REFERENCES feature_requests(id) ON UPDATE CASCADE ON DELETE CASCADE,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  issue_number INTEGER NOT NULL,
  url TEXT,
  synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (repository_id, issue_number)
);

CREATE TABLE IF NOT EXISTS github_pull_links (
  id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposals(id) ON UPDATE CASCADE ON DELETE CASCADE,
  repository_id TEXT NOT NULL REFERENCES github_repositories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pull_number INTEGER NOT NULL,
  branch TEXT NOT NULL,
  url TEXT,
  synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE (repository_id, pull_number)
);

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

CREATE TABLE IF NOT EXISTS schedule_runs (
  id TEXT PRIMARY KEY,
  schedule_id TEXT NOT NULL,
  agent_id TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  domain_id TEXT REFERENCES domains(id) ON UPDATE CASCADE ON DELETE SET NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  finished_at TEXT,
  output_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS backups (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT REFERENCES agents(id) ON UPDATE CASCADE ON DELETE SET NULL,
  size_bytes INTEGER,
  checksum TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);


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

CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_type, aggregate_id, id);
CREATE INDEX IF NOT EXISTS idx_events_chain ON events(id, prev_hash, event_hash);
CREATE INDEX IF NOT EXISTS idx_feature_requests_status ON feature_requests(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_feature_requests_dedupe_key ON feature_requests(dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_work_items_feature_request ON work_items(feature_request_id);
CREATE INDEX IF NOT EXISTS idx_scope_leases_agent_status ON scope_leases(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_policy_checks_patch ON policy_checks(patch_id, status);
CREATE INDEX IF NOT EXISTS idx_github_check_runs_patch ON github_check_runs(patch_id, conclusion);
CREATE INDEX IF NOT EXISTS idx_github_pr_review_links_patch ON github_pr_review_links(patch_id, state);
CREATE INDEX IF NOT EXISTS idx_github_projection_labels_entity ON github_projection_labels(entity_kind, nexus_entity_id);
CREATE INDEX IF NOT EXISTS idx_merge_records_patch ON merge_records(patch_id, status);
CREATE INDEX IF NOT EXISTS idx_github_alerts_open ON github_alerts(status, severity, patch_id, feature_request_id);
CREATE INDEX IF NOT EXISTS idx_agent_tokens_agent_active ON agent_tokens(agent_id, active);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_expiry ON agent_sessions(agent_id, expires_at);

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


def create_schema(connection: sqlite3.Connection) -> None:
    """Create all tables, indexes, and append-only triggers for the current schema."""

    connection.executescript(SCHEMA_SQL)


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def assert_schema_ready(connection: sqlite3.Connection) -> None:
    """Raise ValueError if any MVP table is missing."""

    missing = [table for table in MVP_TABLES if not table_exists(connection, table)]
    if missing:
        raise ValueError(f"database schema missing required tables: {', '.join(missing)}")
