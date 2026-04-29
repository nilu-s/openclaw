from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexusctl.cli import run


def _write_active_session(agent_dir: Path, *, role: str = "trading-strategist") -> None:
    session_dir = agent_dir / ".nexusctl" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": "S-2026-0001",
        "agent_id": "agent-01",
        "role": role,
        "project_id": "trading-system",
        "domain": "Trading",
        "issued_at": datetime.now(tz=timezone.utc).isoformat(),
        "expires_at": (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat(),
        "status": "active",
    }
    (session_dir / "current.json").write_text(json.dumps(payload), encoding="utf-8")


def test_validation_error_when_token_missing(cli_env):
    rc = run(["auth"], env=cli_env)
    assert rc == 2


def test_auth_uses_seed_token_for_openclaw_agent_id(cli_env, tmp_path):
    seed_file = tmp_path / "seed_tokens.env"
    seed_file.write_text("sw-techlead-01=tok_techlead\n", encoding="utf-8")
    env = {
        **cli_env,
        "OPENCLAW_AGENT_ID": "sw-techlead",
        "NEXUSCTL_SEED_TOKENS_FILE": str(seed_file),
    }

    rc = run(["auth", "--output", "json"], env=env)
    assert rc == 0


def test_validation_error_for_invalid_capability_id(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]))
    rc = run(["capabilities", "show", "invalid-id"], env=cli_env)
    assert rc == 2


def test_permission_denied_for_non_techlead_set_status(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]), role="sw-builder")
    rc = run(
        [
            "capabilities",
            "set-status",
            "F-002",
            "--to",
            "available",
            "--reason",
            "All requirements verified and evidence linked.",
        ],
        env=cli_env,
    )
    assert rc == 4


def test_precondition_error_for_short_reason(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]), role="sw-techlead")
    rc = run(
        [
            "capabilities",
            "set-status",
            "F-002",
            "--to",
            "available",
            "--reason",
            "too short",
        ],
        env=cli_env,
    )
    assert rc == 2


def test_precondition_error_for_missing_session(cli_env):
    rc = run(["capabilities", "list"], env=cli_env)
    assert rc == 6


def test_validation_error_for_capabilities_domain_override(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]))
    rc = run(["capabilities", "list", "--domain", "Trading"], env=cli_env)
    assert rc == 2


def test_validation_error_for_handoff_submit_missing_acceptance_criteria(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]), role="trading-strategist")
    rc = run(
        [
            "handoff",
            "submit",
            "--objective",
            "Reduce reaction latency for risk-limit breaches.",
            "--missing-capability",
            "Automatic hard-stop trigger for threshold breaches.",
            "--business-impact",
            "Reduces prolonged exposure during volatility spikes.",
            "--expected-behavior",
            "System blocks new entries immediately after breach detection.",
            "--risk-class",
            "high",
            "--priority",
            "P1",
            "--trading-goals-ref",
            "trading-goal://risk/limit-hard-stop",
        ],
        env=cli_env,
    )
    assert rc == 2


def test_permission_denied_for_non_trading_strategist_handoff_submit(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]), role="sw-builder")
    rc = run(
        [
            "handoff",
            "submit",
            "--objective",
            "Reduce reaction latency for risk-limit breaches.",
            "--missing-capability",
            "Automatic hard-stop trigger for threshold breaches.",
            "--business-impact",
            "Reduces prolonged exposure during volatility spikes.",
            "--expected-behavior",
            "System blocks new entries immediately after breach detection.",
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


def test_permission_denied_for_non_nexus_handoff_set_issue(cli_env):
    _write_active_session(Path(cli_env["NEXUSCTL_AGENT_DIR"]), role="sw-builder")
    rc = run(
        [
            "handoff",
            "set-issue",
            "HC-2026-0001",
            "--issue-ref",
            "issue://github/example/repo#1",
            "--output",
            "json",
        ],
        env=cli_env,
    )
    assert rc == 4
