from __future__ import annotations

import sqlite3

from nexusctl.backend.integrations.github import FakeGitHubClient
from nexusctl.backend.storage import SessionContext, Storage, initialize_database, seed_mvp_data


TOKENS = {
    "nexus-01": "tok_nexus",
    "sw-architect-01": "tok_architect",
    "trading-strategist-01": "tok_trading",
    "sw-techlead-01": "tok_techlead",
    "sw-builder-01": "tok_builder",
}


def actor(agent_id: str, role: str, default_system_id: str = "software-domain", domain: str = "Software") -> SessionContext:
    return SessionContext(session_id=f"S-{agent_id}", agent_id=agent_id, role=role, default_system_id=default_system_id, domain=domain)


def _prepared_work(tmp_path):
    db_path = tmp_path / "nexus.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TOKENS)
    fake = FakeGitHubClient()
    storage = Storage(db_path, github_client=fake)
    strategist = actor("trading-strategist-01", "trading-strategist", "trading-system", "Trading")
    architect = actor("sw-architect-01", "sw-architect")
    techlead = actor("sw-techlead-01", "sw-techlead")
    builder = actor("sw-builder-01", "sw-builder")

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
    storage.transition_request(actor=actor("nexus-01", "nexus", "nexus", "Nexus"), request_id=request_id, to_status="accepted", reason="Accepted for software planning.")
    storage.plan_work(actor=architect, request_id=request_id, repo_id="trading-engine", branch="feature/req-risk-checker", assigned_agent_id="sw-builder-01", sanitized_summary="Implement deterministic risk limit checker")
    storage.set_implementation_context(
        actor=architect,
        request_id=request_id,
        implementation_context={
            "component": "risk",
            "entrypoints": ["src/trading_engine/risk/check_order.py"],
            "likely_files": ["src/trading_engine/risk/check_order.py", "tests/risk/test_check_order.py"],
            "do_not_touch": ["src/trading_engine/execution/live_orders.py"],
            "acceptance_criteria": ["Risk breach blocks new orders."],
            "test_commands": ["pytest tests/risk/test_check_order.py"],
        },
    )
    storage.approve_work_plan(actor=techlead, request_id=request_id)
    return storage, fake, db_path, request_id, architect, techlead, builder


