"""Minimal SQLite repositories for storage Nexus data.

The repositories intentionally cover only the first durable mutations needed by
later services. Every mutation appends an audit event through ``EventStore``.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import sqlite3
from typing import Any

from nexusctl.domain.models import FeatureRequest, ScopeLease, WorkItem
from nexusctl.domain.states import FeatureRequestStatus
from nexusctl.storage.event_store import EventRecord, EventStore


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


class RepositoryContext:
    """Container for repositories sharing one connection and event store."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.events = EventStore(connection)
        self.goals = GoalRepository(connection, self.events)
        self.feature_requests = FeatureRequestRepository(connection, self.events)
        self.work_items = WorkItemRepository(connection, self.events)
        self.scope_leases = ScopeLeaseRepository(connection, self.events)
        self.patches = PatchProposalRepository(connection, self.events)
        self.reviews = ReviewRepository(connection, self.events)
        self.acceptances = AcceptanceRepository(connection, self.events)
        self.policy_checks = PolicyCheckRepository(connection, self.events)
        self.merges = MergeRepository(connection, self.events)

    def count(self, table_name: str) -> int:
        if not table_name.replace("_", "").isalnum():
            raise ValueError("invalid table name")
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"])


class GoalRepository:
    """SQLite access for goal records, evidence, measurements, and evaluations."""

    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def list_for_domain(self, domain_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT id, domain_id, owner_agent_id, status, window, description
              FROM goals
             WHERE domain_id = ?
             ORDER BY id
            """,
            (domain_id,),
        ).fetchall()

    def get(self, goal_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT id, domain_id, owner_agent_id, status, window, description
              FROM goals
             WHERE id = ?
            """,
            (goal_id,),
        ).fetchone()

    def metrics_for_goal(self, goal_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT metric_id, type, operator, target_json, unit
              FROM goal_metrics
             WHERE goal_id = ?
             ORDER BY metric_id
            """,
            (goal_id,),
        ).fetchall()

    def latest_evaluation(self, goal_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT id, status, summary, details_json, evaluated_by, evaluated_at
              FROM goal_evaluations
             WHERE goal_id = ?
             ORDER BY evaluated_at DESC, id DESC
             LIMIT 1
            """,
            (goal_id,),
        ).fetchone()

    def evidence_for_goal(self, goal_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT id, domain_id, goal_id, uri, kind, summary, payload_json, added_by, created_at
              FROM evidence
             WHERE goal_id = ?
             ORDER BY created_at DESC, id DESC
            """,
            (goal_id,),
        ).fetchall()

    def get_evidence_for_goal(self, goal_id: str, evidence_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM evidence WHERE id = ? AND goal_id = ?",
            (evidence_id, goal_id),
        ).fetchone()

    def latest_evidence_for_goal(self, goal_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM evidence
             WHERE goal_id = ?
             ORDER BY created_at DESC, id DESC
             LIMIT 1
            """,
            (goal_id,),
        ).fetchone()

    def add_file_evidence(
        self,
        *,
        evidence_id: str,
        domain_id: str,
        goal_id: str,
        uri: str,
        summary: str,
        payload_json: str,
        added_by: str,
        created_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO evidence(id, domain_id, goal_id, uri, kind, summary, payload_json, added_by, created_at)
            VALUES (?, ?, ?, ?, 'file', ?, ?, ?, ?)
            """,
            (evidence_id, domain_id, goal_id, uri, summary, payload_json, added_by, created_at),
        )

    def add_measurement(
        self,
        *,
        measurement_id: str,
        goal_id: str,
        metric_id: str,
        measured_at: str,
        value_json: str,
        evidence_id: str | None,
        recorded_by: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO goal_measurements(id, goal_id, metric_id, measured_at, value_json, evidence_id, recorded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (measurement_id, goal_id, metric_id, measured_at, value_json, evidence_id, recorded_by),
        )

    def latest_measurements(self, goal_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT id, metric_id, value_json, evidence_id, recorded_by, measured_at
              FROM goal_measurements
             WHERE goal_id = ?
             ORDER BY measured_at DESC, id DESC
            """,
            (goal_id,),
        ).fetchall()

    def add_evaluation(
        self,
        *,
        evaluation_id: str,
        goal_id: str,
        status: str,
        summary: str,
        details_json: str,
        evaluated_by: str,
        evaluated_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO goal_evaluations(id, goal_id, status, summary, details_json, evaluated_by, evaluated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (evaluation_id, goal_id, status, summary, details_json, evaluated_by, evaluated_at),
        )

    def update_cached_evaluation(self, goal_id: str, evaluation_json: str) -> None:
        self.connection.execute(
            """
            UPDATE goals
               SET evaluation_json = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
             WHERE id = ?
            """,
            (evaluation_json, goal_id),
        )

    def goal_domain(self, goal_id: str) -> str | None:
        row = self.connection.execute("SELECT domain_id FROM goals WHERE id = ?", (goal_id,)).fetchone()
        return row["domain_id"] if row is not None else None


class FeatureRequestRepository:
    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def create(
        self,
        request: FeatureRequest,
        *,
        actor_id: str | None = None,
        created_event_payload: dict[str, Any] | None = None,
        created_event_metadata: dict[str, Any] | None = None,
    ) -> EventRecord:
        self.connection.execute(
            """
            INSERT INTO feature_requests(
              id, source_domain_id, target_domain_id, created_by, goal_id, summary,
              status, acceptance_contract, safety_contract, dedupe_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                request.source_domain,
                request.target_domain,
                request.created_by,
                request.goal_id,
                request.summary,
                _enum_value(request.status),
                request.acceptance_contract,
                request.safety_contract,
                request.dedupe_key,
                request.created_at.isoformat().replace("+00:00", "Z"),
                request.created_at.isoformat().replace("+00:00", "Z"),
            ),
        )
        return self.events.append(
            aggregate_type="feature_request",
            aggregate_id=request.id,
            event_type="feature_request.created",
            actor_id=actor_id or request.created_by,
            payload=created_event_payload
            or {
                "id": request.id,
                "source_domain": request.source_domain,
                "target_domain": request.target_domain,
                "goal_id": request.goal_id,
                "summary": request.summary,
                "status": _enum_value(request.status),
                "dedupe_key": request.dedupe_key,
            },
            metadata=created_event_metadata or {"repository": self.__class__.__name__},
        )

    def get(self, request_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM feature_requests WHERE id = ?", (request_id,)).fetchone()

    def get_by_dedupe_key(self, dedupe_key: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM feature_requests WHERE dedupe_key = ?", (dedupe_key,)).fetchone()

    def list_visible_to_domain(self, domain_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT * FROM feature_requests
            WHERE source_domain_id = ? OR target_domain_id = ?
            ORDER BY updated_at DESC, created_at DESC, id ASC
            """,
            (domain_id, domain_id),
        ).fetchall()

    def list_all(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM feature_requests ORDER BY updated_at DESC, created_at DESC, id ASC"
        ).fetchall()

    def route(self, *, request_id: str, target_domain: str, status: FeatureRequestStatus, dedupe_key: str, updated_at: str) -> None:
        self.connection.execute(
            """
            UPDATE feature_requests
            SET target_domain_id = ?, status = ?, dedupe_key = ?, updated_at = ?
            WHERE id = ?
            """,
            (target_domain, _enum_value(status), dedupe_key, updated_at, request_id),
        )

    def transition(self, *, request_id: str, status: FeatureRequestStatus, updated_at: str) -> None:
        self.connection.execute(
            "UPDATE feature_requests SET status = ?, updated_at = ? WHERE id = ?",
            (_enum_value(status), updated_at, request_id),
        )

    def domain_exists(self, domain_id: str) -> bool:
        return self.connection.execute("SELECT id FROM domains WHERE id = ?", (domain_id,)).fetchone() is not None


class WorkItemRepository:
    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def create(self, work: WorkItem, *, actor_id: str | None = None) -> EventRecord:
        self.connection.execute(
            """
            INSERT INTO work_items(
              id, domain_id, feature_request_id, assigned_agent_id, reviewer_agent_id, status, scope_lease_id, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work.id,
                work.domain,
                work.feature_request_id,
                work.assigned_agent,
                work.reviewer_agent,
                _enum_value(work.status),
                work.scope_lease_id,
                work.summary,
            ),
        )
        return self.events.append(
            aggregate_type="work_item",
            aggregate_id=work.id,
            event_type="work_item.created",
            actor_id=actor_id,
            payload={
                "id": work.id,
                "domain": work.domain,
                "feature_request_id": work.feature_request_id,
                "assigned_agent": work.assigned_agent,
                "reviewer_agent": work.reviewer_agent,
                "status": _enum_value(work.status),
            },
            metadata={"repository": self.__class__.__name__},
        )


    def get(self, work_item_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()

    def get_by_feature_request(self, feature_request_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM work_items
            WHERE feature_request_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (feature_request_id,),
        ).fetchone()

    def create_planned(self, *, work_id: str, domain_id: str, feature_request_id: str, summary: str, created_at: str, updated_at: str, status: str) -> None:
        self.connection.execute(
            """
            INSERT INTO work_items(
              id, domain_id, feature_request_id, assigned_agent_id, reviewer_agent_id,
              status, scope_lease_id, summary, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, ?, NULL, ?, ?, ?)
            """,
            (work_id, domain_id, feature_request_id, status, summary, created_at, updated_at),
        )

    def assign(self, *, work_id: str, builder: str, reviewer: str, status: str, updated_at: str) -> None:
        self.connection.execute(
            """
            UPDATE work_items
            SET assigned_agent_id = ?, reviewer_agent_id = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (builder, reviewer, status, updated_at, work_id),
        )

    def update_status(self, *, work_id: str, status: str, updated_at: str) -> None:
        self.connection.execute("UPDATE work_items SET status = ?, updated_at = ? WHERE id = ?", (status, updated_at, work_id))


class ScopeLeaseRepository:
    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def create(self, lease: ScopeLease, *, paths: list[str] | None = None, actor_id: str | None = None) -> EventRecord:
        stored_paths = paths if paths is not None else list(lease.paths)
        expires_at = lease.expires_at.isoformat().replace("+00:00", "Z") if lease.expires_at else None
        self.connection.execute(
            """
            INSERT INTO scope_leases(
              id, work_item_id, agent_id, domain_id, capabilities_json, paths_json, granted_by, status, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease.id,
                lease.work_item_id,
                lease.agent_id,
                lease.domain,
                _json(list(lease.capabilities)),
                _json(stored_paths),
                lease.granted_by,
                _enum_value(lease.status),
                expires_at,
            ),
        )
        return self.events.append(
            aggregate_type="scope_lease",
            aggregate_id=lease.id,
            event_type="scope_lease.created",
            actor_id=actor_id or lease.granted_by,
            payload={
                "id": lease.id,
                "work_item_id": lease.work_item_id,
                "agent_id": lease.agent_id,
                "domain": lease.domain,
                "capabilities": list(lease.capabilities),
                "paths": stored_paths,
                "status": _enum_value(lease.status),
            },
            metadata={"repository": self.__class__.__name__},
        )

    def get(self, lease_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM scope_leases WHERE id = ?", (lease_id,)).fetchone()

    def active_for_builder(self, *, work_item_id: str, agent_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM scope_leases
            WHERE work_item_id = ? AND agent_id = ? AND status = 'active'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (work_item_id, agent_id),
        ).fetchone()


class PatchProposalRepository:
    """SQLite access for work/patch records and GitHub PR projection state."""

    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def create(self, *, patch_id: str, work_item_id: str, submitted_by: str, scope_lease_id: str, status: str, diff_summary: str, diff_json: str, created_at: str, updated_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO patch_proposals(
              id, work_item_id, submitted_by, scope_lease_id, status, diff_summary, diff_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (patch_id, work_item_id, submitted_by, scope_lease_id, status, diff_summary, diff_json, created_at, updated_at),
        )

    def get(self, patch_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM patch_proposals WHERE id = ?", (patch_id,)).fetchone()

    def get_with_work(self, patch_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT p.*, w.feature_request_id, w.domain_id, w.assigned_agent_id, w.reviewer_agent_id
            FROM patch_proposals p
            JOIN work_items w ON w.id = p.work_item_id
            WHERE p.id = ?
            """,
            (patch_id,),
        ).fetchone()

    def get_with_pr(self, patch_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT
              p.*, w.feature_request_id, w.domain_id, w.assigned_agent_id, w.reviewer_agent_id,
              fr.source_domain_id, fr.target_domain_id, fr.acceptance_contract,
              pr.repository_id, pr.pull_number, pr.branch, pr.url AS pull_url,
              ps.head_sha, ps.validated_patch_sha
            FROM patch_proposals p
            JOIN work_items w ON w.id = p.work_item_id
            JOIN feature_requests fr ON fr.id = w.feature_request_id
            LEFT JOIN github_pull_links pr ON pr.patch_id = p.id
            LEFT JOIN github_pull_states ps
              ON ps.patch_id = p.id AND ps.repository_id = pr.repository_id AND ps.pull_number = pr.pull_number
            WHERE p.id = ?
            ORDER BY pr.synced_at DESC, pr.id ASC
            LIMIT 1
            """,
            (patch_id,),
        ).fetchone()

    def get_work(self, work_item_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM work_items WHERE id = ?", (work_item_id,)).fetchone()

    def resolve_work(self, work_or_request_id: str) -> sqlite3.Row | None:
        row = self.get_work(work_or_request_id)
        if row is not None:
            return row
        return self.connection.execute(
            "SELECT * FROM work_items WHERE feature_request_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (work_or_request_id,),
        ).fetchone()

    def update_work_status(self, *, work_item_id: str, status: str, updated_at: str) -> None:
        self.connection.execute("UPDATE work_items SET status = ?, updated_at = ? WHERE id = ?", (status, updated_at, work_item_id))

    def active_lease_for_builder(self, *, work_item_id: str, agent_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM scope_leases
            WHERE work_item_id = ? AND agent_id = ? AND status = 'active'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (work_item_id, agent_id),
        ).fetchone()

    def get_pull_link(self, *, patch_id: str, repository_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM github_pull_links
            WHERE patch_id = ? AND repository_id = ?
            ORDER BY synced_at DESC, id ASC
            LIMIT 1
            """,
            (patch_id, repository_id),
        ).fetchone()

    def upsert_repository(self, *, repository_id: str, owner: str, name: str, default_branch: str, visibility: str) -> None:
        self.connection.execute(
            """
            INSERT INTO github_repositories(id, owner, name, default_branch, visibility)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET owner=excluded.owner, name=excluded.name,
              default_branch=excluded.default_branch, visibility=excluded.visibility
            """,
            (repository_id, owner, name, default_branch, visibility),
        )

    def insert_pull_link(self, *, link_id: str, patch_id: str, repository_id: str, pull_number: int, branch: str, url: str | None, synced_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO github_pull_links(id, patch_id, repository_id, pull_number, branch, url, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (link_id, patch_id, repository_id, pull_number, branch, url, synced_at),
        )

    def update_pull_link(self, *, link_id: str, pull_number: int, branch: str, url: str | None, synced_at: str) -> None:
        self.connection.execute(
            "UPDATE github_pull_links SET pull_number = ?, branch = ?, url = ?, synced_at = ? WHERE id = ?",
            (pull_number, branch, url, synced_at, link_id),
        )

    def upsert_pull_state(self, *, state_id: str, patch_id: str, repository_id: str, pull_number: int, head_sha: str, validated_patch_sha: str, synced_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO github_pull_states(id, patch_id, repository_id, pull_number, head_sha, validated_patch_sha, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(patch_id, repository_id) DO UPDATE SET
              pull_number=excluded.pull_number,
              head_sha=excluded.head_sha,
              validated_patch_sha=excluded.validated_patch_sha,
              synced_at=excluded.synced_at
            """,
            (state_id, patch_id, repository_id, pull_number, head_sha, validated_patch_sha, synced_at),
        )


class ReviewRepository:
    """SQLite access for technical review records and PR-review projections."""

    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def list_for_patch(self, patch_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM reviews WHERE patch_id = ? ORDER BY updated_at DESC, created_at DESC, id DESC",
            (patch_id,),
        ).fetchall()

    def create(self, *, review_id: str, work_item_id: str, patch_id: str, reviewer_agent_id: str, status: str, verdict: str | None, notes: str, created_at: str, updated_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO reviews(id, work_item_id, patch_id, reviewer_agent_id, status, verdict, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (review_id, work_item_id, patch_id, reviewer_agent_id, status, verdict, notes, created_at, updated_at),
        )

    def get(self, review_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()

    def update_patch_status(self, *, patch_id: str, status: str, updated_at: str) -> None:
        self.connection.execute("UPDATE patch_proposals SET status = ?, updated_at = ? WHERE id = ?", (status, updated_at, patch_id))

    def update_work_status(self, *, work_item_id: str, status: str, updated_at: str) -> None:
        self.connection.execute("UPDATE work_items SET status = ?, updated_at = ? WHERE id = ?", (status, updated_at, work_item_id))


class AcceptanceRepository:
    """SQLite access for business-domain acceptance and veto records."""

    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def create(self, *, acceptance_id: str, feature_request_id: str, submitted_by: str, status: str, notes: str, created_at: str) -> None:
        self.connection.execute(
            """
            INSERT INTO acceptances(id, feature_request_id, submitted_by, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (acceptance_id, feature_request_id, submitted_by, status, notes, created_at),
        )

    def list_for_feature_request(self, feature_request_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM acceptances WHERE feature_request_id = ? ORDER BY created_at DESC, id DESC",
            (feature_request_id,),
        ).fetchall()

    def latest_veto_for_feature_request(self, feature_request_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM acceptances WHERE feature_request_id = ? AND status = 'vetoed' ORDER BY created_at DESC, id DESC LIMIT 1",
            (feature_request_id,),
        ).fetchone()


class PolicyCheckRepository:
    """SQLite access for merge policy gates and GitHub check-run projections."""

    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def upsert_policy_check(self, *, check_id: str, patch_id: str, name: str, status: str, conclusion: str, required: bool, head_sha: str, details_json: str, checked_at: str) -> str:
        existing = self.connection.execute("SELECT id FROM policy_checks WHERE patch_id = ? AND name = ?", (patch_id, name)).fetchone()
        if existing is None:
            self.connection.execute(
                """
                INSERT INTO policy_checks(id, patch_id, name, status, conclusion, required, head_sha, details_json, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (check_id, patch_id, name, status, conclusion, int(required), head_sha, details_json, checked_at),
            )
            return check_id
        existing_id = existing["id"]
        self.connection.execute(
            """
            UPDATE policy_checks
            SET status = ?, conclusion = ?, required = ?, head_sha = ?, details_json = ?, checked_at = ?
            WHERE id = ?
            """,
            (status, conclusion, int(required), head_sha, details_json, checked_at, existing_id),
        )
        return existing_id

    def upsert_github_check_run(self, *, check_id: str, patch_id: str, repository_id: str, pull_number: int, name: str, status: str, conclusion: str | None, head_sha: str, external_id: str | None, url: str | None, details_json: str, synced_at: str) -> str:
        existing = self.connection.execute(
            """
            SELECT id FROM github_check_runs
            WHERE patch_id = ? AND repository_id = ? AND pull_number = ? AND name = ?
            """,
            (patch_id, repository_id, pull_number, name),
        ).fetchone()
        if existing is None:
            self.connection.execute(
                """
                INSERT INTO github_check_runs(
                  id, patch_id, repository_id, pull_number, name, status, conclusion, head_sha,
                  external_id, url, details_json, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (check_id, patch_id, repository_id, pull_number, name, status, conclusion, head_sha, external_id, url, details_json, synced_at),
            )
            return check_id
        existing_id = existing["id"]
        self.connection.execute(
            """
            UPDATE github_check_runs
            SET status = ?, conclusion = ?, head_sha = ?, external_id = ?, url = ?, details_json = ?, synced_at = ?
            WHERE id = ?
            """,
            (status, conclusion, head_sha, external_id, url, details_json, synced_at, existing_id),
        )
        return existing_id


class MergeRepository:
    """SQLite access for merge records and terminal feature-request updates."""

    def __init__(self, connection: sqlite3.Connection, event_store: EventStore) -> None:
        self.connection = connection
        self.events = event_store

    def create(self, *, merge_id: str, patch_id: str, feature_request_id: str, work_item_id: str, repository_id: str, pull_number: int, merged_by: str, merge_sha: str, status: str, details_json: str) -> None:
        self.connection.execute(
            """
            INSERT INTO merge_records(
              id, patch_id, feature_request_id, work_item_id, repository_id, pull_number,
              merged_by, merge_sha, status, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (merge_id, patch_id, feature_request_id, work_item_id, repository_id, pull_number, merged_by, merge_sha, status, details_json),
        )

    def get_by_patch(self, patch_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM merge_records WHERE patch_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (patch_id,)).fetchone()
