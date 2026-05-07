from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.app.recovery_evidence import EVIDENCE_VERSION, RecoveryEvidenceBuilder
from nexusctl.app.restore_drill_service import RestoreDrillService
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database


def test_recovery_evidence_builds_green_secret_free_payload_from_restore_drill(tmp_path: Path) -> None:
    source_db = tmp_path / "nexus.db"
    connection = connect_database(source_db)
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        connection.commit()

        drill = RestoreDrillService(connection, source_db_path=source_db, project_root=ROOT).run(
            backup_dir=tmp_path / "restore-drills",
            actor_id="platform-maintainer",
        )
        evidence = RecoveryEvidenceBuilder.from_restore_drill(
            source_db=source_db,
            restore_drill=drill,
            generated_at="2026-05-06T00:00:00Z",
        ).to_json()
    finally:
        connection.close()

    json.dumps(evidence)
    assert evidence["evidence_version"] == EVIDENCE_VERSION
    assert evidence["generated_at"] == "2026-05-06T00:00:00Z"
    assert evidence["source_db"] == str(source_db)
    assert evidence["backup_path"] == drill["backup_path"]
    assert evidence["backup_checksum"]
    assert evidence["schema_version"] >= 1
    assert evidence["latest_schema_version"] >= evidence["schema_version"]
    assert evidence["event_chain_status"]["status_code"] == "ok"
    assert evidence["checked_events"] >= 1
    assert evidence["doctor_status"] == "ok"
    assert evidence["failed_checks"] == []
    assert evidence["counts"]["events"] >= 1
    assert evidence["restore_drill_status"] == "ok"
    assert evidence["retention_status"]["status_code"] == "not_configured"
    assert evidence["offsite_status"]["status_code"] == "not_configured"
    boundaries = evidence["operator_control_boundaries"]
    assert "doctor_status" in boundaries["local_product_evidence"]
    assert "restore_drill_to_fresh_database" in boundaries["local_product_evidence"]
    assert "offsite_replication" in boundaries["external_operator_controls"]
    assert "worm_or_object_lock" in boundaries["external_operator_controls"]
    assert "monitoring_and_paging" in boundaries["external_operator_controls"]
    assert "failed_checks_not_empty" in boundaries["incident_triggers"]


def test_recovery_evidence_marks_event_chain_failure_not_green() -> None:
    drill = {
        "ok": False,
        "backup_path": "/tmp/nexus.backup.sqlite3",
        "checked_events": 7,
        "schema_version": 13,
        "counts": {"events": 7},
        "doctor_status": "drift",
        "failed_checks": [
            {
                "kind": "event_integrity",
                "status_code": "invalid",
                "summary": "event_hash mismatch at event 7",
            }
        ],
    }

    evidence = RecoveryEvidenceBuilder.from_restore_drill(
        source_db="/tmp/nexus.db",
        restore_drill=drill,
        generated_at="2026-05-06T00:00:00Z",
    ).to_json()

    assert evidence["restore_drill_status"] == "not_green"
    assert evidence["event_chain_status"] == {
        "status_code": "invalid",
        "valid": False,
        "checked_events": 7,
        "summary": "event_hash mismatch at event 7",
    }
    assert evidence["failed_checks"][0]["kind"] == "event_integrity"


def test_recovery_evidence_redacts_secret_markers_and_secret_keys() -> None:
    drill = {
        "ok": False,
        "backup_path": "/tmp/nexus.backup.sqlite3",
        "checked_events": 0,
        "schema_version": 13,
        "doctor_status": "critical",
        "failed_checks": [
            {
                "kind": "operational_readiness",
                "status_code": "warning",
                "summary": "do not leak ghp_example or real-secret values",
                "webhook_secret": "super-secret-value",
            }
        ],
    }

    evidence = RecoveryEvidenceBuilder.from_restore_drill(
        source_db="/tmp/nexus.db",
        restore_drill=drill,
        retention_status={"status_code": "configured", "token": "hidden-token"},
        offsite_status={"status_code": "configured", "private_key": "hidden-key"},
    ).to_json()
    serialized = json.dumps(evidence)

    assert "ghp_" not in serialized
    assert "real-secret" not in serialized
    assert "super-secret-value" not in serialized
    assert "hidden-token" not in serialized
    assert "hidden-key" not in serialized
    assert evidence["failed_checks"][0]["webhook_secret"] == "[redacted]"
    assert evidence["retention_status"]["token"] == "[redacted]"
    assert evidence["offsite_status"]["private_key"] == "[redacted]"
    assert "operator_control_boundaries" in evidence