def test_github_issue_and_pr_sync_store_metadata_outside_requests(tmp_path):
    storage, fake, db_path, request_id, architect, techlead, _builder = _prepared_work(tmp_path)

    issue = storage.create_github_issue(actor=architect, request_id=request_id, labels=["nexus"], assignees=["octocat"])
    assert issue["issue"]["number"] == 1
    assert "Nexus Request" in issue["body"]
    assert fake.created_issues[0]["owner"] == "local"
    assert fake.created_issues[0]["repo"] == "trading-engine"

    conn = sqlite3.connect(db_path)
    try:
        request_columns = {row[1] for row in conn.execute("PRAGMA table_info(requests)")}
        assert ("github_" + "issue_url") not in request_columns
        assert ("github_" + "pr_url") not in request_columns
        assert conn.execute("SELECT COUNT(*) FROM github_issues WHERE request_id = ?", (request_id,)).fetchone()[0] == 1
    finally:
        conn.close()

    key = ("local", "trading-engine", 78)
    fake.pull_requests[key] = {
        "number": 78,
        "node_id": "PR_78",
        "title": "Implement deterministic risk limit checker",
        "state": "open",
        "draft": False,
        "merged": False,
        "merge_commit_sha": None,
        "head": {"ref": "feature/req-risk-checker", "sha": "abc123"},
        "base": {"ref": "main"},
        "html_url": "https://github.com/local/trading-engine/pull/78",
        "url": "https://api.github.com/repos/local/trading-engine/pulls/78",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "merged_at": None,
    }
    fake.files[key] = [{"filename": "src/trading_engine/risk/check_order.py"}]
    fake.reviews[key] = [{"user": {"login": "reviewer"}, "state": "APPROVED", "submitted_at": "2026-01-02T00:00:00Z"}]
    fake.commits[key] = [{"sha": "abc123", "html_url": "https://github.com/local/trading-engine/commit/abc123"}]
    fake.statuses[("local", "trading-engine", "abc123")] = {"state": "success"}
    fake.check_runs[("local", "trading-engine", "abc123")] = {"check_runs": [{"status": "completed", "conclusion": "success"}]}

    status = storage.link_github_pr(actor=techlead, request_id=request_id, url="https://github.com/local/trading-engine/pull/78")
    pr = status["github"]["pull_request"]
    assert pr["review_state"] == "approved"
    assert pr["checks_state"] == "passing"
    assert pr["policy_state"] == "ok"
    assert pr["changed_files"] == ["src/trading_engine/risk/check_order.py"]

    storage.transition_work(actor=architect, request_id=request_id, to_status="needs-planning", reason="Move into software planning.")
    storage.transition_work(actor=architect, request_id=request_id, to_status="ready-to-build", reason="Plan approved with GitHub issue and context.")
    storage.transition_work(actor=techlead, request_id=request_id, to_status="in-build", reason="Implementation can start.")
    storage.transition_work(actor=techlead, request_id=request_id, to_status="in-review", reason="Pull request is linked for review.")
    approved = storage.transition_work(actor=techlead, request_id=request_id, to_status="approved", reason="GitHub review and checks are passing.")
    assert approved["to_status"] == "approved"

    fake.pull_requests[key] = {**fake.pull_requests[key], "state": "closed", "merged": True, "merge_commit_sha": "merge123", "merged_at": "2026-01-03T00:00:00Z"}
    storage.sync_github_pr(actor=techlead, request_id=request_id)
    done = storage.transition_work(actor=techlead, request_id=request_id, to_status="done", reason="Merged PR has review and checks evidence.")
    assert done["to_status"] == "done"


def test_do_not_touch_violation_blocks_approved_transition(tmp_path):
    storage, fake, _db_path, request_id, architect, techlead, _builder = _prepared_work(tmp_path)
    key = ("local", "trading-engine", 79)
    fake.pull_requests[key] = {
        "number": 79,
        "node_id": "PR_79",
        "title": "Touch forbidden file",
        "state": "open",
        "draft": False,
        "merged": False,
        "head": {"ref": "feature/req-risk-checker", "sha": "def456"},
        "base": {"ref": "main"},
        "html_url": "https://github.com/local/trading-engine/pull/79",
        "url": "https://api.github.com/repos/local/trading-engine/pulls/79",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "merged_at": None,
    }
    fake.files[key] = [{"filename": "src/trading_engine/execution/live_orders.py"}]
    fake.reviews[key] = [{"user": {"login": "reviewer"}, "state": "APPROVED", "submitted_at": "2026-01-02T00:00:00Z"}]
    fake.check_runs[("local", "trading-engine", "def456")] = {"check_runs": [{"status": "completed", "conclusion": "success"}]}

    status = storage.link_github_pr(actor=techlead, request_id=request_id, url="https://github.com/local/trading-engine/pull/79")
    assert status["github"]["pull_request"]["policy_state"] == "violated"
    storage.transition_work(actor=architect, request_id=request_id, to_status="needs-planning", reason="Move into software planning.")
    storage.transition_work(actor=architect, request_id=request_id, to_status="ready-to-build", reason="Plan approved with context.")
    storage.transition_work(actor=techlead, request_id=request_id, to_status="in-build", reason="Implementation can start.")
    storage.transition_work(actor=techlead, request_id=request_id, to_status="in-review", reason="Pull request is linked.")
    try:
        storage.transition_work(actor=techlead, request_id=request_id, to_status="approved", reason="Attempt approval with violation.")
    except Exception as exc:
        assert getattr(exc, "code", None) == "NX-PRECONDITION-001"
    else:
        raise AssertionError("approved transition should be blocked by do-not-touch violation")
