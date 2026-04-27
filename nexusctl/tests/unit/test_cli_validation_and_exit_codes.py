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
