from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Session:
    session_id: str
    agent_id: str
    role: str
    project_id: str
    domain: str
    issued_at: datetime
    expires_at: datetime
    status: str = "active"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            role=data["role"],
            project_id=data["project_id"],
            domain=data.get("domain", "unknown"),
            issued_at=parse_ts(data["issued_at"]),
            expires_at=parse_ts(data["expires_at"]),
            status=data.get("status", "active"),
        )

    @classmethod
    def from_auth_response(cls, data: dict[str, Any]) -> "Session":
        now = datetime.now(tz=timezone.utc)
        issued_at = parse_ts(data["timestamp"]) if data.get("timestamp") else now
        expires_at = parse_ts(data["expires_at"]) if data.get("expires_at") else (issued_at + timedelta(minutes=60))
        return cls(
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            role=data["role"],
            project_id=data["project_id"],
            domain=data.get("domain", "unknown"),
            issued_at=issued_at,
            expires_at=expires_at,
            status="active",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "role": self.role,
            "project_id": self.project_id,
            "domain": self.domain,
            "issued_at": format_ts(self.issued_at),
            "expires_at": format_ts(self.expires_at),
            "status": self.status,
        }

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(tz=timezone.utc)
        return self.status == "active" and self.expires_at > now
