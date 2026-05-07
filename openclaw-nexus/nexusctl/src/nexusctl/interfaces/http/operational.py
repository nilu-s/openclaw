"""Operational hardening primitives for the stdlib HTTP boundary.

The module keeps deployment defaults explicit and testable without adding a web
framework: loopback-safe binding, opt-in insecure remote binding, bounded
request bodies, central client timeout/retry settings, and a lightweight
session-store abstraction for per-request transport metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from nexusctl.domain.errors import ValidationError

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_CLIENT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_RETRIES = 1
DEFAULT_MAX_BODY_BYTES = 1_048_576


def env_bool(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, *, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValidationError(f"{name} must be greater than zero")
    return value


def env_int(name: str, *, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValidationError(f"{name} must be at least {minimum}")
    return value


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in LOOPBACK_HOSTS


def validate_server_binding(
    host: str,
    *,
    tls_enabled: bool = False,
    allow_insecure_remote: bool = False,
) -> None:
    """Reject remote plain-HTTP bindings unless the operator opts in explicitly."""

    if is_loopback_host(host):
        return
    if tls_enabled:
        return
    if allow_insecure_remote:
        return
    raise ValidationError(
        "remote API bindings require TLS; bind to 127.0.0.1 or set "
        "NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND=1 for a trusted internal network"
    )


def validate_client_url(base_url: str, *, allow_insecure_remote: bool = False) -> None:
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    scheme = parsed.scheme.lower()
    if scheme == "https":
        return
    if scheme == "http" and (is_loopback_host(host) or allow_insecure_remote):
        return
    raise ValidationError(
        "remote API URLs must use HTTPS unless they target loopback; set "
        "NEXUSCTL_API_ALLOW_INSECURE_REMOTE=1 only for a trusted internal network"
    )


@dataclass(frozen=True, slots=True)
class HTTPClientSettings:
    timeout_seconds: float = DEFAULT_CLIENT_TIMEOUT_SECONDS
    read_retries: int = DEFAULT_READ_RETRIES
    allow_insecure_remote: bool = False

    @classmethod
    def from_environment(cls) -> "HTTPClientSettings":
        return cls(
            timeout_seconds=env_float("NEXUSCTL_API_TIMEOUT_SECONDS", default=DEFAULT_CLIENT_TIMEOUT_SECONDS),
            read_retries=env_int("NEXUSCTL_API_READ_RETRIES", default=DEFAULT_READ_RETRIES, minimum=0),
            allow_insecure_remote=env_bool("NEXUSCTL_API_ALLOW_INSECURE_REMOTE", default=False),
        )


@dataclass(frozen=True, slots=True)
class HTTPServerSettings:
    host: str = "127.0.0.1"
    port: int = 8080
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    tls_enabled: bool = False
    allow_insecure_remote_bind: bool = False

    @classmethod
    def from_environment(cls) -> "HTTPServerSettings":
        return cls(
            host=os.environ.get("NEXUSCTL_API_HOST", "127.0.0.1"),
            port=env_int("NEXUSCTL_API_PORT", default=8080, minimum=1),
            max_body_bytes=env_int("NEXUSCTL_API_MAX_BODY_BYTES", default=DEFAULT_MAX_BODY_BYTES, minimum=1),
            tls_enabled=env_bool("NEXUSCTL_API_TLS_ENABLED", default=False),
            allow_insecure_remote_bind=env_bool("NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND", default=False),
        )


@dataclass(slots=True)
class SessionStore:
    """Small in-memory session metadata store for stdlib server deployments."""

    ttl_seconds: float = 3600.0
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def issue(self, *, agent_id: str | None = None, transport: str = "http") -> str:
        self.prune()
        session_id = secrets.token_urlsafe(24)
        self._sessions[session_id] = {
            "agent_id": agent_id,
            "transport": transport,
            "created_at": time.time(),
            "last_seen_at": time.time(),
        }
        return session_id

    def touch(self, session_id: str) -> dict[str, Any] | None:
        self.prune()
        session = self._sessions.get(session_id)
        if session is None:
            return None
        session["last_seen_at"] = time.time()
        return dict(session)

    def prune(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for session_id, session in list(self._sessions.items()):
            if float(session.get("last_seen_at", session.get("created_at", 0.0))) < cutoff:
                self._sessions.pop(session_id, None)
