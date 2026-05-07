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
        "auth", "login", "--agent", agent,
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ])
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["credential"]["token"]


def copy_project_worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "candidate"
    worktree.mkdir()
    for rel in ["README.md", "nexus/goals.yml"]:
        src = ROOT / rel
        dst = worktree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return worktree


def create_patch_with_pr(db: Path, tmp_path: Path) -> tuple[dict, dict, dict, dict[str, str]]:
    tokens = {
        "trading": login(db, "trading-strategist"),
        "control": login(db, "control-router"),
        "techlead": login(db, "software-techlead"),
        "builder": login(db, "software-builder"),
        "reviewer": login(db, "software-reviewer"),
    }
    created = run_cli([
        "feature-request", "create", "--target", "software", "--goal", "trade_success_quality",
        "--title", "Need policy gates", "--db", str(db), "--project-root", str(ROOT), "--json",
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
        "--paths", "README.md,tests/test_policy_checks.py", "--ttl", "2h",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert lease.returncode == 0, lease.stderr or lease.stdout

    worktree = copy_project_worktree(tmp_path)
    readme = worktree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nPolicy gate candidate change.\n", encoding="utf-8")

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
    github_pr = json.loads(pr.stdout)["github_pr"]
    assert github_pr["validated_patch_sha"] == github_pr["head_sha"]
    return request, work, patch, tokens


def test_policy_checks_policy_check_reports_pending_required_gates_and_syncs_github_checks(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    _request, _work, patch, tokens = create_patch_with_pr(db, tmp_path)

    policy = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert policy.returncode == 0, policy.stderr or policy.stdout
    evaluation = json.loads(policy.stdout)["policy_check"]
    gates = {gate["name"]: gate for gate in evaluation["gates"]}
    assert gates["scope_respected"]["status"] == "passed"
    assert gates["required_review"]["status"] == "pending"
    assert gates["acceptance"]["status"] == "pending"
    assert gates["no_safety_veto"]["status"] == "passed"
    assert gates["head_sha_matches_validated_patch"]["status"] == "passed"
    assert evaluation["merge_allowed"] is False
    assert evaluation["overall_status"] == "pending"

    builder_sync = run_cli([
        "github", "checks", "sync", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert builder_sync.returncode == 3
    assert json.loads(builder_sync.stdout)["rule_id"] in {"capability_not_granted", "normal_agents_no_cross_domain_mutation"}

    synced = run_cli([
        "github", "checks", "sync", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert synced.returncode == 0, synced.stderr or synced.stdout
    payload = json.loads(synced.stdout)
    assert len(payload["github_checks"]) == 5
    assert {check["name"] for check in payload["github_checks"]} == {
        "nexus/policy/scope_respected",
        "nexus/policy/required_review",
        "nexus/policy/acceptance",
        "nexus/policy/no_safety_veto",
        "nexus/policy/head_sha_matches_validated_patch",
    }

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM policy_checks WHERE patch_id = ?", (patch["id"],)).fetchone()["count"] == 5
        assert connection.execute("SELECT COUNT(*) AS count FROM github_check_runs WHERE patch_id = ?", (patch["id"],)).fetchone()["count"] == 5
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("patch_proposal", patch["id"])]
        assert "github.checks.synced" in events
    finally:
        connection.close()


def test_policy_checks_changed_pr_head_sha_after_approval_blocks_policy_gate(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, work, patch, tokens = create_patch_with_pr(db, tmp_path)

    connection = connect_database(db)
    try:
        connection.execute(
            """
            INSERT INTO reviews(id, work_item_id, patch_id, reviewer_agent_id, status, verdict, notes)
            VALUES ('review-policy-ok', ?, ?, 'software-reviewer', 'approved', 'approved', 'validator approved')
            """,
            (work["id"], patch["id"]),
        )
        connection.execute(
            """
            INSERT INTO acceptances(id, feature_request_id, submitted_by, status, notes)
            VALUES ('acceptance-policy-ok', ?, 'trading-strategist', 'accepted', 'validator accepted')
            """,
            (request["id"],),
        )
        connection.commit()
    finally:
        connection.close()

    green = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert green.returncode == 0, green.stderr or green.stdout
    green_eval = json.loads(green.stdout)["policy_check"]
    assert green_eval["overall_status"] == "passed"
    assert green_eval["merge_allowed"] is True

    connection = connect_database(db)
    try:
        connection.execute("UPDATE github_pull_states SET head_sha = ? WHERE patch_id = ?", ("0" * 40, patch["id"]))
        connection.commit()
    finally:
        connection.close()

    changed = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert changed.returncode == 0, changed.stderr or changed.stdout
    changed_eval = json.loads(changed.stdout)["policy_check"]
    gates = {gate["name"]: gate for gate in changed_eval["gates"]}
    assert gates["head_sha_matches_validated_patch"]["status"] == "failed"
    assert "head_sha_matches_validated_patch" in changed_eval["failed_gates"]
    assert changed_eval["merge_allowed"] is False
