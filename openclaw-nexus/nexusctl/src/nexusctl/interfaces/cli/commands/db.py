"""Database maintenance CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from nexusctl.domain.errors import ValidationError
from nexusctl.interfaces.cli.output import error_payload
from nexusctl.interfaces.cli.commands.common import add_runtime_args, emit_payload
from nexusctl.interfaces.cli.runtime import db_path_from_args, open_ready_database
from nexusctl.app.backup_service import BackupService
from nexusctl.app.restore_drill_service import RestoreDrillService
from nexusctl.app.recovery_evidence import RecoveryEvidenceBuilder, write_recovery_evidence_manifest


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    db_parser = subparsers.add_parser("db", help="database maintenance commands")
    db_subparsers = db_parser.add_subparsers(dest="db_command")

    init_parser = db_subparsers.add_parser("init", help="initialize nexus.db from nexus/*.yml")
    init_parser.add_argument("--db", default="nexus.db", help="SQLite database path")
    init_parser.add_argument("--project-root", default=".", help="project root containing nexus/*.yml")
    init_parser.add_argument("--json", action="store_true", help="emit machine-readable output")

    backup_parser = db_subparsers.add_parser("backup", help="create a verified SQLite backup")
    add_runtime_args(backup_parser)
    backup_parser.add_argument("--path", dest="backup_path", help="backup file path; defaults beside the source DB")
    backup_parser.add_argument("--actor", default=None, help="known agent id recorded in backup metadata")
    backup_parser.add_argument("--json", action="store_true")

    check_parser = db_subparsers.add_parser("restore-check", help="verify a backup before restore")
    add_runtime_args(check_parser)
    check_parser.add_argument("backup_path", help="backup file path to verify")
    check_parser.add_argument("--json", action="store_true")

    restore_parser = db_subparsers.add_parser("restore", help="restore a verified backup into a target DB")
    restore_parser.add_argument("backup_path", help="backup file path to restore")
    restore_parser.add_argument("--db", required=True, help="target SQLite database path")
    restore_parser.add_argument("--overwrite", action="store_true", help="replace an existing target DB")
    restore_parser.add_argument("--json", action="store_true")

    drill_parser = db_subparsers.add_parser("restore-drill", help="run a verified backup/restore/doctor drill")
    add_runtime_args(drill_parser)
    drill_parser.add_argument("--backup-dir", help="directory for generated backup and restored drill DB")
    drill_parser.add_argument("--backup-path", help="existing backup file to drill instead of creating a new backup")
    drill_parser.add_argument("--actor", default=None, help="known agent id recorded when the drill creates a backup")
    drill_parser.add_argument("--evidence-path", help="write the recovery evidence manifest to this JSON file")
    drill_parser.add_argument("--overwrite-evidence", action="store_true", help="replace an existing recovery evidence manifest file")
    drill_parser.add_argument("--json", action="store_true")


def handle(args: argparse.Namespace) -> int:
    if args.db_command == "backup":
        connection = open_ready_database(args)
        try:
            payload = BackupService(connection, db_path=db_path_from_args(args)).create(
                backup_path=getattr(args, "backup_path", None),
                actor_id=getattr(args, "actor", None),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return emit_payload(args, {"backup": payload, **payload})

    if args.db_command == "restore-check":
        payload = BackupService().check(args.backup_path)
        return emit_payload(args, {"restore_check": payload, **payload})

    if args.db_command == "restore":
        payload = BackupService().restore(
            backup_path=args.backup_path,
            target_db_path=args.db,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        return emit_payload(args, {"restore": payload, **payload})

    if args.db_command == "restore-drill":
        connection = open_ready_database(args)
        try:
            try:
                payload = RestoreDrillService(
                    connection,
                    source_db_path=db_path_from_args(args),
                    project_root=args.project_root,
                ).run(
                    backup_dir=getattr(args, "backup_dir", None),
                    backup_path=getattr(args, "backup_path", None),
                    actor_id=getattr(args, "actor", None),
                )
            except ValidationError as exc:
                connection.rollback()
                payload = _failed_restore_drill_payload(args, exc)
                _write_evidence_manifest_if_requested(args, payload)
                emit_payload(args, {"restore_drill": payload, **payload})
                return 4
            _write_evidence_manifest_if_requested(args, payload)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        emit_payload(args, {"restore_drill": payload, **payload})
        return 0 if payload.get("ok") else 1

    return 2


def _write_evidence_manifest_if_requested(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    evidence_path = getattr(args, "evidence_path", None)
    if not evidence_path:
        return
    evidence = payload.get("recovery_evidence")
    if not isinstance(evidence, dict):
        raise ValidationError("restore drill did not produce recovery evidence")
    payload["recovery_evidence_manifest"] = write_recovery_evidence_manifest(
        evidence=evidence,
        target_path=evidence_path,
        overwrite=bool(getattr(args, "overwrite_evidence", False)),
    )


def _failed_restore_drill_payload(args: argparse.Namespace, exc: ValidationError) -> dict[str, Any]:
    backup_path = str(getattr(args, "backup_path", None) or "")
    summary = str(exc)
    kind = "event_integrity" if "event chain" in summary.lower() else "backup_validation"
    status_code = "invalid"
    payload: dict[str, Any] = {
        "ok": False,
        "backup_path": backup_path,
        "restored_db": "",
        "checked_events": 0,
        "schema_version": 0,
        "counts": {},
        "doctor_status": "not_run",
        "failed_checks": [
            {
                "kind": kind,
                "status_code": status_code,
                "summary": summary,
            }
        ],
        **error_payload(exc),
    }
    payload["recovery_evidence"] = RecoveryEvidenceBuilder.from_restore_drill(
        source_db=db_path_from_args(args),
        restore_drill=payload,
    ).to_json()
    return payload
