from __future__ import annotations

import argparse
import json
from io import StringIO
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.interfaces.cli.output import error_payload, print_json
from nexusctl.storage.event_store import EventStore
from nexusctl.interfaces.cli.runtime import (
    CommandRuntime,
    count_rows,
    finalize_transaction,
    open_ready_database,
    project_root_from_args,
    resolve_token,
)


def test_runtime_resolves_project_root_and_token_precedence() -> None:
    args = argparse.Namespace(project_root="/tmp/project", token="from-arg")

    assert project_root_from_args(args) == Path("/tmp/project")
    assert resolve_token(args, environ={"NEXUSCTL_TOKEN": "from-env"}) == "from-arg"
    assert resolve_token(argparse.Namespace(token=None), environ={"NEXUSCTL_TOKEN": "from-env"}) == "from-env"


def test_open_ready_database_applies_schema_and_seeds_blueprint(tmp_path: Path) -> None:
    args = argparse.Namespace(db=str(tmp_path / "nexus.db"), project_root=str(ROOT))
    connection = open_ready_database(args)
    try:
        assert count_rows(connection, "agents") > 0
        assert count_rows(connection, "domains") > 0
    finally:
        connection.close()


def test_runtime_facade_exposes_shared_dependencies(tmp_path: Path) -> None:
    args = argparse.Namespace(db=str(tmp_path / "nexus.db"), project_root=str(ROOT), token=None)
    runtime = CommandRuntime(args)

    assert runtime.db_path == tmp_path / "nexus.db"
    assert runtime.project_root == ROOT
    assert runtime.capability_matrix().subject_for_agent("control-router").domain == "control"


def test_finalize_transaction_commit_and_rollback(tmp_path: Path) -> None:
    database = tmp_path / "tx.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE items (name TEXT)")
    connection.execute("INSERT INTO items VALUES ('committed')")
    finalize_transaction(connection, commit=True)
    connection.execute("INSERT INTO items VALUES ('rolled-back')")
    finalize_transaction(connection, commit=False)
    rows = [row[0] for row in connection.execute("SELECT name FROM items")]
    connection.close()

    assert rows == ["committed"]


def test_output_json_and_error_payload_are_stable() -> None:
    stream = StringIO()
    print_json({"z": 1, "a": 2}, stream=stream)

    assert json.loads(stream.getvalue()) == {"a": 2, "z": 1}
    assert stream.getvalue().startswith('{"a"')
    assert error_payload(ValueError("bad")) == {
        "ok": False,
        "error": "ValueError",
        "message": "bad",
        "rule_id": None,
    }


