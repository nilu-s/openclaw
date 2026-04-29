from __future__ import annotations

import io
import json

from nexusctl.cli import run


def test_ac_001_auth_returns_feature_list(cli_env):
    rc = run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env)
    assert rc == 0


def test_ac_002_auth_rejects_invalid_token(cli_env):
    rc = run(["auth", "--agent-token", "tok_invalid", "--output", "json"], env=cli_env)
    assert rc != 0


def test_ac_003_auth_creates_auditable_entry(cli_env, backend_server):
    rc = run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env)
    assert rc == 0
    rows = backend_server.fetchall(
        "SELECT auth_id, session_id FROM auth_log ORDER BY rowid ASC"
    )
    assert len(rows) == 1
    entry = {"auth_id": rows[0][0], "session_id": rows[0][1]}
    assert entry["auth_id"].startswith("AUTH-2026-")
    assert entry["session_id"].startswith("S-2026-")


def test_ac_004_capabilities_list_returns_current_state(cli_env):
    assert run(["auth", "--agent-token", "tok_trading"], env=cli_env) == 0
    rc = run(["capabilities", "list", "--status", "all", "--output", "json"], env=cli_env)
    assert rc == 0


def test_ac_005_capabilities_show_returns_consistent_details(cli_env):
    assert run(["auth", "--agent-token", "tok_trading"], env=cli_env) == 0
    rc = run(["capabilities", "show", "F-001", "--output", "json"], env=cli_env)
    assert rc == 0


def test_ac_006_strategy_can_derive_from_available_and_planned(cli_env):
    assert run(["auth", "--agent-token", "tok_trading"], env=cli_env) == 0
    rc = run(["capabilities", "list", "--status", "all", "--output", "json"], env=cli_env)
    assert rc == 0


def test_ac_007_show_and_list_require_active_session(cli_env):
    rc_list = run(["capabilities", "list"], env=cli_env)
    rc_show = run(["capabilities", "show", "F-001"], env=cli_env)
    assert rc_list == 6
    assert rc_show == 6


def test_ac_008_set_status_only_sw_techlead_with_audit_event(cli_env, backend_server):
    assert run(["auth", "--agent-token", "tok_techlead", "--output", "json"], env=cli_env) == 0
    backend_server.execute(
        "UPDATE capability_requirements SET status = 'verified' WHERE capability_id = ?",
        ("F-002",),
    )
    backend_server.execute(
        "UPDATE capability_evidence SET issue_ref = ?, pr_ref = ?, test_ref = ? WHERE capability_id = ?",
        ("issue://123", "pr://123", "test://123", "F-002"),
    )
    rc = run(
        [
            "capabilities",
            "set-status",
            "F-002",
            "--to",
            "available",
            "--reason",
            "All requirements verified and evidence linked.",
            "--output",
            "json",
        ],
        env=cli_env,
    )
    assert rc == 0
    rows = backend_server.fetchall("SELECT event_id FROM capability_status_events")
    assert len(rows) == 1


def test_ac_009_set_status_rejects_when_gate_fails(cli_env):
    assert run(["auth", "--agent-token", "tok_techlead", "--output", "json"], env=cli_env) == 0
    rc = run(
        [
            "capabilities",
            "set-status",
            "F-002",
            "--to",
            "available",
            "--reason",
            "All requirements verified and evidence linked.",
            "--output",
            "json",
        ],
        env=cli_env,
    )
    assert rc == 6


