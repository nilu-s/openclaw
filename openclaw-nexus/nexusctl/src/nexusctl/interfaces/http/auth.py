"""HTTP authentication helpers for Nexusctl API.

The HTTP layer derives agent identity from the same local token registry as the
CLI. It deliberately returns a Subject only; authorization remains inside the
shared app services and PolicyEngine.
"""

from __future__ import annotations

import sqlite3
from typing import Mapping

from nexusctl.authz.subject import Subject
from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.domain.errors import AuthenticationError, ValidationError


def bearer_token(headers: Mapping[str, str]) -> str:
    """Extract a Bearer token from case-insensitive HTTP headers."""

    authorization = ""
    for key, value in headers.items():
        if key.lower() == "authorization":
            authorization = value.strip()
            break
    if not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing Authorization: Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("empty bearer token")
    return token


def authenticate_subject(connection: sqlite3.Connection, headers: Mapping[str, str]) -> Subject:
    """Authenticate the request and return the registry-derived subject."""

    return AgentTokenRegistry(connection).authenticate(bearer_token(headers)).subject


def optional_json_bool(value: object, *, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValidationError(f"{field} must be boolean")
