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

from nexusctl.adapters.github.webhooks import compute_signature
from nexusctl.interfaces.cli.main import main as cli_main
from nexusctl.interfaces.http.routes import handle_github_webhook
from nexusctl.storage.sqlite.connection import connect_database
from github_fixtures import TEST_WEBHOOK_SECRET, load_github_fixture


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


def create_projected_issue(db: Path) -> tuple[dict, dict, str]:
    tokens = {"trading": login(db, "trading-strategist"), "control": login(db, "control-router")}
    created = run_cli([
        "feature-request", "create", "--target", "software", "--goal", "trade_success_quality",
        "--title", "Need webhook-reconciliation webhook reconciliation", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert created.returncode == 0, created.stderr or created.stdout
    request = json.loads(created.stdout)["feature_request"]
    issue = run_cli([
        "github", "issue", "sync", request["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert issue.returncode == 0, issue.stderr or issue.stdout
    return request, json.loads(issue.stdout)["github_issue"], tokens["control"]


def signed_headers(event: str, delivery: str, body: bytes, secret: str) -> dict[str, str]:
    return {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": compute_signature(secret, body),
    }


def fixture_webhook_body(name: str, *, pull_number: int | None = None, issue_number: int | None = None, head_sha: str | None = None) -> bytes:
    payload = load_github_fixture(name)
    if issue_number is not None and isinstance(payload.get("issue"), dict):
        payload["issue"]["number"] = issue_number
    if pull_number is not None:
        payload["number"] = pull_number
        if isinstance(payload.get("pull_request"), dict):
            payload["pull_request"]["number"] = pull_number
        check = payload.get("check_run")
        if isinstance(check, dict) and isinstance(check.get("pull_requests"), list):
            for pr in check["pull_requests"]:
                if isinstance(pr, dict):
                    pr["number"] = pull_number
    if head_sha is not None:
        if isinstance(payload.get("pull_request"), dict):
            payload["pull_request"].setdefault("head", {})["sha"] = head_sha
        if isinstance(payload.get("review"), dict):
            payload["review"]["commit_id"] = head_sha
        if isinstance(payload.get("check_run"), dict):
            payload["check_run"]["head_sha"] = head_sha
            for pr in payload["check_run"].get("pull_requests", []):
                if isinstance(pr, dict):
                    pr.setdefault("head", {})["sha"] = head_sha
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def test_webhooks_cli_verifies_hmac_signature(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    nexus_token = login(db, "control-router")
    body = '{"zen":"webhook-reconciliation"}'
    signature = compute_signature("secret-13", body)

    verified = run_cli([
        "github", "webhook", "verify",
        "--payload", body,
        "--signature", signature,
        "--secret", "secret-13",
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": nexus_token})
    assert verified.returncode == 0, verified.stderr or verified.stdout
    payload = json.loads(verified.stdout)
    assert payload["verified"] is True
    assert payload["signature_algorithm"] == "hmac-sha256"


def test_webhooks_http_webhook_persists_idempotently_and_reconciles_issue_labels(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    secret = "secret-13"
    request, issue, nexus_token = create_projected_issue(db)
    body = json.dumps({
        "action": "labeled",
        "repository": {"owner": {"login": "openclaw"}, "name": "openclaw-nexus", "full_name": "openclaw/openclaw-nexus"},
        "issue": {
            "number": issue["issue_number"],
            "labels": [{"name": "manual:drift"}, {"name": "status:wrong"}],
        },
    }, sort_keys=True).encode("utf-8")

    connection = connect_database(db)
    try:
        first = handle_github_webhook(
            connection,
            project_root=ROOT,
            headers=signed_headers("issues", "delivery-webhook-reconciliation-issue", body, secret),
            body=body,
            secret=secret,
        )
        assert first.status == 202, first.body
        assert first.body["webhook"]["duplicate"] is False
        duplicate = handle_github_webhook(
            connection,
            project_root=ROOT,
            headers=signed_headers("issues", "delivery-webhook-reconciliation-issue", body, secret),
            body=body,
            secret=secret,
        )
        assert duplicate.status == 202, duplicate.body
        assert duplicate.body["webhook"]["duplicate"] is True
        assert connection.execute("SELECT COUNT(*) AS count FROM github_webhook_events").fetchone()["count"] == 1
    finally:
        connection.close()

    reconciled = run_cli([
        "github", "reconcile", "--limit", "10", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": nexus_token})
    assert reconciled.returncode == 0, reconciled.stderr or reconciled.stdout
    payload = json.loads(reconciled.stdout)
    assert payload["processed_count"] == 1
    assert payload["alerts"][0]["kind"] == "github_label_drift_reconciled"

    connection = connect_database(db)
    try:
        webhook = connection.execute("SELECT * FROM github_webhook_events WHERE delivery_id = 'delivery-webhook-reconciliation-issue'").fetchone()
        assert webhook["processing_status"] == "alerted"
        labels_row = connection.execute(
            "SELECT labels_json FROM github_projection_labels WHERE entity_kind = 'issue' AND nexus_entity_id = ?",
            (request["id"],),
        ).fetchone()
        labels = json.loads(labels_row["labels_json"])
        assert labels == sorted([
            f"nexus:{request['id']}",
            "domain:trading",
            "target:software",
            "status:proposed",
        ])
        events = connection.execute(
            "SELECT event_type FROM events WHERE aggregate_type = 'feature_request' AND aggregate_id = ? ORDER BY id",
            (request["id"],),
        ).fetchall()
        assert "github.issue.reconciled" in [row["event_type"] for row in events]
    finally:
        connection.close()


def test_webhooks_pull_request_webhook_detects_head_sha_drift_and_unauthorized_merge(tmp_path: Path) -> None:
    from test_merge_gate import create_patch_with_pr

    db = tmp_path / "nexus.db"
    request, _work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="webhook-reconciliation-pr")
    connection = connect_database(db)
    try:
        pr = connection.execute("SELECT * FROM github_pull_links WHERE patch_id = ?", (patch["id"],)).fetchone()
        old_state = connection.execute("SELECT * FROM github_pull_states WHERE patch_id = ?", (patch["id"],)).fetchone()
        body = fixture_webhook_body(
            "pull_request_closed_merged.json",
            pull_number=pr["pull_number"],
            head_sha="changed-head-sha-webhook-reconciliation",
        )
        response = handle_github_webhook(
            connection,
            project_root=ROOT,
            headers=signed_headers("pull_request", "delivery-webhook-reconciliation-pr", body, "secret-13"),
            body=body,
            secret="secret-13",
        )
        assert response.status == 202, response.body
        connection.commit()
    finally:
        connection.close()

    reconciled = run_cli([
        "github", "reconcile", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert reconciled.returncode == 0, reconciled.stderr or reconciled.stdout
    alert_kinds = {alert["kind"] for alert in json.loads(reconciled.stdout)["alerts"]}
    assert "github_pr_head_sha_changed" in alert_kinds
    assert "unauthorized_github_merge" in alert_kinds

    policy = run_cli([
        "policy", "check", patch["id"], "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert policy.returncode == 0, policy.stderr or policy.stdout
    gates = {gate["name"]: gate for gate in json.loads(policy.stdout)["policy_check"]["gates"]}
    assert gates["head_sha_matches_validated_patch"]["status"] == "failed"

    connection = connect_database(db)
    try:
        new_state = connection.execute("SELECT * FROM github_pull_states WHERE patch_id = ?", (patch["id"],)).fetchone()
        assert old_state["head_sha"] != new_state["head_sha"]
        assert new_state["head_sha"] == "changed-head-sha-webhook-reconciliation"
        critical = connection.execute(
            "SELECT COUNT(*) AS count FROM github_alerts WHERE patch_id = ? AND severity = 'critical' AND status = 'open'",
            (patch["id"],),
        ).fetchone()["count"]
        assert critical == 1
    finally:
        connection.close()


def test_webhooks_fixture_review_and_check_signals_do_not_become_nexus_authority(tmp_path: Path) -> None:
    from test_merge_gate import create_patch_with_pr

    db = tmp_path / "nexus.db"
    _request, _work, patch, tokens = create_patch_with_pr(db, tmp_path, marker="webhook-fixture-signals")
    connection = connect_database(db)
    try:
        pr = connection.execute("SELECT * FROM github_pull_links WHERE patch_id = ?", (patch["id"],)).fetchone()
        prior_patch_status = connection.execute("SELECT status FROM patch_proposals WHERE id = ?", (patch["id"],)).fetchone()["status"]
        review_body = fixture_webhook_body(
            "pull_request_review_submitted.json",
            pull_number=pr["pull_number"],
            head_sha="1111111111111111111111111111111111111111",
        )
        check_body = fixture_webhook_body(
            "check_run_completed_failure.json",
            pull_number=pr["pull_number"],
            head_sha="1111111111111111111111111111111111111111",
        )
        for event, delivery, body in (
            ("pull_request_review", "delivery-fixture-review", review_body),
            ("check_run", "delivery-fixture-check-failure", check_body),
        ):
            response = handle_github_webhook(
                connection,
                project_root=ROOT,
                headers=signed_headers(event, delivery, body, TEST_WEBHOOK_SECRET),
                body=body,
                secret=TEST_WEBHOOK_SECRET,
            )
            assert response.status == 202, response.body
        connection.commit()
    finally:
        connection.close()

    reconciled = run_cli([
        "github", "reconcile", "--limit", "10", "--db", str(db), "--project-root", str(ROOT), "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert reconciled.returncode == 0, reconciled.stderr or reconciled.stdout
    payload = json.loads(reconciled.stdout)
    assert payload["processed_count"] == 2
    alert_kinds = {alert["kind"] for alert in payload["alerts"]}
    assert "external_github_review_ignored" in alert_kinds
    assert "external_github_check_failed" in alert_kinds

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM reviews WHERE patch_id = ?", (patch["id"],)).fetchone()["count"] == 0
        assert connection.execute("SELECT status FROM patch_proposals WHERE id = ?", (patch["id"],)).fetchone()["status"] == prior_patch_status
        check = connection.execute(
            "SELECT * FROM github_check_runs WHERE patch_id = ? AND name = 'nexus/policy/fast'",
            (patch["id"],),
        ).fetchone()
        assert check is not None
        assert check["status"] == "completed"
        assert check["conclusion"] == "failure"
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM github_alerts WHERE patch_id = ? AND severity = 'critical'",
            (patch["id"],),
        ).fetchone()["count"] == 0
    finally:
        connection.close()


def test_webhooks_duplicate_delivery_with_changed_body_is_rejected(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, issue, _nexus_token = create_projected_issue(db)
    secret = "secret-13"
    first_body = json.dumps({
        "action": "labeled",
        "repository": {"owner": {"login": "openclaw"}, "name": "openclaw-nexus", "full_name": "openclaw/openclaw-nexus"},
        "issue": {"number": issue["issue_number"], "labels": [{"name": "manual:drift"}]},
    }, sort_keys=True).encode("utf-8")
    changed_body = json.dumps({
        "action": "labeled",
        "repository": {"owner": {"login": "openclaw"}, "name": "openclaw-nexus", "full_name": "openclaw/openclaw-nexus"},
        "issue": {"number": issue["issue_number"], "labels": [{"name": "different:drift"}]},
    }, sort_keys=True).encode("utf-8")

    connection = connect_database(db)
    try:
        first = handle_github_webhook(
            connection,
            project_root=ROOT,
            headers=signed_headers("issues", "delivery-conflict", first_body, secret),
            body=first_body,
            secret=secret,
        )
        assert first.status == 202, first.body
        conflict = handle_github_webhook(
            connection,
            project_root=ROOT,
            headers=signed_headers("issues", "delivery-conflict", changed_body, secret),
            body=changed_body,
            secret=secret,
        )
        assert conflict.status == 400
        assert "conflicting GitHub webhook delivery" in conflict.body["error"]
        assert secret not in json.dumps(conflict.body)
        assert connection.execute("SELECT COUNT(*) AS count FROM github_webhook_events WHERE delivery_id = 'delivery-conflict'").fetchone()["count"] == 1
    finally:
        connection.close()


def test_webhooks_reconcile_does_not_replay_processed_delivery_or_duplicate_alerts(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, issue, nexus_token = create_projected_issue(db)
    secret = "secret-13"
    body = json.dumps({
        "action": "labeled",
        "repository": {"owner": {"login": "openclaw"}, "name": "openclaw-nexus", "full_name": "openclaw/openclaw-nexus"},
        "issue": {"number": issue["issue_number"], "labels": [{"name": "manual:drift"}]},
    }, sort_keys=True).encode("utf-8")

    connection = connect_database(db)
    try:
        received = handle_github_webhook(
            connection,
            project_root=ROOT,
            headers=signed_headers("issues", "delivery-no-replay", body, secret),
            body=body,
            secret=secret,
        )
        assert received.status == 202, received.body
        row = connection.execute("SELECT processing_status FROM github_webhook_events WHERE delivery_id = 'delivery-no-replay'").fetchone()
        assert row["processing_status"] == "pending"
        connection.commit()
    finally:
        connection.close()

    first = run_cli(["github", "reconcile", "--limit", "10", "--db", str(db), "--project-root", str(ROOT), "--json"], env={"NEXUSCTL_TOKEN": nexus_token})
    assert first.returncode == 0, first.stderr or first.stdout
    assert json.loads(first.stdout)["processed_count"] == 1

    second = run_cli(["github", "reconcile", "--limit", "10", "--db", str(db), "--project-root", str(ROOT), "--json"], env={"NEXUSCTL_TOKEN": nexus_token})
    assert second.returncode == 0, second.stderr or second.stdout
    assert json.loads(second.stdout)["processed_count"] == 0

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS count FROM github_alerts WHERE kind = 'github_label_drift_reconciled'").fetchone()["count"] == 1
    finally:
        connection.close()