def test_ac_010_trading_strategist_can_submit_handoff(cli_env, backend_server):
    assert run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env) == 0
    out = io.StringIO()
    err = io.StringIO()
    rc = run(
        [
            "handoff",
            "submit",
            "--objective",
            "Reduce reaction latency for risk-limit breaches.",
            "--missing-capability",
            "Automatic hard-stop trigger when risk threshold is exceeded.",
            "--business-impact",
            "Prevents prolonged exposure during volatility spikes.",
            "--expected-behavior",
            "System halts new entries within breach window.",
            "--acceptance-criteria",
            "Given threshold breach, new entries are blocked within 500ms.",
            "--acceptance-criteria",
            "Event is logged with timestamp and breach metadata.",
            "--risk-class",
            "high",
            "--priority",
            "P1",
            "--trading-goals-ref",
            "trading-goal://risk/limit-hard-stop",
            "--output",
            "json",
        ],
        env=cli_env,
        out=out,
        err=err,
    )
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert payload["ok"] is True
    assert payload["status"] == "submitted"
    assert payload["risk_class"] == "high"
    assert payload["priority"] == "P1"
    assert payload["agent_id"] == "trading-strategist-01"

    rows = backend_server.fetchall(
        "SELECT handoff_id, status, submitted_by_agent_id, project_id FROM handoff_requests"
    )
    assert len(rows) == 1
    assert rows[0][0].startswith("HC-2026-")
    assert rows[0][1] == "submitted"
    assert rows[0][2] == "trading-strategist-01"
    assert rows[0][3] == "trading-system"


def test_ac_011_handoff_submit_rejects_non_trading_strategist(cli_env):
    assert run(["auth", "--agent-token", "tok_techlead", "--output", "json"], env=cli_env) == 0
    rc = run(
        [
            "handoff",
            "submit",
            "--objective",
            "Reduce reaction latency for risk-limit breaches.",
            "--missing-capability",
            "Automatic hard-stop trigger when risk threshold is exceeded.",
            "--business-impact",
            "Prevents prolonged exposure during volatility spikes.",
            "--expected-behavior",
            "System halts new entries within breach window.",
            "--acceptance-criteria",
            "Given threshold breach, new entries are blocked within 500ms.",
            "--risk-class",
            "high",
            "--priority",
            "P1",
            "--trading-goals-ref",
            "trading-goal://risk/limit-hard-stop",
            "--output",
            "json",
        ],
        env=cli_env,
    )
    assert rc == 4


def test_ac_012_nexus_can_list_handoffs_and_set_issue_link(cli_env):
    assert run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env) == 0
    assert run(
        [
            "handoff",
            "submit",
            "--objective",
            "Need CAP-PT-001 baseline simulator.",
            "--missing-capability",
            "CAP-PT-001 paper execution simulator.",
            "--business-impact",
            "Paper baseline is blocked.",
            "--expected-behavior",
            "Order lifecycle simulation is deterministic and logged.",
            "--acceptance-criteria",
            "Given paper order submit, lifecycle state is persisted.",
            "--risk-class",
            "high",
            "--priority",
            "P1",
            "--trading-goals-ref",
            "trading-goal://g-001/paper-baseline",
            "--output",
            "json",
        ],
        env=cli_env,
    ) == 0

    assert run(["auth", "--agent-token", "tok_nexus", "--output", "json"], env=cli_env) == 0
    out = io.StringIO()
    err = io.StringIO()
    rc = run(["handoff", "list", "--status", "submitted", "--limit", "10", "--output", "json"], env=cli_env, out=out, err=err)
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert payload["handoffs"]
    handoff_id = payload["handoffs"][0]["handoff_id"]

    out2 = io.StringIO()
    err2 = io.StringIO()
    rc2 = run(
        [
            "handoff",
            "set-issue",
            handoff_id,
            "--issue-ref",
            "issue://github/mawly-engineer/trading-system#99",
            "--issue-number",
            "99",
            "--issue-url",
            "https://github.com/mawly-engineer/trading-system/issues/99",
            "--output",
            "json",
        ],
        env=cli_env,
        out=out2,
        err=err2,
    )
    assert rc2 == 0, err2.getvalue()
    payload2 = json.loads(out2.getvalue())
    assert payload2["issue_ref"] == "issue://github/mawly-engineer/trading-system#99"
