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

from nexusctl.interfaces.cli.main import main as cli_main
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.connection import connect_database


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
        "auth",
        "login",
        "--agent",
        agent,
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ])
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["credential"]["token"]


def test_goals_trading_agent_can_measure_evaluate_and_audit_evidence(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-analyst")
    env = {"NEXUSCTL_TOKEN": token}
    evidence_file = tmp_path / "trade_success_quality.json"
    evidence_file.write_text(
        json.dumps(
            {
                "source": "goals-test-backtest",
                "measurements": {
                    "win_rate": 63,
                    "average_profit_pct": 5.8,
                    "max_drawdown_pct": 9.5,
                    "min_sample_size": 81,
                },
            }
        ),
        encoding="utf-8",
    )

    add = run_cli([
        "evidence",
        "add",
        "--goal",
        "trade_success_quality",
        "--file",
        str(evidence_file),
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env=env)
    assert add.returncode == 0, add.stderr or add.stdout
    evidence = json.loads(add.stdout)["evidence"]
    assert evidence["goal_id"] == "trade_success_quality"
    assert set(evidence["measurement_keys"]) >= {"win_rate", "max_drawdown_pct"}

    measure = run_cli([
        "goals",
        "measure",
        "trade_success_quality",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env=env)
    assert measure.returncode == 0, measure.stderr or measure.stdout
    measurement = json.loads(measure.stdout)["measurement"]
    assert len(measurement["measurements"]) == 4
    assert {item["metric_id"] for item in measurement["measurements"]} == {
        "win_rate", "average_profit_pct", "max_drawdown_pct", "min_sample_size"
    }
    assert all(item["known"] for item in measurement["measurements"])

    evaluate = run_cli([
        "goals",
        "evaluate",
        "trade_success_quality",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env=env)
    assert evaluate.returncode == 0, evaluate.stderr or evaluate.stdout
    evaluation = json.loads(evaluate.stdout)["evaluation"]
    assert evaluation["status"] == "passing"
    assert evaluation["details"]["failed_metrics"] == []

    status = run_cli([
        "goals",
        "status",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env=env)
    assert status.returncode == 0, status.stderr
    body = json.loads(status.stdout)
    assert body["visible_domain"] == "trading"
    assert body["goals"][0]["evaluation_status"] == "passing"

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS c FROM evidence").fetchone()["c"] == 1
        assert connection.execute("SELECT COUNT(*) AS c FROM goal_measurements").fetchone()["c"] == 4
        assert connection.execute("SELECT COUNT(*) AS c FROM goal_evaluations").fetchone()["c"] == 1
        goal_events = [e.event_type for e in EventStore(connection).list_for_aggregate("goal", "trade_success_quality")]
        assert "goal.evidence_referenced" in goal_events
        assert "goal.measured" in goal_events
        assert "goal.evaluated" in goal_events
    finally:
        connection.close()


def test_goals_goal_visibility_is_domain_scoped_for_normal_agents(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "software-techlead")
    env = {"NEXUSCTL_TOKEN": token}

    visible = run_cli([
        "goals",
        "list",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env=env)
    assert visible.returncode == 0, visible.stderr
    body = json.loads(visible.stdout)
    assert body["visible_domain"] == "software"
    assert {goal["domain"] for goal in body["goals"]} == {"software"}

    denied = run_cli([
        "goals",
        "show",
        "trade_success_quality",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env=env)
    assert denied.returncode == 3
    assert json.loads(denied.stdout)["rule_id"] == "goal_visibility_own_domain_only"


def test_goals_goal_evaluation_can_be_warning_or_unknown(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-analyst")
    env = {"NEXUSCTL_TOKEN": token}

    warning_measure = run_cli([
        "goals",
        "measure",
        "trade_success_quality",
        "--value", "win_rate=58",
        "--value", "average_profit_pct=4.7",
        "--value", "max_drawdown_pct=12.5",
        "--value", "min_sample_size=49",
        "--db", str(db),
        "--project-root", str(ROOT),
        "--json",
    ], env=env)
    assert warning_measure.returncode == 0, warning_measure.stderr or warning_measure.stdout
    warning_eval = run_cli([
        "goals", "evaluate", "trade_success_quality",
        "--db", str(db),
        "--project-root", str(ROOT),
        "--json",
    ], env=env)
    assert warning_eval.returncode == 0, warning_eval.stderr or warning_eval.stdout
    assert json.loads(warning_eval.stdout)["evaluation"]["status"] == "warning"

    db2 = tmp_path / "unknown.db"
    token2 = login(db2, "trading-analyst")
    unknown_eval = run_cli([
        "goals", "evaluate", "trade_success_quality",
        "--db", str(db2),
        "--project-root", str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": token2})
    assert unknown_eval.returncode == 0, unknown_eval.stderr or unknown_eval.stdout
    assert json.loads(unknown_eval.stdout)["evaluation"]["status"] == "unknown"
