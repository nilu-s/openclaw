from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.interfaces.cli.main import build_parser, main as cli_main


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


def login(db: Path, agent: str) -> str:
    result = run_cli([
        "auth", "login", "--agent", agent,
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ])
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["credential"]["token"]


def test_cli_commands_build_parser_exposes_extracted_command_groups() -> None:
    help_text = build_parser().format_help()
    for command in ["me", "domains", "goals", "feature-request", "github", "work", "patch", "review", "acceptance", "scopes", "generate", "schedules", "doctor"]:
        assert command in help_text


def test_cli_commands_extracted_me_domains_and_goals_commands_preserve_json_contracts(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-analyst")
    env = {"NEXUSCTL_TOKEN": token}

    me = run_cli(["me", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert me.returncode == 0, me.stderr or me.stdout
    assert json.loads(me.stdout)["identity"]["agent_id"] == "trading-analyst"

    capabilities = run_cli([
        "me", "capabilities", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env=env)
    assert capabilities.returncode == 0, capabilities.stderr or capabilities.stdout
    assert "goal.measure" in json.loads(capabilities.stdout)["capabilities"]

    domains = run_cli(["domains", "list", "--project-root", str(ROOT), "--json"])
    assert domains.returncode == 0, domains.stderr or domains.stdout
    assert {item["id"] for item in json.loads(domains.stdout)["domains"]} >= {"control", "trading", "software"}

    goals = run_cli(["goals", "list", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert goals.returncode == 0, goals.stderr or goals.stdout
    assert {goal["domain"] for goal in json.loads(goals.stdout)["goals"]} == {"trading"}


def test_cli_commands_extracted_schedules_generate_and_doctor_commands_stay_wired(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "platform-maintainer")
    env = {"NEXUSCTL_TOKEN": token}

    schedules = run_cli(["schedules", "validate", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert schedules.returncode == 0, schedules.stderr or schedules.stdout
    assert json.loads(schedules.stdout)["ok"] is True

    generated = run_cli(["generate", "openclaw", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert generated.returncode == 0, generated.stderr or generated.stdout
    assert json.loads(generated.stdout)["kind"] == "openclaw"

    doctor = run_cli(["doctor", "--project-root", str(ROOT), "--db", str(db), "--json"])
    assert doctor.returncode == 0, doctor.stderr or doctor.stdout
    assert json.loads(doctor.stdout)["drift_count"] == 0
