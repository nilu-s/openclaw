"""GitHub webhook parsing and signature verification for webhook reconciliation.

The adapter is intentionally framework-free and network-free.  It verifies the
GitHub ``X-Hub-Signature-256`` header, normalizes delivery metadata, and leaves
all Nexusctl state decisions to the application service.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import hashlib
import json
from typing import Any, Mapping

from nexusctl.domain.errors import ValidationError

SUPPORTED_WEBHOOK_EVENTS: tuple[str, ...] = (
    "issues",
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "check_run",
    "workflow_run",
    "push",
)


@dataclass(frozen=True, slots=True)
class GitHubWebhookEnvelope:
    """Normalized GitHub webhook request metadata."""

    delivery_id: str
    event_name: str
    payload: dict[str, Any]
    signature: str | None = None
    action: str | None = None
    repository_full_name: str | None = None

    @classmethod
    def from_headers_and_body(cls, headers: Mapping[str, str], body: bytes) -> "GitHubWebhookEnvelope":
        normalized = {str(key).lower(): value for key, value in headers.items()}
        delivery_id = normalized.get("x-github-delivery") or normalized.get("github-delivery")
        event_name = normalized.get("x-github-event") or normalized.get("github-event")
        if not delivery_id:
            raise ValidationError("missing X-GitHub-Delivery header")
        if not event_name:
            raise ValidationError("missing X-GitHub-Event header")
        payload = parse_payload(body)
        repository = payload.get("repository") if isinstance(payload, dict) else None
        full_name = repository.get("full_name") if isinstance(repository, dict) else None
        return cls(
            delivery_id=str(delivery_id),
            event_name=str(event_name),
            payload=payload,
            signature=normalized.get("x-hub-signature-256"),
            action=str(payload.get("action")) if payload.get("action") is not None else None,
            repository_full_name=str(full_name) if full_name else None,
        )

    def validate_supported_event(self) -> None:
        if self.event_name not in SUPPORTED_WEBHOOK_EVENTS:
            raise ValidationError(f"unsupported GitHub webhook event {self.event_name}")


def parse_payload(body: bytes | str) -> dict[str, Any]:
    raw = body.encode("utf-8") if isinstance(body, str) else body
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid GitHub webhook JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("GitHub webhook payload must be a JSON object")
    return data


def compute_signature(secret: str, body: bytes | str) -> str:
    if not secret:
        raise ValidationError("webhook secret is required for signature verification")
    raw = body.encode("utf-8") if isinstance(body, str) else body
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes | str, signature: str | None) -> bool:
    if not signature:
        return False
    expected = compute_signature(secret, body)
    return hmac.compare_digest(expected, signature)


def require_valid_signature(secret: str, body: bytes | str, signature: str | None) -> None:
    if not verify_signature(secret, body, signature):
        raise ValidationError("invalid GitHub webhook signature")


def canonical_payload(payload: Mapping[str, Any]) -> str:
    """Return the stable JSON representation stored in Nexusctl."""

    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
