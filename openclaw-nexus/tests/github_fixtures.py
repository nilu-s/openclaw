from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexusctl.adapters.github.webhooks import compute_signature

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "github"
TEST_WEBHOOK_SECRET = "fixture-webhook-secret"


def load_github_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def fixture_body(name: str) -> bytes:
    # Use the exact checked-in bytes so HMAC tests exercise the same payload a
    # webhook endpoint receives, not a reserialized copy.
    return (FIXTURE_ROOT / name).read_bytes()


def signed_fixture_headers(event: str, delivery: str, body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> dict[str, str]:
    return {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": compute_signature(secret, body),
    }
