from __future__ import annotations

import pytest

from nexusctl.backend.storage import SessionContext, Storage, initialize_database, seed_mvp_data



pytestmark = pytest.mark.unit
TOKENS = {
    "nexus-01": "tok_nexus",
    "trading-strategist-01": "tok_trading",
    "sw-architect-01": "tok_architect",
    "sw-techlead-01": "tok_techlead",
    "sw-builder-01": "tok_builder",
    "sw-reviewer-01": "tok_reviewer",
}


def actor(agent_id: str, role: str, default_system_id: str = "software-domain", domain: str = "Software") -> SessionContext:
    return SessionContext(session_id=f"S-{agent_id}", agent_id=agent_id, role=role, default_system_id=default_system_id, domain=domain)


def test_builder_and_reviewer_assignments_are_separate(tmp_path):
    db_path = tmp_path / "nexus.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TOKENS)
    storage = Storage(db_path)

    strategist = actor("trading-strategist-01", "trading-strategist", "trading-system", "Trading")
    nexus = actor("nexus-01", "nexus", "trading-system", "Control")
    architect = actor("sw-architect-01", "sw-architect")
    techlead = actor("sw-techlead-01", "sw-techlead")
    builder = actor("sw-builder-01", "sw-builder")
    reviewer = actor("sw-reviewer-01", "sw-reviewer")

    created = storage.create_request(
        actor=strategist,
        objective="Implement deterministic risk limit checker",
        missing_capability="Risk limit checker is missing",
        business_impact="Reduces exposure during volatile periods",
        expected_behavior="Orders are blocked when threshold is breached",
        acceptance_criteria=["Given a breached threshold, new orders are rejected."],
        risk_class="high",
        priority="P1",
        goal_ref="trading-goal://risk/limit-hard-stop",
    )
    request_id = created["request_id"]
    storage.transition_request(actor=nexus, request_id=request_id, to_status="accepted", reason="Accepted for software planning.")
    planned = storage.plan_work(
        actor=architect,
        request_id=request_id,
        repo_id="trading-engine",
        branch="feature/req-risk-checker",
        assigned_agent_id="sw-builder-01",
        reviewer_agent_id="sw-reviewer-01",
        sanitized_summary="Implement deterministic risk limit checker",
    )

    assert planned["assigned_agent_id"] == "sw-builder-01"
    assert planned["reviewer_agent_id"] == "sw-reviewer-01"

    assert storage.show_work(actor=builder, request_id=request_id)["assigned_agent_id"] == "sw-builder-01"
    assert storage.show_work(actor=reviewer, request_id=request_id)["reviewer_agent_id"] == "sw-reviewer-01"

    storage.set_implementation_context(
        actor=architect,
        request_id=request_id,
        implementation_context={
            "component": "risk",
            "likely_files": ["src/trading_engine/risk/check_order.py"],
            "acceptance_criteria": ["Risk breach blocks new orders."],
            "test_commands": ["pytest tests/risk/test_check_order.py"],
        },
    )
    storage.approve_work_plan(actor=techlead, request_id=request_id)
    review = storage.submit_review(actor=reviewer, request_id=request_id, verdict="changes-requested", summary="Need a failing risk-threshold regression test.")
    assert review["verdict"] == "changes-requested"

    try:
        storage.submit_review(actor=builder, request_id=request_id, verdict="approved", summary="Builder cannot self-review.")
    except Exception as exc:
        assert getattr(exc, "code", None) in {"NX-PERM-001", "NX-PRECONDITION-001"}
    else:
        raise AssertionError("builder must not be able to submit its own review")


def test_unresolved_goal_ref_is_rejected(tmp_path):
    db_path = tmp_path / "nexus.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TOKENS)
    storage = Storage(db_path)

    try:
        storage.create_request(
            actor=actor("trading-strategist-01", "trading-strategist", "trading-system", "Trading"),
            objective="Implement an unknown capability",
            missing_capability="Unknown goal wiring is missing",
            business_impact="Would create untraceable work",
            expected_behavior="Request creation is blocked",
            acceptance_criteria=["Unknown goal refs are rejected."],
            risk_class="medium",
            priority="P2",
            goal_ref="trading-goal://does/not/exist",
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "NX-PRECONDITION-001"
    else:
        raise AssertionError("unresolved goal_ref should be rejected")
