from __future__ import annotations

import pytest

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexusctl.cli import run



pytestmark = pytest.mark.unit
def _write_active_session(agent_dir: Path, *, role: str = "trading-strategist") -> None:
    session_dir = agent_dir / ".nexusctl" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": "S-2026-0001",
        "agent_id": "agent-01",
        "role": role,
        "default_system_id": "trading-system",
        "domain": "Trading",
        "issued_at": datetime.now(tz=timezone.utc).isoformat(),
        "expires_at": (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat(),
        "status": "active",
    }
    (session_dir / "current.json").write_text(json.dumps(payload), encoding="utf-8")


def test_validation_error_when_token_missing(agent_env):
    rc = run(["auth"], env=agent_env)
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




def test_validation_error_for_invalid_timeout_env(agent_env):
    env = dict(agent_env)
    env["NEXUSCTL_TIMEOUT_SECONDS"] = "0"
    rc = run(["auth", "--agent-token", "tok_techlead"], env=env)
    assert rc == 2

def test_validation_error_for_invalid_capability_id(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]))
    rc = run(["capabilities", "show", "invalid-id"], env=agent_env)
    assert rc == 2


def test_permission_denied_for_non_techlead_set_status(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]), role="sw-builder")
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
        env=agent_env,
    )
    assert rc == 4


def test_precondition_error_for_short_reason(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]), role="sw-techlead")
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
        env=agent_env,
    )
    assert rc == 2


def test_precondition_error_for_missing_session(agent_env):
    rc = run(["capabilities", "list"], env=agent_env)
    assert rc == 6


def test_validation_error_for_capabilities_domain_override(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]))
    rc = run(["capabilities", "list", "--domain", "Trading"], env=agent_env)
    assert rc == 2


def test_validation_error_for_request_create_missing_acceptance_criteria(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]), role="trading-strategist")
    rc = run(
        [
            "request",
            "create",
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
            "--goal-ref",
            "trading-goal://risk/limit-hard-stop",
        ],
        env=agent_env,
    )
    assert rc == 2


def test_permission_denied_for_non_trading_strategist_request_create(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]), role="sw-builder")
    rc = run(
        [
            "request",
            "create",
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
            "--goal-ref",
            "trading-goal://risk/limit-hard-stop",
            "--output",
            "json",
        ],
        env=agent_env,
    )
    assert rc == 4


def test_builder_cannot_run_global_github_repo_sync(agent_env):
    _write_active_session(Path(agent_env["NEXUSCTL_AGENT_DIR"]), role="sw-builder")
    rc = run(["github", "repos", "sync", "--output", "json"], env=agent_env)
    assert rc == 4


def test_removed_request_command_is_not_supported_after_v2_cutoff(agent_env):
    rc = run(["request", "submit"], env=agent_env)
    assert rc == 2