def test_command_runtime_context_commits_only_when_marked_success(tmp_path: Path) -> None:
    args = _runtime_args_with_token(tmp_path)
    with CommandRuntime(args) as runtime:
        connection = runtime.require_connection()
        EventStore(connection).append(
            event_id="runtime-rollback-check",
            aggregate_type="runtime",
            aggregate_id="runtime-rollback-check",
            event_type="runtime.test",
            actor_id="control-router",
            occurred_at="2026-05-05T00:00:00Z",
        )
        runtime.mark_success(commit=False)

    connection = sqlite3.connect(tmp_path / "nexus.db")
    try:
        count = connection.execute("SELECT COUNT(*) FROM events WHERE event_id = ?", ("runtime-rollback-check",)).fetchone()[0]
    finally:
        connection.close()
    assert count == 0

    with CommandRuntime(args) as runtime:
        connection = runtime.require_connection()
        EventStore(connection).append(
            event_id="runtime-commit-check",
            aggregate_type="runtime",
            aggregate_id="runtime-commit-check",
            event_type="runtime.test",
            actor_id="control-router",
            occurred_at="2026-05-05T00:00:00Z",
        )
        runtime.mark_success(commit=True)

    connection = sqlite3.connect(tmp_path / "nexus.db")
    try:
        count = connection.execute("SELECT COUNT(*) FROM events WHERE event_id = ?", ("runtime-commit-check",)).fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_command_runtime_rolls_back_on_exception(tmp_path: Path) -> None:
    args = _runtime_args_with_token(tmp_path)
    try:
        with CommandRuntime(args) as runtime:
            connection = runtime.require_connection()
            EventStore(connection).append(
                event_id="runtime-exception-check",
                aggregate_type="runtime",
                aggregate_id="runtime-exception-check",
                event_type="runtime.test",
                actor_id="control-router",
                occurred_at="2026-05-05T00:00:00Z",
            )
            runtime.mark_success(commit=True)
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    connection = sqlite3.connect(tmp_path / "nexus.db")
    try:
        count = connection.execute("SELECT COUNT(*) FROM events WHERE event_id = ?", ("runtime-exception-check",)).fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def _runtime_args_with_token(tmp_path: Path) -> argparse.Namespace:
    db = tmp_path / "nexus.db"
    seed_args = argparse.Namespace(db=str(db), project_root=str(ROOT), token=None)
    connection = open_ready_database(seed_args)
    try:
        credential, _ = AgentTokenRegistry(connection).issue_local_login("control-router")
        connection.commit()
    finally:
        connection.close()
    return argparse.Namespace(db=str(db), project_root=str(ROOT), token=credential.token)


def test_cli_db_backup_restore_commands_smoke(tmp_path: Path, capsys) -> None:
    from nexusctl.interfaces.cli.main import main

    source_db = tmp_path / "nexus.db"
    backup_db = tmp_path / "nexus.backup.sqlite3"
    restored_db = tmp_path / "restored.db"

    assert main(["db", "init", "--db", str(source_db), "--project-root", str(ROOT), "--json"]) == 0
    assert main([
        "db",
        "backup",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--path",
        str(backup_db),
        "--json",
    ]) == 0
    backup_output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert backup_output["ok"] is True
    assert backup_output["backup_path"] == str(backup_db)

    assert main(["db", "restore-check", str(backup_db), "--project-root", str(ROOT), "--json"]) == 0
    check_output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert check_output["ok"] is True
    assert check_output["checked_events"] >= 1

    assert main(["db", "restore", str(backup_db), "--db", str(restored_db), "--json"]) == 0
    restore_output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert restore_output["ok"] is True
    assert restore_output["restored_db"] == str(restored_db)


def test_cli_db_restore_drill_command_reports_recovery_contract(tmp_path: Path, capsys) -> None:
    from nexusctl.interfaces.cli.main import main

    source_db = tmp_path / "nexus.db"
    recovery_dir = tmp_path / "recovery"

    assert main(["db", "init", "--db", str(source_db), "--project-root", str(ROOT), "--json"]) == 0
    assert main([
        "db",
        "restore-drill",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--backup-dir",
        str(recovery_dir),
        "--json",
    ]) == 0
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert output["ok"] is True
    assert Path(output["backup_path"]).is_file()
    assert Path(output["restored_db"]).is_file()
    assert output["checked_events"] >= 1
    assert output["schema_version"] >= 1
    assert output["doctor_status"] == "ok"
    assert output["failed_checks"] == []
    assert output["counts"]["events"] >= 1
    assert output["recovery_evidence"]["restore_drill_status"] == "ok"
    assert output["recovery_evidence"]["backup_path"] == output["backup_path"]
    assert output["recovery_evidence"]["event_chain_status"]["status_code"] == "ok"


