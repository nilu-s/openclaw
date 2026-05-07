from __future__ import annotations

import json
from pathlib import Path

from nexusctl.adapters.github.checks import GitHubCheckRunSpec
from nexusctl.adapters.github.client import GitHubPullRequestSpec, GitHubRepositoryRef, MockGitHubClient
from nexusctl.adapters.github.reviews import GitHubPullRequestReviewSpec
from nexusctl.adapters.github.hardening import (
    derive_checks_state,
    derive_review_state,
    evaluate_changed_files_policy,
    parse_github_url,
)
from nexusctl.adapters.github.webhooks import GitHubWebhookEnvelope, compute_signature
from nexusctl.app.reconciliation_service import GitHubReconciliationService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database

from github_fixtures import FIXTURE_ROOT, fixture_body, load_github_fixture, signed_fixture_headers

ROOT = Path(__file__).resolve().parents[1]


def _services(tmp_path: Path):
    connection = connect_database(tmp_path / "nexus.db")
    init_database(connection, ROOT, seed_blueprint=True)
    registry = AgentTokenRegistry(connection)
    matrix = CapabilityMatrix.from_project_root(ROOT)
    policy = PolicyEngine(matrix)
    return connection, registry, policy


def test_github_hardening_github_url_parser_normalizes_common_forms() -> None:
    assert parse_github_url("https://github.com/openclaw/openclaw-nexus").to_json() == {
        "owner": "openclaw",
        "name": "openclaw-nexus",
        "full_name": "openclaw/openclaw-nexus",
        "kind": "repository",
        "number": None,
        "branch": None,
        "path": None,
    }
    assert parse_github_url("git@github.com:openclaw/openclaw-nexus.git").full_name == "openclaw/openclaw-nexus"
    pr = parse_github_url("https://github.com/openclaw/openclaw-nexus/pull/42")
    assert pr.kind == "pull_request"
    assert pr.number == 42
    blob = parse_github_url("https://github.com/openclaw/openclaw-nexus/blob/main/nexus/github.yml")
    assert blob.kind == "blob"
    assert blob.branch == "main"
    assert blob.path == "nexus/github.yml"


def test_github_hardening_derives_external_review_and_check_state_as_non_authoritative() -> None:
    review_state = derive_review_state([
        {"id": 1, "state": "COMMENTED"},
        {"id": 2, "state": "APPROVED"},
    ])
    assert review_state.state == "approved"
    assert review_state.authoritative is False

    check_state = derive_checks_state([
        {"name": "unit", "status": "completed", "conclusion": "success"},
        {"name": "lint", "status": "completed", "conclusion": "failure"},
    ])
    assert check_state.state == "failed"
    assert check_state.authoritative is False
    assert check_state.failed == ("lint",)


def test_github_payload_fixtures_are_secretfree_and_supported_events_are_normalized() -> None:
    fixture_contracts = {
        "issues_labeled.json": "issues",
        "pull_request_closed_merged.json": "pull_request",
        "pull_request_review_submitted.json": "pull_request_review",
        "check_run_completed_failure.json": "check_run",
    }

    for filename, event_name in fixture_contracts.items():
        raw_text = (FIXTURE_ROOT / filename).read_text(encoding="utf-8").lower()
        assert "ghp_" not in raw_text
        assert "github_pat_" not in raw_text
        assert "private_key" not in raw_text

        body = fixture_body(filename)
        envelope = GitHubWebhookEnvelope.from_headers_and_body(
            signed_fixture_headers(event_name, f"delivery-{filename}", body),
            body,
        )
        envelope.validate_supported_event()

        assert envelope.event_name == event_name
        assert envelope.repository_full_name == "openclaw/openclaw-nexus"
        assert envelope.action == load_github_fixture(filename)["action"]
        assert envelope.signature and envelope.signature.startswith("sha256=")


def test_github_fixture_normalizer_contracts_cover_common_field_forms() -> None:
    issue_payload = load_github_fixture("issues_labeled.json")
    assert issue_payload["repository"]["full_name"] == "openclaw/openclaw-nexus"
    assert issue_payload["issue"]["number"] == 42
    assert [label["name"] for label in issue_payload["issue"]["labels"]] == [
        "nexus:FR-2026-0001",
        "domain:trading",
        "status:proposed",
    ]

    pr_payload = load_github_fixture("pull_request_closed_merged.json")
    pull_request = pr_payload["pull_request"]
    assert pull_request["number"] == 17
    assert pull_request["merged"] is True
    assert pull_request["head"]["sha"] == "1111111111111111111111111111111111111111"
    assert [label["name"] for label in pull_request["labels"]] == [
        "nexus:PATCH-2026-0001",
        "status:reviewed",
    ]

    review_payload = load_github_fixture("pull_request_review_submitted.json")
    review_state = derive_review_state([review_payload["review"]])
    assert review_state.to_json() == {
        "state": "approved",
        "authoritative": False,
        "latest_external_id": "777888999",
        "source": "github_projection",
        "details": {"observed_states": ["APPROVED"]},
    }

    check_payload = load_github_fixture("check_run_completed_failure.json")
    check_run = check_payload["check_run"]
    checks_state = derive_checks_state([check_run])
    assert checks_state.to_json() == {
        "state": "failed",
        "authoritative": False,
        "total": 1,
        "failed": ["nexus/policy/fast"],
        "pending": [],
        "passed": [],
    }
    assert check_run["head_sha"] == "1111111111111111111111111111111111111111"
    assert check_run["pull_requests"][0]["number"] == 17


