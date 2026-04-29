from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexusctl.session import SessionStore


def test_session_store_writes_restrictive_file_permissions(monkeypatch, tmp_path):
    calls: list[int] = []

    def _capture_chmod(self: Path, mode: int) -> None:
        calls.append(mode)

    monkeypatch.setattr(Path, "chmod", _capture_chmod, raising=True)
    path = tmp_path / "current.json"
    SessionStore._write_json(path, {"session_id": "S-1"})

    assert any(mode == 0o600 for mode in calls)


def test_session_store_writes_to_selected_agent_alias_dir(tmp_path):
    env = {
        "NEXUSCTL_SESSION_BASE": str(tmp_path / "agents"),
        "OPENCLAW_AGENT_ID": "nexus",
    }
    store = SessionStore(env)
    auth_response = {
        "session_id": "S-2026-abc",
        "agent_id": "nexus-01",
        "role": "nexus",
        "project_id": "trading-system",
        "domain": "Control",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "expires_at": (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat(),
        "status": "active",
    }

    store.save_auth_response(auth_response)

    expected = tmp_path / "agents" / "nexus" / "agent" / ".nexusctl" / "sessions" / "current.json"
    assert expected.is_file()


def test_session_store_loads_selected_agent_with_dash01_fallback(tmp_path):
    base = tmp_path / "agents"
    sessions_dir = base / "nexus-01" / "agent" / ".nexusctl" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": "S-2026-xyz",
        "agent_id": "nexus-01",
        "role": "nexus",
        "project_id": "trading-system",
        "domain": "Control",
        "issued_at": datetime.now(tz=timezone.utc).isoformat(),
        "expires_at": (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat(),
        "status": "active",
    }
    (sessions_dir / "current.json").write_text(json.dumps(payload), encoding="utf-8")
    store = SessionStore({"NEXUSCTL_SESSION_BASE": str(base), "OPENCLAW_AGENT_ID": "nexus"})

    session = store.load_active()
    assert session.agent_id == "nexus-01"


def test_session_store_prefers_selected_agent_dir_when_both_aliases_exist(tmp_path):
    base = tmp_path / "agents"
    now = datetime.now(tz=timezone.utc)
    payload_main = {
        "session_id": "S-2026-main",
        "agent_id": "main-01",
        "role": "main",
        "project_id": "trading-system",
        "domain": "Control",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "status": "active",
    }
    payload_alias = dict(payload_main)
    payload_alias["session_id"] = "S-2026-alias"

    d1 = base / "main" / "agent" / ".nexusctl" / "sessions"
    d2 = base / "main-01" / "agent" / ".nexusctl" / "sessions"
    d1.mkdir(parents=True, exist_ok=True)
    d2.mkdir(parents=True, exist_ok=True)
    (d1 / "current.json").write_text(json.dumps(payload_main), encoding="utf-8")
    (d2 / "current.json").write_text(json.dumps(payload_alias), encoding="utf-8")

    store = SessionStore({"NEXUSCTL_SESSION_BASE": str(base), "OPENCLAW_AGENT_ID": "main"})
    session = store.load_active()
    assert session.session_id == "S-2026-main"
