from __future__ import annotations

import sqlite3

import pytest

from nexusctl.backend.integrations.github import FakeGitHubClient
from nexusctl.backend.storage import SessionContext, Storage, initialize_database, seed_mvp_data
from nexusctl.errors import NexusError

pytestmark = pytest.mark.unit

TOKENS = {
    "nexus-01": "tok_nexus",
    "sw-architect-01": "tok_architect",
    "trading-strategist-01": "tok_trading",
    "sw-techlead-01": "tok_techlead",
    "sw-builder-01": "tok_builder",
    "sw-reviewer-01": "tok_reviewer",
}


def actor(agent_id: str, role: str, default_system_id: str = "software-domain", domain: str = "Software") -> SessionContext:
    return SessionContext(session_id=f"S-{agent_id}", agent_id=agent_id, role=role, default_system_id=default_system_id, domain=domain)


def make_storage(tmp_path):
    db_path = tmp_path / "nexus.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TOKENS)
    return Storage(db_path, github_client=FakeGitHubClient()), db_path


def test_invalid_auth_attempts_are_rate_limited(tmp_path):
    storage, _db_path = make_storage(tmp_path)
    for _ in range(5):
        with pytest.raises(NexusError):
            storage.authenticate(agent_token="bad-token")
    with pytest.raises(NexusError) as excinfo:
        storage.authenticate(agent_token="bad-token")
    assert excinfo.value.code == "NX-PERM-002"


def test_token_rotation_revokes_sessions_and_returns_new_token(tmp_path):
    storage, _db_path = make_storage(tmp_path)
    session = storage.authenticate(agent_token="tok_builder")
    nexus = actor("nexus-01", "nexus", "trading-system", "Control")
    rotated = storage.rotate_agent_token(actor=nexus, target_agent_id="sw-builder-01")
    assert rotated["agent_id"] == "sw-builder-01"
    assert len(rotated["new_token"]) >= 24
    with pytest.raises(NexusError):
        storage.validate_session(session["session_id"])
    assert storage.authenticate(agent_token=rotated["new_token"])["agent_id"] == "sw-builder-01"


def test_manual_override_requires_distinct_second_approver(tmp_path):
    storage, _db_path = make_storage(tmp_path)
    strategist = actor("trading-strategist-01", "trading-strategist", "trading-system", "Trading")
    techlead = actor("sw-techlead-01", "sw-techlead")
    request = storage.create_request(
        actor=strategist,
        objective="Need manual override test.",
        missing_capability="Override gate hardening.",
        business_impact="Avoid single-person bypass.",
        expected_behavior="Override requires second approver.",
        acceptance_criteria=["Override is dual-controlled."],
        risk_class="high",
        priority="P1",
        goal_ref="trading-goal://risk/limit-hard-stop",
    )
    request_id = request["request_id"]
    storage.transition_request(actor=actor("nexus-01", "nexus", "trading-system", "Control"), request_id=request_id, to_status="accepted", reason="Accepted for planning.")
    with pytest.raises(NexusError):
        storage.transition_work(actor=techlead, request_id=request_id, to_status="needs-planning", reason="Manual override with durable evidence context.", override=True)
    result = storage.transition_work(actor=techlead, request_id=request_id, to_status="needs-planning", reason="Manual override with durable evidence context.", override=True, approved_by="nexus-01")
    assert result["override"] is True
    assert result["approved_by"] == "nexus-01"


def test_dead_letter_creates_alert(tmp_path):
    storage, db_path = make_storage(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO github_events(event_id, delivery_id, event_type, action, request_id, repo_id, github_owner, github_repo, payload_json, received_at, processing_status)
            VALUES ('evt-1', 'delivery-1', 'pull_request', 'synchronize', 'missing-request', 'trading-engine', 'local', 'trading-engine', '{}', '2026-01-01T00:00:00Z', 'queued')
        """)
    processed = storage.process_queued_github_events(limit=1)
    assert processed["dead_letter"]
    alerts = storage.list_github_alerts(actor=actor("sw-techlead-01", "sw-techlead"))["alerts"]
    assert any(item["kind"] == "webhook_dead_letter" for item in alerts)
