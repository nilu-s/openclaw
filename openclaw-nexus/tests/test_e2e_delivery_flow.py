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

from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.interfaces.cli.main import main as cli_main


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


def copy_project_worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "e2e-delivery-worktree"
    worktree.mkdir()
    for rel in ["README.md", "nexus/goals.yml"]:
        src = ROOT / rel
        dst = worktree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    readme = worktree / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n\nMVP demo capability note: trading-quality gap analysis is auditable through Nexusctl.\n",
        encoding="utf-8",
    )
    return worktree


def test_e2e_delivery_full_trading_to_software_to_merge_audit_chain(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    tokens = {
        "analyst": login(db, "trading-analyst"),
        "strategist": login(db, "trading-strategist"),
        "control": login(db, "control-router"),
        "architect": login(db, "software-architect"),
        "techlead": login(db, "software-techlead"),
        "builder": login(db, "software-builder"),
        "reviewer": login(db, "software-reviewer"),
        "applier": login(db, "merge-applier"),
        "platform": login(db, "platform-maintainer"),
    }

    evidence_file = tmp_path / "trade_success_quality_gap.json"
    evidence_file.write_text(
        json.dumps(
            {
                "source": "e2e-delivery-e2e-demo",
                "detected_gap": "missing capability for auditable post-trade quality attribution",
                "measurements": {
                    "win_rate": 58,
                    "average_profit_pct": 4.6,
                    "max_drawdown_pct": 13.4,
                    "min_sample_size": 72,
                },
            }
        ),
        encoding="utf-8",
    )

    added = run_cli([
        "evidence", "add", "--goal", "trade_success_quality", "--file", str(evidence_file),
        "--summary", "MVP demo: goal quality gap indicates missing software capability",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["analyst"]})
    assert added.returncode == 0, added.stderr or added.stdout
    evidence = json.loads(added.stdout)["evidence"]
    assert "win_rate" in evidence["measurement_keys"]

    measured = run_cli([
        "goals", "measure", "trade_success_quality",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["analyst"]})
    assert measured.returncode == 0, measured.stderr or measured.stdout

    evaluated = run_cli([
        "goals", "evaluate", "trade_success_quality",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["analyst"]})
    assert evaluated.returncode == 0, evaluated.stderr or evaluated.stdout
    evaluation = json.loads(evaluated.stdout)["evaluation"]
    assert evaluation["status"] == "failing"
    assert set(evaluation["details"]["failed_metrics"]) >= {"win_rate", "max_drawdown_pct"}

    created = run_cli([
        "feature-request", "create", "--target", "software", "--goal", "trade_success_quality",
        "--title", "Add auditable trade quality attribution capability",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["strategist"]})
    assert created.returncode == 0, created.stderr or created.stdout
    request = json.loads(created.stdout)["feature_request"]
    assert request["source_domain"] == "trading"
    assert request["target_domain"] == "software"

    issue = run_cli([
        "github", "issue", "sync", request["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert issue.returncode == 0, issue.stderr or issue.stdout
    assert json.loads(issue.stdout)["github_issue"]["issue_number"] >= 1

    routed = run_cli([
        "feature-request", "route", request["id"], "--target", "software",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert routed.returncode == 0, routed.stderr or routed.stdout

    planned = run_cli([
        "work", "plan", request["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["architect"]})
    assert planned.returncode == 0, planned.stderr or planned.stdout
    assert json.loads(planned.stdout)["work"]["feature_request_id"] == request["id"]

    assigned = run_cli([
        "work", "assign", request["id"], "--builder", "software-builder", "--reviewer", "software-reviewer",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["techlead"]})
    assert assigned.returncode == 0, assigned.stderr or assigned.stdout
    work = json.loads(assigned.stdout)["work"]

    denied_lease = run_cli([
        "scopes", "lease", "--agent", "trading-analyst", "--request", request["id"],
        "--paths", "README.md", "--ttl", "1h",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert denied_lease.returncode == 3
    assert json.loads(denied_lease.stdout)["rule_id"] == "trading_cannot_receive_software_lease"

    lease = run_cli([
        "scopes", "lease", "--agent", "software-builder", "--request", request["id"],
        "--paths", "README.md,tests/test_e2e_delivery_flow.py", "--ttl", "2h",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert lease.returncode == 0, lease.stderr or lease.stdout

    worktree = copy_project_worktree(tmp_path)
    submitted = run_cli([
        "patch", "submit", work["id"], "--from-worktree", str(worktree),
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert submitted.returncode == 0, submitted.stderr or submitted.stdout
    patch = json.loads(submitted.stdout)["patch"]
    assert patch["changed_paths"] == ["README.md"]

    pr = run_cli([
        "github", "pr", "create", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert pr.returncode == 0, pr.stderr or pr.stdout
    assert json.loads(pr.stdout)["github_pr"]["pull_number"] >= 1

    checks_pending = run_cli([
        "github", "checks", "sync", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert checks_pending.returncode == 0, checks_pending.stderr or checks_pending.stdout
    assert json.loads(checks_pending.stdout)["policy_check"]["merge_allowed"] is False

    reviewed = run_cli([
        "review", "submit", patch["id"], "--verdict", "approved", "--notes", "e2e-delivery technical review approved",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert reviewed.returncode == 0, reviewed.stderr or reviewed.stdout

    accepted = run_cli([
        "acceptance", "submit", request["id"], "--verdict", "accepted", "--notes", "e2e-delivery trading acceptance complete",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["strategist"]})
    assert accepted.returncode == 0, accepted.stderr or accepted.stdout

    checks_green = run_cli([
        "github", "checks", "sync", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert checks_green.returncode == 0, checks_green.stderr or checks_green.stdout
    policy_check = json.loads(checks_green.stdout)["policy_check"]
    assert policy_check["overall_status"] == "passed"
    assert policy_check["merge_allowed"] is True

    blocked_builder_merge = run_cli([
        "merge", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert blocked_builder_merge.returncode == 3

    merged = run_cli([
        "merge", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["applier"]})
    assert merged.returncode == 0, merged.stderr or merged.stdout
    merge_payload = json.loads(merged.stdout)
    assert merge_payload["merge"]["status"] == "merged"
    assert merge_payload["github_merge"]["merged"] is True
    assert all(check["status"] == "passed" for check in merge_payload["required_checks"])

    generated = run_cli([
        "generate", "all",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["platform"]})
    assert generated.returncode == 0, generated.stderr or generated.stdout
    assert json.loads(generated.stdout)["artifact_count"] >= 120

    connection = connect_database(db)
    try:
        counts = {
            "evidence": connection.execute("SELECT COUNT(*) AS c FROM evidence").fetchone()["c"],
            "feature_requests": connection.execute("SELECT COUNT(*) AS c FROM feature_requests").fetchone()["c"],
            "work_items": connection.execute("SELECT COUNT(*) AS c FROM work_items").fetchone()["c"],
            "scope_leases": connection.execute("SELECT COUNT(*) AS c FROM scope_leases").fetchone()["c"],
            "patch_proposals": connection.execute("SELECT COUNT(*) AS c FROM patch_proposals").fetchone()["c"],
            "reviews": connection.execute("SELECT COUNT(*) AS c FROM reviews").fetchone()["c"],
            "acceptances": connection.execute("SELECT COUNT(*) AS c FROM acceptances").fetchone()["c"],
            "merge_records": connection.execute("SELECT COUNT(*) AS c FROM merge_records").fetchone()["c"],
        }
        assert counts == {
            "evidence": 1,
            "feature_requests": 1,
            "work_items": 1,
            "scope_leases": 1,
            "patch_proposals": 1,
            "reviews": 1,
            "acceptances": 1,
            "merge_records": 1,
        }
        patch_events = [event.event_type for event in EventStore(connection).list_for_aggregate("patch_proposal", patch["id"])]
        assert patch_events == [
            "patch.submitted",
            "github.pr.created",
            "github.checks.synced",
            "review.submitted",
            "github.checks.synced",
            "merge.applied",
        ]
        request_events = [event.event_type for event in EventStore(connection).list_for_aggregate("feature_request", request["id"])]
        assert "feature_request.created" in request_events
        assert "github.issue.synced" in request_events
        assert "feature_request.routed" in request_events
        assert "feature_request.merged" in request_events
        assert connection.execute("SELECT status FROM feature_requests WHERE id = ?", (request["id"],)).fetchone()["status"] == "closed"
    finally:
        connection.close()
