from __future__ import annotations

import pytest

import sqlite3

from nexusctl.backend.storage import SessionContext, Storage, initialize_database, seed_mvp_data



pytestmark = pytest.mark.unit
def _seed_tokens() -> dict[str, str]:
    return {
        "main-01": "tok_main",
        "nexus-01": "tok_nexus",
        "sw-architect-01": "tok_architect",
        "trading-strategist-01": "tok_trading",
        "trading-analyst-01": "tok_analyst",
        "trading-sentinel-01": "tok_sentinel",
        "sw-techlead-01": "tok_techlead",
        "sw-builder-01": "tok_builder",
        "sw-reviewer-01": "tok_reviewer",
    }


def _strategist_actor() -> SessionContext:
    return SessionContext(
        session_id="S-2026-0001",
        agent_id="trading-strategist-01",
        role="trading-strategist",
        default_system_id="trading-system",
        domain="Trading",
    )


def _nexus_actor() -> SessionContext:
    return SessionContext(
        session_id="S-2026-0002",
        agent_id="nexus-01",
        role="nexus",
        default_system_id="trading-system",
        domain="Control",
    )


def test_request_lifecycle_keeps_github_issue_metadata_outside_request_row(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=_seed_tokens())
    storage = Storage(db_path)

    created = storage.create_request(
        actor=_strategist_actor(),
        objective="Need paper execution simulator",
        missing_capability="CAP-PT-001 paper execution simulator",
        business_impact="No executable paper trades possible",
        expected_behavior="Simulated order lifecycle is deterministic",
        acceptance_criteria=["Given order submit, fill lifecycle is persisted"],
        risk_class="high",
        priority="P1",
        goal_ref="trading-goal://g-001/paper-baseline",
    )
    assert "issue_ref" not in created
    assert "handoff_id" not in created

    transitioned = storage.transition_request(
        actor=_nexus_actor(),
        request_id=created["request_id"],
        to_status="accepted",
        reason="Gate accepted for software planning.",
    )
    assert transitioned["to_status"] == "accepted"

    listed = storage.list_requests(actor=_nexus_actor(), status_filter="accepted", limit=10)
    assert len(listed["requests"]) == 1
    assert "issue_ref" not in listed["requests"][0]

    conn = sqlite3.connect(db_path)
    try:
        request_columns = {row[1] for row in conn.execute("PRAGMA table_info(requests)").fetchall()}
    finally:
        conn.close()
    assert "github_issue_url" not in request_columns
    assert "github_pr_url" not in request_columns
