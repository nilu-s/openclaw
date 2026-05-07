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


def copy_project_worktree(tmp_path: Path, marker: str) -> Path:
    worktree = tmp_path / marker
    worktree.mkdir()
    for rel in ["README.md", "nexus/goals.yml"]:
        src = ROOT / rel
        dst = worktree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    readme = worktree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + f"\n{marker}\n", encoding="utf-8")
    return worktree


def create_patch_with_pr(db: Path, tmp_path: Path, *, marker: str = "merge-gate") -> tuple[dict, dict, dict, dict[str, str]]:
    tokens = {
        "trading": login(db, "trading-strategist"),
        "control": login(db, "control-router"),
        "applier": login(db, "merge-applier"),
        "techlead": login(db, "software-techlead"),
        "builder": login(db, "software-builder"),
        "reviewer": login(db, "software-reviewer"),
    }
    created = run_cli([
        "feature-request", "create", "--target", "software", "--goal", "trade_success_quality",
        "--title", f"Need {marker} merge gate", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert created.returncode == 0, created.stderr or created.stdout
    request = json.loads(created.stdout)["feature_request"]

    routed = run_cli([
        "feature-request", "route", request["id"], "--target", "software",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert routed.returncode == 0, routed.stderr or routed.stdout

    issue = run_cli([
        "github", "issue", "sync", request["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert issue.returncode == 0, issue.stderr or issue.stdout

    assigned = run_cli([
        "work", "assign", request["id"], "--builder", "software-builder", "--reviewer", "software-reviewer",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["techlead"]})
    assert assigned.returncode == 0, assigned.stderr or assigned.stdout
    work = json.loads(assigned.stdout)["work"]

    lease = run_cli([
        "scopes", "lease", "--agent", "software-builder", "--request", request["id"],
        "--paths", "README.md,tests/test_merge_gate.py", "--ttl", "2h",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert lease.returncode == 0, lease.stderr or lease.stdout

    worktree = copy_project_worktree(tmp_path, marker)
    submitted = run_cli([
        "patch", "submit", work["id"], "--from-worktree", str(worktree),
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert submitted.returncode == 0, submitted.stderr or submitted.stdout
    patch = json.loads(submitted.stdout)["patch"]

    pr = run_cli([
        "github", "pr", "create", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert pr.returncode == 0, pr.stderr or pr.stdout
    return request, work, patch, tokens


def approve_accept_and_sync(db: Path, request: dict, patch: dict, tokens: dict[str, str]) -> None:
    reviewed = run_cli([
        "review", "submit", patch["id"], "--verdict", "approved", "--notes", "approved for merge-gate",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert reviewed.returncode == 0, reviewed.stderr or reviewed.stdout

    accepted = run_cli([
        "acceptance", "submit", request["id"], "--verdict", "accepted", "--notes", "business accepted",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert accepted.returncode == 0, accepted.stderr or accepted.stdout

    checks = run_cli([
        "github", "checks", "sync", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert checks.returncode == 0, checks.stderr or checks.stdout
    assert json.loads(checks.stdout)["policy_check"]["merge_allowed"] is True


def test_merge_gate_only_applier_merges_after_green_required_checks(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="merge-gate-success")
    approve_accept_and_sync(db, request, patch, tokens)

    builder_merge = run_cli([
        "merge", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert builder_merge.returncode == 3
    assert json.loads(builder_merge.stdout)["rule_id"] in {"capability_not_granted", "merge_only_merge_applier"}

    merged = run_cli([
        "merge", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["applier"]})
    assert merged.returncode == 0, merged.stderr or merged.stdout
    payload = json.loads(merged.stdout)
    assert payload["merge"]["status"] == "merged"
    assert payload["github_merge"]["merged"] is True
    assert payload["policy_check"]["merge_allowed"] is True
    assert all(check["status"] == "passed" for check in payload["required_checks"])
    pr_labels = payload["label_projection"]["pull_request_labels"][0]["labels"]
    assert "status:merged" in pr_labels
    assert "gate:review-approved" in pr_labels

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM merge_records WHERE patch_id = ?", (patch["id"],)).fetchone()["count"] == 1
        assert connection.execute("SELECT status FROM work_items WHERE id = ?", (work["id"],)).fetchone()["status"] == "done"
        assert connection.execute("SELECT status FROM feature_requests WHERE id = ?", (request["id"],)).fetchone()["status"] == "closed"
        assert connection.execute("SELECT status FROM patch_proposals WHERE id = ?", (patch["id"],)).fetchone()["status"] == "merged"
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("patch_proposal", patch["id"])]
        assert "merge.applied" in events
    finally:
        connection.close()


def test_merge_gate_merge_requires_synced_green_checks_and_no_critical_alerts(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, _work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="merge-gate-checks-alert")

    reviewed = run_cli([
        "review", "submit", patch["id"], "--verdict", "approved",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert reviewed.returncode == 0, reviewed.stderr or reviewed.stdout
    accepted = run_cli([
        "acceptance", "submit", request["id"], "--verdict", "accepted",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert accepted.returncode == 0, accepted.stderr or accepted.stdout

    blocked = run_cli([
        "merge", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["applier"]})
    assert blocked.returncode == 3
    assert json.loads(blocked.stdout)["rule_id"] == "required_checks_not_green"

    checks = run_cli([
        "github", "checks", "sync", patch["id"],
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert checks.returncode == 0, checks.stderr or checks.stdout

    connection = connect_database(db)
    try:
        row = connection.execute("SELECT repository_id, pull_number FROM github_pull_links WHERE patch_id = ?", (patch["id"],)).fetchone()
        connection.execute(
            """
            INSERT INTO github_alerts(id, repository_id, pull_number, patch_id, feature_request_id, severity, status, kind, summary)
            VALUES ('alert-merge-gate-critical', ?, ?, ?, ?, 'critical', 'open', 'manual_merge_or_security_alert', 'critical alert blocks merge')
            """,
            (row["repository_id"], row["pull_number"], patch["id"], request["id"]),
        )
        connection.commit()
    finally:
        connection.close()

    alert_blocked = run_cli([
        "merge", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["applier"]})
    assert alert_blocked.returncode == 3
    assert json.loads(alert_blocked.stdout)["rule_id"] == "critical_github_alerts_block_merge"
