from __future__ import annotations

import sqlite3

from nexusctl.backend.storage import SessionContext, Storage, initialize_database, seed_mvp_data


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
    return SessionContext("S-1", "trading-strategist-01", "trading-strategist", "trading-system", "Trading")


def _nexus_actor() -> SessionContext:
    return SessionContext("S-2", "nexus-01", "nexus", "trading-system", "Control")


def test_request_create_has_no_embedded_github_metadata(tmp_path):
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
    assert "github_" + "issue_url" not in created
    storage.transition_request(actor=_nexus_actor(), request_id=created["request_id"], to_status="accepted", reason="accepted")

    listed = storage.list_requests(actor=_nexus_actor(), status_filter="accepted", limit=10)
    assert len(listed["requests"]) == 1
    assert "issue_ref" not in listed["requests"][0]

    conn = sqlite3.connect(db_path)
    try:
        request_columns = {row[1] for row in conn.execute("PRAGMA table_info(requests)").fetchall()}
    finally:
        conn.close()
    assert "github_" + "issue_url" not in request_columns
    assert "github_" + "pr_url" not in request_columns