def test_cli_db_restore_drill_rejects_empty_external_backup_without_secret_leak(tmp_path: Path, capsys) -> None:
    from nexusctl.interfaces.cli.main import main

    source_db = tmp_path / "nexus.db"
    empty_backup = tmp_path / "empty.backup.sqlite3"
    empty_backup.write_bytes(b"")

    assert main(["db", "init", "--db", str(source_db), "--project-root", str(ROOT), "--json"]) == 0
    exit_code = main([
        "db",
        "restore-drill",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--backup-path",
        str(empty_backup),
        "--json",
    ])
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert exit_code == 4
    assert output["ok"] is False
    assert output["error"] == "ValidationError"
    assert "backup is empty" in output["message"]
    assert output["recovery_evidence"]["restore_drill_status"] == "not_green"
    assert output["recovery_evidence"]["doctor_status"] == "not_run"
    assert output["recovery_evidence"]["failed_checks"][0]["kind"] == "backup_validation"
    assert "secret" not in json.dumps(output).lower()


def test_cli_db_restore_drill_rejects_tampered_event_chain_backup(tmp_path: Path, capsys) -> None:
    from nexusctl.interfaces.cli.main import main

    source_db = tmp_path / "nexus.db"
    backup_db = tmp_path / "nexus.backup.sqlite3"

    assert main(["db", "init", "--db", str(source_db), "--project-root", str(ROOT), "--json"]) == 0
    assert main([
        "db",
        "backup",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--path",
        str(backup_db),
        "--json",
    ]) == 0

    tampered = sqlite3.connect(backup_db)
    try:
        tampered.execute("DROP TRIGGER events_append_only_no_update")
        first_event_id = tampered.execute("SELECT event_id FROM events ORDER BY id LIMIT 1").fetchone()[0]
        tampered.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = ?",
            ('{"summary":"tampered"}', first_event_id),
        )
        tampered.commit()
    finally:
        tampered.close()

    exit_code = main([
        "db",
        "restore-drill",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--backup-path",
        str(backup_db),
        "--json",
    ])
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert exit_code == 4
    assert output["ok"] is False
    assert output["error"] == "ValidationError"
    assert "backup event chain invalid" in output["message"]
    assert "event_hash mismatch" in output["message"]
    assert output["recovery_evidence"]["restore_drill_status"] == "not_green"
    assert output["recovery_evidence"]["event_chain_status"]["status_code"] == "invalid"



def test_cli_db_restore_drill_writes_recovery_evidence_manifest(tmp_path: Path, capsys) -> None:
    from nexusctl.interfaces.cli.main import main

    source_db = tmp_path / "nexus.db"
    recovery_dir = tmp_path / "recovery"
    manifest = tmp_path / "evidence" / "restore-drill.evidence.json"

    assert main(["db", "init", "--db", str(source_db), "--project-root", str(ROOT), "--json"]) == 0
    assert main([
        "db",
        "restore-drill",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--backup-dir",
        str(recovery_dir),
        "--evidence-path",
        str(manifest),
        "--json",
    ]) == 0
    output = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    written = json.loads(manifest.read_text(encoding="utf-8"))

    assert output["recovery_evidence_manifest"]["path"] == str(manifest)
    assert written == output["recovery_evidence"]
    assert written["restore_drill_status"] == "ok"
    assert "secret" not in json.dumps(written).lower()

    exit_code = main([
        "db",
        "restore-drill",
        "--db",
        str(source_db),
        "--project-root",
        str(ROOT),
        "--backup-dir",
        str(recovery_dir),
        "--evidence-path",
        str(manifest),
        "--json",
    ])
    duplicate = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert exit_code == 4
    assert duplicate["error"] == "ValidationError"
    assert "already exists" in duplicate["message"]


def test_cli_db_restore_drill_has_no_user_supplied_restore_target_option() -> None:
    from nexusctl.interfaces.cli.main import build_parser

    parser = build_parser()
    db_parser = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    db_command = db_parser.choices["db"]
    db_subparser = next(
        action for action in db_command._actions if isinstance(action, argparse._SubParsersAction)
    )
    drill_parser = db_subparser.choices["restore-drill"]
    option_dests = {action.dest for action in drill_parser._actions}

    assert "target_db_path" not in option_dests
    assert "overwrite" not in option_dests
