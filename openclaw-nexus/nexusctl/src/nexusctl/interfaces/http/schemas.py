"""Tiny HTTP schema helpers for Nexusctl routes."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from nexusctl.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class JsonResponse:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        return {"status": self.status, "body": self.body, "headers": dict(self.headers or {})}


def parse_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("JSON body must be an object")
    return payload


def require_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"missing required string field: {field}")
    return value.strip()


def optional_string(payload: Mapping[str, Any], field: str, default: str = "") -> str:
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    return value
