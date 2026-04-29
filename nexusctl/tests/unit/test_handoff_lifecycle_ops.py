from __future__ import annotations

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
    return SessionContext(
        session_id="S-2026-0001",
        agent_id="trading-strategist-01",
        role="trading-strategist",
        project_id="trading-system",
        domain="Trading",
    )


def _nexus_actor() -> SessionContext:
    return SessionContext(
        session_id="S-2026-0002",
        agent_id="nexus-01",
        role="nexus",
        project_id="trading-system",
        domain="Control",
    )


def test_handoff_submit_keeps_issue_unset_until_nexus_links_it(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=_seed_tokens())
    storage = Storage(db_path)

    created = storage.submit_handoff(
        actor=_strategist_actor(),
        objective="Need paper execution simulator",
        missing_capability="CAP-PT-001 paper execution simulator",
        business_impact="No executable paper trades possible",
        expected_behavior="Simulated order lifecycle is deterministic",
        acceptance_criteria=["Given order submit, fill lifecycle is persisted"],
        risk_class="high",
        priority="P1",
        trading_goals_ref="trading-goal://g-001/paper-baseline",
    )
    assert created["issue_ref"] == "none"

    linked = storage.set_handoff_issue(
        actor=_nexus_actor(),
        handoff_id=created["handoff_id"],
        issue_ref="issue://github/mawly-engineer/trading-system#42",
        issue_number=42,
        issue_url="https://github.com/mawly-engineer/trading-system/issues/42",
    )
    assert linked["ok"] is True
    assert linked["issue_ref"] == "issue://github/mawly-engineer/trading-system#42"

    listed = storage.list_handoffs(status_filter="submitted", limit=10)
    assert len(listed["handoffs"]) == 1
    assert listed["handoffs"][0]["issue_ref"] == "issue://github/mawly-engineer/trading-system#42"

