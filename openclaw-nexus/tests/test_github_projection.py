from __future__ import annotations

import json
from pathlib import Path

from nexusctl.adapters.github.app_auth import GitHubAppConfig
from nexusctl.adapters.github.client import MockGitHubClient
from nexusctl.app.feature_request_service import FeatureRequestService
from nexusctl.app.github_service import GitHubService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database

ROOT = Path(__file__).resolve().parents[1]


def _services(tmp_path: Path):
    connection = connect_database(tmp_path / "nexus.db")
    init_database(connection, ROOT, seed_blueprint=True)
    registry = AgentTokenRegistry(connection)
    matrix = CapabilityMatrix.from_project_root(ROOT)
    policy = PolicyEngine(matrix)
    return connection, registry, policy


def test_github_app_status_uses_mock_mode_without_credentials(tmp_path: Path) -> None:
    connection, registry, policy = _services(tmp_path)
    try:
        _, nexus_session = registry.issue_local_login("control-router")
        client = MockGitHubClient()
        service = GitHubService(connection, policy, ROOT, client=client)
        status = service.app_status(nexus_session.subject)
        assert status["github_app"]["mock_mode"] is True
        assert status["github_app"]["credentials_required_for_local_tests"] is False
        assert status["github_app"]["agents_receive_github_tokens"] is False
        assert status["github_app"]["role"] == "projection"
        assert status["github_app"]["lifecycle_authority"] is False
    finally:
        connection.close()


def test_repositories_and_labels_sync_from_github_yml(tmp_path: Path) -> None:
    connection, registry, policy = _services(tmp_path)
    try:
        _, nexus_session = registry.issue_local_login("control-router")
        client = MockGitHubClient()
        service = GitHubService(connection, policy, ROOT, client=client)
        repos = service.sync_repositories(nexus_session.subject)
        labels = service.sync_labels(nexus_session.subject)
        connection.commit()

        assert repos["repositories"][0]["full_name"] == "openclaw/openclaw-nexus"
        label_names = {label["name"] for label in labels["labels"]}
        assert {"domain:software", "target:software", "status:proposed"}.issubset(label_names)
        assert connection.execute("SELECT COUNT(*) AS count FROM github_repositories").fetchone()["count"] >= 1
        event_types = [event.event_type for event in EventStore(connection).list_recent(limit=10)]
        assert "github.repositories.synced" in event_types
        assert "github.labels.synced" in event_types
    finally:
        connection.close()


def test_feature_request_projects_to_github_issue_with_contract_sections(tmp_path: Path) -> None:
    connection, registry, policy = _services(tmp_path)
    try:
        _, strategist_session = registry.issue_local_login("trading-strategist")
        _, nexus_session = registry.issue_local_login("control-router")
        feature_requests = FeatureRequestService(connection, policy)
        request = feature_requests.create(
            strategist_session.subject,
            target_domain="software",
            goal_id="trade_success_quality",
            title="Need projected risk dashboard issue",
        )

        client = MockGitHubClient()
        github = GitHubService(connection, policy, ROOT, client=client)
        projected = github.sync_feature_request_issue(nexus_session.subject, request["id"])
        connection.commit()

        issue = projected["github_issue"]
        assert issue["repository"] == "openclaw/openclaw-nexus"
        assert issue["issue_number"] == 1
        assert f"nexus:{request['id']}" in issue["labels"]
        assert "domain:trading" in issue["labels"]
        assert "target:software" in issue["labels"]
        assert "status:proposed" in issue["labels"]
        assert "## Acceptance Contract" in issue["body"]
        assert "## Safety Contract" in issue["body"]
        assert "GitHub is a projection only" in issue["body"]

        row = connection.execute(
            "SELECT * FROM github_issue_links WHERE feature_request_id = ?", (request["id"],)
        ).fetchone()
        assert row is not None
        assert row["repository_id"] == "primary"
        assert row["issue_number"] == 1
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("feature_request", request["id"])]
        assert "feature_request.created" in events
        assert "github.issue.synced" in events
    finally:
        connection.close()


def test_issue_sync_is_idempotent_for_existing_feature_request_link(tmp_path: Path) -> None:
    connection, registry, policy = _services(tmp_path)
    try:
        _, strategist_session = registry.issue_local_login("trading-strategist")
        _, nexus_session = registry.issue_local_login("control-router")
        request = FeatureRequestService(connection, policy).create(
            strategist_session.subject,
            target_domain="software",
            goal_id="trade_success_quality",
            title="Need idempotent GitHub issue projection",
        )
        client = MockGitHubClient()
        github = GitHubService(connection, policy, ROOT, client=client)
        first = github.sync_feature_request_issue(nexus_session.subject, request["id"])
        second = github.sync_feature_request_issue(nexus_session.subject, request["id"])
        connection.commit()

        assert second["github_issue"]["id"] == first["github_issue"]["id"]
        assert second["github_issue"]["issue_number"] == first["github_issue"]["issue_number"]
        assert second["github_issue"]["mock_status"] == "mock_updated"
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM github_issue_links WHERE feature_request_id = ?", (request["id"],)
        ).fetchone()["count"]
        assert count == 1
    finally:
        connection.close()


def test_github_repo_sync_capability_is_reserved_to_nexusctl_actor() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    engine = PolicyEngine(matrix)
    nexus = matrix.subject_for_agent("control-router")
    strategist = matrix.subject_for_agent("trading-strategist")

    assert engine.authorize(nexus, "github.repo.sync", resource_domain="software").allowed
    assert not engine.authorize(strategist, "github.repo.sync", resource_domain="software").allowed


def test_github_app_config_reports_missing_credentials_without_blocking_mock() -> None:
    config = GitHubAppConfig.from_env({})
    status = config.status()
    assert status["mode"] == "mock"
    assert status["mock_mode"] is True
    assert set(status["missing_credentials"]) >= {
        "GITHUB_APP_ID",
        "GITHUB_APP_INSTALLATION_ID",
        "GITHUB_APP_PRIVATE_KEY_PATH",
    }
