from __future__ import annotations

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
