from __future__ import annotations

from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.domain.models import FeatureRequest, ScopeLease, WorkItem
from nexusctl.domain.states import ScopeLeaseStatus
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database
from nexusctl.storage.sqlite.repositories import RepositoryContext
from nexusctl.storage.sqlite.schema import MVP_TABLES, assert_schema_ready


def test_storage_schema_has_all_mvp_tables(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    connection = connect_database(db)
    try:
        init_database(connection, ROOT, seed_blueprint=False)
        connection.commit()
        assert_schema_ready(connection)
        actual = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        assert set(MVP_TABLES).issubset(actual)
        assert "agent_capabilities" in actual
    finally:
        connection.close()


def test_storage_db_can_be_initialized_from_blueprint(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    connection = connect_database(db)
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        connection.commit()

        counts = {
            table: connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ["domains", "agents", "capabilities", "goals", "goal_metrics", "github_repositories"]
        }
        assert counts["domains"] == 5
        assert counts["agents"] == 11
        assert counts["capabilities"] >= 30
        assert counts["goals"] >= 3
        assert counts["goal_metrics"] >= 9
        assert counts["github_repositories"] == 1

        builder_caps = {
            row["capability_id"]
            for row in connection.execute(
                "SELECT capability_id FROM agent_capabilities WHERE agent_id = ?",
                ("software-builder",),
            ).fetchall()
        }
        assert "patch.submit" in builder_caps
        assert "review.approve" not in builder_caps

        seed_events = EventStore(connection).list_for_aggregate("database", "nexus")
        assert seed_events[-1].event_type == "database.blueprint_seeded"
    finally:
        connection.close()


def test_storage_events_are_append_only(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=False)
        event = EventStore(connection).append(
            aggregate_type="feature_request",
            aggregate_id="fr-001",
            event_type="feature_request.created",
            actor_id="control-router",
            payload={"summary": "demo"},
        )
        connection.commit()

        try:
            connection.execute("UPDATE events SET event_type = ? WHERE event_id = ?", ("changed", event.event_id))
        except sqlite3.IntegrityError as exc:
            assert "append-only" in str(exc)
        else:  # pragma: no cover - should be impossible with trigger installed
            raise AssertionError("events table allowed UPDATE")

        try:
            connection.execute("DELETE FROM events WHERE event_id = ?", (event.event_id,))
        except sqlite3.IntegrityError as exc:
            assert "append-only" in str(exc)
        else:  # pragma: no cover - should be impossible with trigger installed
            raise AssertionError("events table allowed DELETE")
    finally:
        connection.close()


def test_storage_mutating_repositories_write_events(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        repos = RepositoryContext(connection)
        request = FeatureRequest(
            id="fr-trading-software-001",
            source_domain="trading",
            target_domain="software",
            created_by="trading-strategist",
            goal_id="trade_success_quality",
            summary="Need an exportable backtest report.",
        )
        repos.feature_requests.create(request)
        work = WorkItem(
            id="work-001",
            domain="software",
            feature_request_id=request.id,
            assigned_agent="software-builder",
            summary="Build exportable backtest report.",
        )
        repos.work_items.create(work, actor_id="software-techlead")
        lease = ScopeLease(
            id="lease-001",
            work_item_id=work.id,
            agent_id="software-builder",
            domain="software",
            capabilities=("patch.submit",),
            granted_by="control-router",
            status=ScopeLeaseStatus.ACTIVE,
        )
        repos.scope_leases.create(lease, paths=["nexusctl/**", "tests/**"])
        connection.commit()

        assert repos.feature_requests.get(request.id)["summary"] == "Need an exportable backtest report."
        assert repos.count("feature_requests") == 1
        assert [event.event_type for event in repos.events.list_for_aggregate("feature_request", request.id)] == [
            "feature_request.created"
        ]
        assert [event.event_type for event in repos.events.list_for_aggregate("work_item", work.id)] == [
            "work_item.created"
        ]
        assert [event.event_type for event in repos.events.list_for_aggregate("scope_lease", lease.id)] == [
            "scope_lease.created"
        ]
    finally:
        connection.close()


def test_storage_events_include_deterministic_hash_chain(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=False)
        store = EventStore(connection)
        first = store.append(
            aggregate_type="feature_request",
            aggregate_id="fr-001",
            event_type="feature_request.created",
            actor_id="control-router",
            payload={"summary": "demo"},
            occurred_at="2026-05-06T00:00:00Z",
        )
        second = store.append(
            aggregate_type="feature_request",
            aggregate_id="fr-001",
            event_type="feature_request.updated",
            actor_id="control-router",
            payload={"status": "accepted"},
            occurred_at="2026-05-06T00:01:00Z",
        )
        connection.commit()

        assert first.prev_hash == "0" * 64
        assert first.event_hash
        assert second.prev_hash == first.event_hash
        assert second.event_hash != first.event_hash
        assert store.verify_integrity().valid is True
    finally:
        connection.close()


def test_storage_event_integrity_detects_content_tampering(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=False)
        event = EventStore(connection).append(
            aggregate_type="feature_request",
            aggregate_id="fr-001",
            event_type="feature_request.created",
            actor_id="control-router",
            payload={"summary": "demo"},
        )
        connection.commit()

        connection.execute("DROP TRIGGER events_append_only_no_update")
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            ('{"summary":"tampered"}', event.event_id),
        )
        connection.commit()

        report = EventStore(connection).verify_integrity()
        assert report.valid is False
        assert report.checked_events == 1
        assert "event_hash mismatch" in str(report.first_error)
    finally:
        connection.close()


def test_storage_event_hash_chain_survives_repository_service_path(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        repos = RepositoryContext(connection)
        request = FeatureRequest(
            id="fr-trading-software-chain",
            source_domain="trading",
            target_domain="software",
            created_by="trading-strategist",
            goal_id="trade_success_quality",
            summary="Need chain-protected audit event.",
        )
        repos.feature_requests.create(request)
        connection.commit()

        events = repos.events.list_for_aggregate("feature_request", request.id)
        assert len(events) == 1
        assert events[0].prev_hash
        assert events[0].event_hash
        assert repos.events.verify_integrity().valid is True
    finally:
        connection.close()


def test_storage_backup_restore_preserves_core_counts_and_event_integrity(tmp_path: Path) -> None:
    source_db = tmp_path / "nexus.db"
    backup_db = tmp_path / "backups" / "nexus.backup.sqlite3"
    restored_db = tmp_path / "restored" / "nexus.db"
    connection = connect_database(source_db)
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        repos = RepositoryContext(connection)
        request = FeatureRequest(
            id="fr-backup-restore-001",
            source_domain="trading",
            target_domain="software",
            created_by="trading-strategist",
            goal_id="trade_success_quality",
            summary="Need backup/restore smoke coverage.",
        )
        repos.feature_requests.create(request)
        connection.commit()

        from nexusctl.storage.sqlite.backup import create_sqlite_backup, restore_sqlite_backup

        result = create_sqlite_backup(
            connection,
            source_db_path=source_db,
            backup_path=backup_db,
            actor_id="platform-maintainer",
        )
        connection.commit()
        assert result.ok is True
        assert backup_db.is_file()
        assert result.checked_events >= 2
    finally:
        connection.close()

    from nexusctl.storage.sqlite.backup import check_sqlite_backup, restore_sqlite_backup

    check = check_sqlite_backup(backup_db)
    assert check.ok is True
    assert check.counts["feature_requests"] == 1

    restore = restore_sqlite_backup(backup_path=backup_db, target_db_path=restored_db)
    assert restore.ok is True
    assert restore.counts["feature_requests"] == 1

    restored = connect_database(restored_db)
    try:
        assert restored.execute("SELECT summary FROM feature_requests WHERE id = ?", (request.id,)).fetchone()["summary"] == request.summary
        assert EventStore(restored).verify_integrity().valid is True
    finally:
        restored.close()


def test_storage_restore_rejects_missing_or_existing_targets(tmp_path: Path) -> None:
    from nexusctl.domain.errors import ValidationError
    from nexusctl.storage.sqlite.backup import restore_sqlite_backup

    target = tmp_path / "target.db"
    target.write_bytes(b"already here")
    try:
        restore_sqlite_backup(backup_path=tmp_path / "missing.sqlite3", target_db_path=target)
    except ValidationError as exc:
        assert "backup not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing backup to fail")
