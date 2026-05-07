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


def create_assigned_work_and_lease(db: Path) -> tuple[dict, dict, dict[str, str]]:
    tokens = {
        "trading": login(db, "trading-strategist"),
        "control": login(db, "control-router"),
        "techlead": login(db, "software-techlead"),
        "builder": login(db, "software-builder"),
    }
    created = run_cli([
        "feature-request", "create", "--target", "software", "--goal", "trade_success_quality",
        "--title", "Need patch proposal support", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert created.returncode == 0, created.stderr or created.stdout
    request = json.loads(created.stdout)["feature_request"]
    routed = run_cli([
        "feature-request", "route", request["id"], "--target", "software",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert routed.returncode == 0, routed.stderr or routed.stdout
    request = json.loads(routed.stdout)["feature_request"]
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
        "--paths", "nexusctl/src/**,tests/test_patch_proposals.py,README.md", "--ttl", "2h",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert lease.returncode == 0, lease.stderr or lease.stdout
    return request, work, tokens


def copy_project_worktree(tmp_path: Path) -> Path:
    worktree = tmp_path / "candidate"
    worktree.mkdir()
    for rel in ["README.md", "nexus/goals.yml"]:
        src = ROOT / rel
        dst = worktree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return worktree


def test_patch_proposals_builder_submits_scoped_patch_and_nexus_creates_pr(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, work, tokens = create_assigned_work_and_lease(db)
    worktree = copy_project_worktree(tmp_path)
    target = worktree / "README.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nPatch proposal candidate change.\n", encoding="utf-8")

    started = run_cli([
        "work", "start", work["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert started.returncode == 0, started.stderr or started.stdout
    assert json.loads(started.stdout)["work_start"]["worktree"]["branch"].startswith("nexus/")

    submitted = run_cli([
        "patch", "submit", work["id"], "--from-worktree", str(worktree),
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert submitted.returncode == 0, submitted.stderr or submitted.stdout
    patch = json.loads(submitted.stdout)["patch"]
    assert patch["work_item_id"] == work["id"]
    assert patch["feature_request_id"] == request["id"]
    assert patch["changed_paths"] == ["README.md"]
    assert patch["status"] == "submitted"

    builder_pr = run_cli([
        "github", "pr", "create", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert builder_pr.returncode == 3
    assert json.loads(builder_pr.stdout)["rule_id"] in {"builder_no_repo_apply_or_review", "capability_not_granted"}

    pr = run_cli([
        "github", "pr", "create", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert pr.returncode == 0, pr.stderr or pr.stdout
    github_pr = json.loads(pr.stdout)["github_pr"]
    assert github_pr["pull_number"] == 1
    assert github_pr["branch"].startswith("nexus/")
    assert github_pr["branch_projection"]["canonical_repo_mutated"] is False

    connection = connect_database(db)
    try:
        row = connection.execute("SELECT patch_id, branch, pull_number FROM github_pull_links WHERE patch_id = ?", (patch["id"],)).fetchone()
        assert row["patch_id"] == patch["id"]
        assert row["pull_number"] == 1
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("patch_proposal", patch["id"])]
        assert "patch.submitted" in events
        assert "github.pr.created" in events
    finally:
        connection.close()


def test_patch_proposals_patch_outside_scope_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    _request, work, tokens = create_assigned_work_and_lease(db)
    worktree = copy_project_worktree(tmp_path)
    forbidden = worktree / "nexus" / "goals.yml"
    forbidden.write_text(forbidden.read_text(encoding="utf-8") + "\n# out of scope\n", encoding="utf-8")

    submitted = run_cli([
        "patch", "submit", work["id"], "--from-worktree", str(worktree),
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert submitted.returncode == 3
    error = json.loads(submitted.stdout)
    assert error["rule_id"] == "scope_path_bound"

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM patch_proposals").fetchone()["count"] == 0
    finally:
        connection.close()
