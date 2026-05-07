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


def create_patch_with_pr(db: Path, tmp_path: Path, *, marker: str = "review-acceptance") -> tuple[dict, dict, dict, dict[str, str]]:
    tokens = {
        "trading": login(db, "trading-strategist"),
        "sentinel": login(db, "trading-sentinel"),
        "control": login(db, "control-router"),
        "techlead": login(db, "software-techlead"),
        "builder": login(db, "software-builder"),
        "reviewer": login(db, "software-reviewer"),
    }
    created = run_cli([
        "feature-request", "create", "--target", "software", "--goal", "trade_success_quality",
        "--title", f"Need {marker} review acceptance", "--db", str(db), "--project-root", str(ROOT), "--json",
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
        "--paths", "README.md,tests/test_review_acceptance.py", "--ttl", "2h",
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


def test_review_acceptance_software_reviewer_can_review_but_builder_cannot(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    _request, _work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="review-acceptance-review")

    queue = run_cli([
        "review", "queue", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert queue.returncode == 0, queue.stderr or queue.stdout
    queued = json.loads(queue.stdout)["review_queue"]
    assert [item["patch_id"] for item in queued] == [patch["id"]]

    builder_review = run_cli([
        "review", "submit", patch["id"], "--verdict", "approved",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert builder_review.returncode == 3
    assert json.loads(builder_review.stdout)["rule_id"] in {"capability_not_granted", "builder_no_repo_apply_or_review"}

    reviewed = run_cli([
        "review", "submit", patch["id"], "--verdict", "approved", "--notes", "looks good",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert reviewed.returncode == 0, reviewed.stderr or reviewed.stdout
    review_payload = json.loads(reviewed.stdout)
    assert review_payload["review"]["status"] == "approved"
    assert review_payload["github_pr_review"]["event"] == "APPROVE"
    assert "gate:review-approved" in review_payload["label_projection"]["pull_request_labels"]

    policy = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    gates = {gate["name"]: gate for gate in json.loads(policy.stdout)["policy_check"]["gates"]}
    assert gates["required_review"]["status"] == "passed"
    assert gates["acceptance"]["status"] == "pending"

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM reviews WHERE patch_id = ?", (patch["id"],)).fetchone()["count"] == 1
        assert connection.execute("SELECT COUNT(*) AS count FROM github_pr_review_links WHERE patch_id = ?", (patch["id"],)).fetchone()["count"] == 1
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("patch_proposal", patch["id"])]
        assert "review.submitted" in events
    finally:
        connection.close()


def test_review_acceptance_trading_acceptance_completes_business_gate_not_technical_review(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, _work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="review-acceptance-acceptance")

    reviewer_acceptance = run_cli([
        "acceptance", "submit", request["id"], "--verdict", "accepted",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert reviewer_acceptance.returncode == 3
    assert json.loads(reviewer_acceptance.stdout)["rule_id"] == "capability_not_granted"

    accepted = run_cli([
        "acceptance", "submit", patch["id"], "--verdict", "accepted", "--notes", "domain criteria met",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert accepted.returncode == 0, accepted.stderr or accepted.stdout
    accepted_payload = json.loads(accepted.stdout)
    assert accepted_payload["acceptance"]["status"] == "accepted"
    issue_labels = accepted_payload["label_projection"]["issue_labels"][0]["labels"]
    assert "gate:acceptance-accepted" in issue_labels
    assert "status:accepted" in issue_labels

    policy_before_review = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert policy_before_review.returncode == 0, policy_before_review.stderr or policy_before_review.stdout
    gates = {gate["name"]: gate for gate in json.loads(policy_before_review.stdout)["policy_check"]["gates"]}
    assert gates["acceptance"]["status"] == "passed"
    assert gates["required_review"]["status"] == "pending"

    reviewed = run_cli([
        "review", "submit", patch["id"], "--verdict", "approved",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["reviewer"]})
    assert reviewed.returncode == 0, reviewed.stderr or reviewed.stdout

    green = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert green.returncode == 0, green.stderr or green.stdout
    evaluation = json.loads(green.stdout)["policy_check"]
    assert evaluation["overall_status"] == "passed"
    assert evaluation["merge_allowed"] is True

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM acceptances WHERE feature_request_id = ? AND status = 'accepted'", (request["id"],)).fetchone()["count"] == 1
        assert connection.execute("SELECT COUNT(*) AS count FROM github_projection_labels").fetchone()["count"] >= 2
    finally:
        connection.close()


def test_review_acceptance_trading_sentinel_safety_veto_blocks_merge_gate(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, _work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="review-acceptance-veto")

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

    veto = run_cli([
        "acceptance", "submit", request["id"], "--verdict", "vetoed", "--notes", "risk limit breached",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["sentinel"]})
    assert veto.returncode == 0, veto.stderr or veto.stdout
    veto_payload = json.loads(veto.stdout)
    assert veto_payload["acceptance"]["status"] == "vetoed"
    assert veto_payload["acceptance_status"]["effective_status"] == "vetoed"

    blocked = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert blocked.returncode == 0, blocked.stderr or blocked.stdout
    evaluation = json.loads(blocked.stdout)["policy_check"]
    gates = {gate["name"]: gate for gate in evaluation["gates"]}
    assert gates["acceptance"]["status"] == "passed"
    assert gates["no_safety_veto"]["status"] == "failed"
    assert evaluation["merge_allowed"] is False

    status = run_cli([
        "acceptance", "status", request["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["sentinel"]})
    assert json.loads(status.stdout)["acceptance_status"]["latest_safety_veto"]["submitted_by"] == "trading-sentinel"
