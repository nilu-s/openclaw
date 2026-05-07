"""Agent token registry and session handling for Nexusctl auth/identity workflow.

Tokens authenticate agents.  The agent's domain, role, and capabilities are
then derived from the registry/blueprint seed, never from a user supplied
``--domain`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets
import sqlite3
from typing import Any
from uuid import uuid4

from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import PolicyDeniedError, UnknownAgentError, ValidationError
from nexusctl.storage.event_store import EventStore

_HASH_ALGORITHM = "pbkdf2_sha256"
_HASH_ITERATIONS = 48_000
_SESSION_TTL_SECONDS = 3600
_TOKEN_PREFIX = "nxs1"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hash_token_secret(secret: str, *, salt: bytes | None = None, iterations: int = _HASH_ITERATIONS) -> str:
    """Return a salted PBKDF2 hash string for a token secret."""

    if not secret:
        raise ValidationError("token secret must not be empty")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt_bytes, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt_bytes).decode("ascii").rstrip("=")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{_HASH_ALGORITHM}${iterations}${salt_b64}${digest_b64}"


def verify_token_secret(secret: str, encoded_hash: str) -> bool:
    """Verify a token secret against an encoded hash in constant time."""

    try:
        algorithm, iterations_raw, salt_b64, expected_b64 = encoded_hash.split("$", 3)
        if algorithm != _HASH_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _b64decode(salt_b64)
        expected = _b64decode(expected_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(frozen=True, slots=True)
class TokenCredential:
    token_id: str
    agent_id: str
    token: str
    token_prefix: str
    created_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "agent_id": self.agent_id,
            "token": self.token,
            "token_prefix": self.token_prefix,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    session_id: str
    token_id: str
    subject: Subject
    issued_at: str
    expires_at: str

    @property
    def agent_id(self) -> str:
        return self.subject.agent_id

    @property
    def domain(self) -> str:
        return self.subject.domain

    def to_json(self, *, include_capabilities: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "session_id": self.session_id,
            "token_id": self.token_id,
            "agent_id": self.subject.agent_id,
            "domain": self.subject.domain,
            "role": self.subject.role,
            "normal_agent": self.subject.normal_agent,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "ttl_seconds": max(0, int((parse_iso_z(self.expires_at) - utcnow()).total_seconds())),
            "domain_source": "auth_token",
        }
        if include_capabilities:
            body["capabilities"] = sorted(self.subject.capabilities)
        return body


class AgentTokenRegistry:
    """SQLite-backed registry for agent tokens and short-lived sessions."""

    def __init__(self, connection: sqlite3.Connection, *, session_ttl_seconds: int = _SESSION_TTL_SECONDS) -> None:
        self.connection = connection
        self.session_ttl_seconds = session_ttl_seconds
        self.events = EventStore(connection)

    def issue_local_login(self, agent_id: str) -> tuple[TokenCredential, AuthenticatedSession]:
        """Create a local-test token for an agent and return a fresh session."""

        credential = self.create_token(agent_id, actor_id=None, deactivate_existing=False)
        session = self.authenticate(credential.token)
        self.events.append(
            aggregate_type="agent",
            aggregate_id=agent_id,
            event_type="auth.local_login_token_issued",
            actor_id="local-login",
            payload={"agent_id": agent_id, "token_id": credential.token_id},
            metadata={"milestone": 4},
        )
        return credential, session

    def rotate_token(self, target_agent_id: str, *, actor: Subject) -> TokenCredential:
        """Rotate an agent token; only control/platform actors may do this."""

        if actor.domain not in {"control", "platform"}:
            raise PolicyDeniedError(
                "only control or platform agents may rotate agent tokens",
                rule_id="rotate_token_control_or_platform_only",
            )
        credential = self.create_token(target_agent_id, actor_id=actor.agent_id, deactivate_existing=True)
        self.events.append(
            aggregate_type="agent",
            aggregate_id=target_agent_id,
            event_type="auth.agent_token_rotated",
            actor_id=actor.agent_id,
            payload={"agent_id": target_agent_id, "token_id": credential.token_id},
            metadata={"milestone": 4},
        )
        return credential

    def create_token(
        self,
        agent_id: str,
        *,
        actor_id: str | None,
        deactivate_existing: bool,
    ) -> TokenCredential:
        self.subject_for_agent(agent_id)  # validates the seeded agent exists
        if deactivate_existing:
            self.connection.execute(
                """
                UPDATE agent_tokens
                   SET active = 0, rotated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
                 WHERE agent_id = ? AND active = 1
                """,
                (agent_id,),
            )
        token_id = f"tok-{uuid4().hex}"
        secret = secrets.token_urlsafe(32)
        token = f"{_TOKEN_PREFIX}_{token_id}_{secret}"
        created_at = isoformat_z(utcnow())
        self.connection.execute(
            """
            INSERT INTO agent_tokens(token_id, agent_id, token_hash, token_prefix, active, created_by, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                token_id,
                agent_id,
                hash_token_secret(secret),
                token[:18],
                actor_id,
                created_at,
            ),
        )
        return TokenCredential(
            token_id=token_id,
            agent_id=agent_id,
            token=token,
            token_prefix=token[:18],
            created_at=created_at,
        )

    def authenticate(self, token: str | None) -> AuthenticatedSession:
        """Verify a token and return a short-lived authenticated session."""

        if not token:
            raise ValidationError("missing Nexusctl token; set NEXUSCTL_TOKEN or pass --token")
        token_id, secret = self._parse_token(token)
        row = self.connection.execute(
            """
            SELECT token_id, agent_id, token_hash, active, expires_at
              FROM agent_tokens
             WHERE token_id = ?
            """,
            (token_id,),
        ).fetchone()
        if row is None or int(row["active"]) != 1:
            raise ValidationError("invalid or inactive Nexusctl token")
        if row["expires_at"] and parse_iso_z(row["expires_at"]) <= utcnow():
            raise ValidationError("Nexusctl token has expired")
        if not verify_token_secret(secret, row["token_hash"]):
            raise ValidationError("invalid Nexusctl token")

        self.connection.execute(
            "UPDATE agent_tokens SET last_used_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE token_id = ?",
            (token_id,),
        )
        subject = self.subject_for_agent(row["agent_id"])
        return self._issue_session(token_id=token_id, subject=subject)

    def subject_for_agent(self, agent_id: str) -> Subject:
        row = self.connection.execute(
            """
            SELECT id, domain_id, role, normal_agent
              FROM agents
             WHERE id = ?
            """,
            (agent_id,),
        ).fetchone()
        if row is None:
            raise UnknownAgentError(f"unknown agent {agent_id}")
        capabilities = tuple(
            capability_row["capability_id"]
            for capability_row in self.connection.execute(
                """
                SELECT capability_id
                  FROM agent_capabilities
                 WHERE agent_id = ?
                 ORDER BY capability_id
                """,
                (agent_id,),
            ).fetchall()
        )
        return Subject.create(
            agent_id=row["id"],
            domain=row["domain_id"],
            role=row["role"],
            capabilities=capabilities,
            normal_agent=bool(row["normal_agent"]),
        )

    def _issue_session(self, *, token_id: str, subject: Subject) -> AuthenticatedSession:
        issued_at = utcnow()
        expires_at = issued_at + timedelta(seconds=self.session_ttl_seconds)
        session_id = f"ses-{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO agent_sessions(session_id, token_id, agent_id, issued_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, token_id, subject.agent_id, isoformat_z(issued_at), isoformat_z(expires_at)),
        )
        return AuthenticatedSession(
            session_id=session_id,
            token_id=token_id,
            subject=subject,
            issued_at=isoformat_z(issued_at),
            expires_at=isoformat_z(expires_at),
        )

    @staticmethod
    def _parse_token(token: str) -> tuple[str, str]:
        parts = token.split("_", 2)
        if len(parts) != 3 or parts[0] != _TOKEN_PREFIX or not parts[1].startswith("tok-"):
            raise ValidationError("invalid Nexusctl token format")
        return parts[1], parts[2]
