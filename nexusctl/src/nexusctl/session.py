from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from nexusctl.errors import NexusError
from nexusctl.models import Session


class SessionStore:
    def __init__(self, env: Mapping[str, str]):
        self._env = env

    def save_auth_response(self, auth_response: dict) -> Session:
        session = Session.from_auth_response(auth_response)
        sessions_dir = self._sessions_dir_for_write(session.agent_id)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(sessions_dir / f"{session.project_id}.json", session.to_dict())
        self._write_json(sessions_dir / "current.json", session.to_dict())
        return session

    def load_active(self) -> Session:
        candidates = self._candidate_session_dirs()
        matches = [p for p in candidates if (p / "current.json").is_file()]
        if not matches:
            raise NexusError("NX-PRECONDITION-001", "no active session found, run `nexusctl auth` first")
        if len(matches) > 1:
            raise NexusError(
                "NX-PRECONDITION-001",
                "multiple agent sessions found; set NEXUSCTL_AGENT_ID or NEXUSCTL_AGENT_DIR",
            )
        payload = self._read_json(matches[0] / "current.json")
        session = Session.from_dict(payload)
        if session.status != "active":
            raise NexusError("NX-PRECONDITION-001", "session is not active")
        now = datetime.now(tz=timezone.utc)
        if session.expires_at <= now:
            raise NexusError("NX-PRECONDITION-002", "session expired, run `nexusctl auth` again")
        return session

    def _sessions_dir_for_write(self, agent_id: str) -> Path:
        explicit_agent_dir = self._env.get("NEXUSCTL_AGENT_DIR")
        if explicit_agent_dir:
            return Path(explicit_agent_dir).expanduser() / ".nexusctl" / "sessions"
        base = Path(self._env.get("NEXUSCTL_SESSION_BASE", str(Path.home() / ".openclaw" / "agents"))).expanduser()
        return base / agent_id / "agent" / ".nexusctl" / "sessions"

    def _candidate_session_dirs(self) -> list[Path]:
        explicit_agent_dir = self._env.get("NEXUSCTL_AGENT_DIR")
        if explicit_agent_dir:
            return [Path(explicit_agent_dir).expanduser() / ".nexusctl" / "sessions"]

        base = Path(self._env.get("NEXUSCTL_SESSION_BASE", str(Path.home() / ".openclaw" / "agents"))).expanduser()
        selected_agent_id = self._env.get("NEXUSCTL_AGENT_ID") or self._env.get("OPENCLAW_AGENT_ID")
        if selected_agent_id:
            return [base / selected_agent_id / "agent" / ".nexusctl" / "sessions"]

        if not base.exists():
            return []
        return [path / "agent" / ".nexusctl" / "sessions" for path in base.iterdir() if path.is_dir()]

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))
