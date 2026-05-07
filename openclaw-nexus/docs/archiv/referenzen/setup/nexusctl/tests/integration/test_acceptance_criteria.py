from __future__ import annotations

import io
import json

import pytest

from nexusctl.cli import run

pytestmark = pytest.mark.integration


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


def test_ac_010_trading_strategist_can_create_request(cli_env, backend_server):
    assert run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env) == 0
    out = io.StringIO()
    err = io.StringIO()
    rc = run(
        [
            "request",
            "create",
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
            "--goal-ref",
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
        "SELECT request_id, status, submitted_by_agent_id, default_system_id FROM requests"
    )
    assert len(rows) == 1
    assert rows[0][0].startswith("REQ-2026-")
    assert rows[0][1] == "submitted"
    assert rows[0][2] == "trading-strategist-01"
    assert rows[0][3] == "trading-system"


def test_ac_011_request_create_rejects_non_trading_strategist(cli_env):
    assert run(["auth", "--agent-token", "tok_techlead", "--output", "json"], env=cli_env) == 0
    rc = run(
        [
            "request",
            "create",
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
            "--goal-ref",
            "trading-goal://risk/limit-hard-stop",
            "--output",
            "json",
        ],
        env=cli_env,
    )
    assert rc == 4


def test_ac_012_nexus_can_list_and_accept_requests(cli_env):
    assert run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env) == 0
    assert run(
        [
            "request",
            "create",
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
            "--goal-ref",
            "trading-goal://g-001/paper-baseline",
            "--output",
            "json",
        ],
        env=cli_env,
    ) == 0

    assert run(["auth", "--agent-token", "tok_nexus", "--output", "json"], env=cli_env) == 0
    out = io.StringIO()
    err = io.StringIO()
    rc = run(["request", "list", "--status", "submitted", "--limit", "10", "--output", "json"], env=cli_env, out=out, err=err)
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert payload["requests"]
    request_id = payload["requests"][0]["request_id"]
    assert "issue_ref" not in payload["requests"][0]
    assert (
        run(
            [
                "request",
                "transition",
                request_id,
                "--to",
                "accepted",
                "--reason",
                "Gate accepted for planning.",
                "--output",
                "json",
            ],
            env=cli_env,
        )
        == 0
    )


def test_ac_013_context_and_request_create_work_without_explicit_auth(cli_env):
    env = dict(cli_env)
    env["NEXUS_AGENT_TOKEN"] = "tok_trading"

    out = io.StringIO()
    err = io.StringIO()
    rc = run(["context", "--output", "json"], env=env, out=out, err=err)
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert payload["ok"] is True
    assert payload["agent"]["agent_id"] == "trading-strategist-01"
    assert "request.create" in payload["allowed_actions"]

    out2 = io.StringIO()
    err2 = io.StringIO()
    rc2 = run(
        [
            "request",
            "create",
            "--objective",
            "Need CAP-PT-002 for deterministic simulator replay.",
            "--missing-capability",
            "CAP-PT-002 deterministic replay engine.",
            "--business-impact",
            "Research replay quality is limited.",
            "--expected-behavior",
            "Replay reproduces the same sequence for equal input.",
            "--acceptance-criteria",
            "Given same input, replay output is deterministic.",
            "--risk-class",
            "medium",
            "--priority",
            "P2",
            "--goal-ref",
            "trading-goal://g-002/replay-determinism",
            "--output",
            "json",
        ],
        env=env,
        out=out2,
        err=err2,
    )
    assert rc2 == 0, err2.getvalue()
    created = json.loads(out2.getvalue())
    assert created["status"] == "submitted"
    assert "issue_ref" not in created


def test_context_advertises_capability_status_write_only_for_sw_techlead(cli_env):
    techlead_env = dict(cli_env)
    techlead_env["NEXUS_AGENT_TOKEN"] = "tok_techlead"

    out = io.StringIO()
    err = io.StringIO()
    rc = run(["context", "--output", "json"], env=techlead_env, out=out, err=err)
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert "capabilities.set-status" in payload["allowed_actions"]

    for token in ("tok_builder", "tok_reviewer"):
        env = dict(cli_env)
        env["NEXUS_AGENT_TOKEN"] = token
        out = io.StringIO()
        err = io.StringIO()
        rc = run(["context", "--output", "json"], env=env, out=out, err=err)
        assert rc == 0, err.getvalue()
        payload = json.loads(out.getvalue())
        assert "capabilities.set-status" not in payload["allowed_actions"]


def test_ac_014_github_issue_dry_run_uses_approved_work_context(cli_env):
    trading_env = dict(cli_env)
    trading_env["NEXUS_AGENT_TOKEN"] = "tok_trading"

    out = io.StringIO()
    err = io.StringIO()
    rc = run(
        [
            "request",
            "create",
            "--objective",
            "Need CAP-PT-003 for event-queue replay.",
            "--missing-capability",
            "CAP-PT-003 event-queue replay tool.",
            "--business-impact",
            "No reliable latency replay baseline.",
            "--expected-behavior",
            "Event queue replay can be reproduced and validated.",
            "--acceptance-criteria",
            "Given queue snapshot, replay output is stable.",
            "--risk-class",
            "high",
            "--priority",
            "P1",
            "--goal-ref",
            "trading-goal://g-003/queue-replay",
            "--output",
            "json",
        ],
        env=trading_env,
        out=out,
        err=err,
    )
    assert rc == 0, err.getvalue()
    request_id = json.loads(out.getvalue())["request_id"]

    nexus_env = dict(cli_env)
    nexus_env["NEXUS_AGENT_TOKEN"] = "tok_nexus"
    assert run(["request", "transition", request_id, "--to", "accepted", "--reason", "Gate accepted for planning.", "--output", "json"], env=nexus_env) == 0

    architect_env = dict(cli_env)
    architect_env["NEXUS_AGENT_TOKEN"] = "tok_architect"
    assert run(["work", "plan", request_id, "--repo", "trading-engine", "--branch", "feature/req-123", "--sanitized-summary", "Implement replay queue", "--output", "json"], env=architect_env) == 0
    assert run([
        "work", "set-implementation-context", request_id,
        "--component", "replay",
        "--entrypoint", "trading.replay",
        "--likely-file", "src/trading_engine/replay.py",
        "--do-not-touch", "secrets/*",
        "--acceptance-criteria", "Replay is deterministic",
        "--test-command", "pytest tests/replay",
        "--output", "json",
    ], env=architect_env) == 0

    techlead_env = dict(cli_env)
    techlead_env["NEXUS_AGENT_TOKEN"] = "tok_techlead"
    assert run(["work", "approve-plan", request_id, "--output", "json"], env=techlead_env) == 0

    out2 = io.StringIO()
    err2 = io.StringIO()
    rc2 = run(["github", "issue", "create", request_id, "--dry-run", "--output", "json"], env=architect_env, out=out2, err=err2)
    assert rc2 == 0, err2.getvalue()
    payload = json.loads(out2.getvalue())
    assert payload["dry_run"] is True
    assert "Nexus Request" in payload["body"]
    assert "src/trading_engine/replay.py" in payload["body"]