def test_github_fixture_optional_fields_can_be_absent_without_uncontrolled_exceptions() -> None:
    pr_payload = load_github_fixture("pull_request_closed_merged.json")
    pr_payload["repository"].pop("full_name")
    pr_payload["pull_request"].pop("mergeable")
    body = json.dumps(pr_payload, sort_keys=True).encode("utf-8")

    envelope = GitHubWebhookEnvelope.from_headers_and_body(
        signed_fixture_headers("pull_request", "delivery-pr-missing-optional-fields", body),
        body,
    )
    envelope.validate_supported_event()
    assert envelope.repository_full_name is None
    assert envelope.payload["pull_request"]["number"] == 17

    # GitHub may omit app information in reduced test payloads. The normalizer
    # falls back to a deterministic check name instead of crashing.
    check_payload = load_github_fixture("check_run_completed_failure.json")["check_run"]
    check_payload.pop("app")
    check_payload.pop("name")
    checks_state = derive_checks_state([check_payload])
    assert checks_state.failed == ("check-1",)


def test_github_hardening_changed_files_policy_rejects_unsafe_and_out_of_scope_paths() -> None:
    result = evaluate_changed_files_policy(
        ["README.md", "nexus/github.yml", ".github/workflows/deploy.yml"],
        allowed_patterns=["README.md", "nexus/**"],
    )
    assert result.ok is False
    assert result.blocked_paths == (".github/workflows/deploy.yml",)
    assert result.out_of_scope_paths == (".github/workflows/deploy.yml",)

    try:
        evaluate_changed_files_policy(["../secret.txt"])
    except Exception as exc:
        assert "unsafe changed path" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsafe path was accepted")


def test_github_hardening_mock_github_client_covers_projection_state_roundtrip() -> None:
    repo = GitHubRepositoryRef(id="primary", owner="openclaw", name="openclaw-nexus")
    client = MockGitHubClient()
    pr = client.create_or_update_pull_request(
        repo,
        GitHubPullRequestSpec(title="T", body="B", head="nexus/patch", base="main"),
    )
    check = client.create_or_update_check_run(
        repo,
        pr["number"],
        GitHubCheckRunSpec(name="nexus/policy/unit", status="completed", conclusion="success", head_sha=pr["head_sha"], summary="ok"),
    )
    review = client.create_pull_request_review(
        repo,
        pr["number"],
        GitHubPullRequestReviewSpec(event="APPROVE", body="approved", commit_sha=pr["head_sha"]),
    )
    merge = client.merge_pull_request(repo, pr["number"], type("Merge", (), {"method": "squash", "expected_head_sha": pr["head_sha"], "commit_title": "T", "commit_message": "", "details": {}})())

    assert check["mock_status"] == "mock_created"
    assert review["status"] == "mock_created"
    assert merge["merged"] is True
    assert client.pull_requests[("primary", pr["number"])]["merged"] is True


def test_github_hardening_reconciliation_keeps_external_review_non_authoritative_and_alerts(tmp_path: Path) -> None:
    connection, registry, policy = _services(tmp_path)
    try:
        _, nexus_session = registry.issue_local_login("control-router")
        # Unknown external review cannot be mapped to a Nexus review, so it creates an alert
        # instead of changing Nexus review/patch lifecycle state.
        payload = {
            "action": "submitted",
            "repository": {"full_name": "openclaw/openclaw-nexus", "owner": {"login": "openclaw"}, "name": "openclaw-nexus"},
            "pull_request": {"number": 999},
            "review": {"id": 123, "state": "APPROVED"},
        }
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature("secret", body)
        envelope = GitHubWebhookEnvelope.from_headers_and_body(
            {"X-GitHub-Delivery": "github-hardening-delivery", "X-GitHub-Event": "pull_request_review", "X-Hub-Signature-256": signature},
            body,
        )
        service = GitHubReconciliationService(connection, policy, ROOT)
        service.persist_envelope(envelope)
        result = service.reconcile(nexus_session.subject)
        connection.commit()

        assert result["alerts"][0]["kind"] == "unknown_github_pr_review"
        assert connection.execute("SELECT COUNT(*) AS count FROM reviews").fetchone()["count"] == 0
    finally:
        connection.close()
