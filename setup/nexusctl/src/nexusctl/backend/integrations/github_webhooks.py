from __future__ import annotations

import hashlib
import hmac

from nexusctl.errors import NexusError


def verify_webhook_signature(*, secret: str, body: bytes, signature_header: str | None) -> None:
    if not secret:
        raise NexusError("NX-GH-AUTH", "missing webhook secret")
    if not signature_header or not signature_header.startswith("sha256="):
        raise NexusError("NX-GH-AUTH", "missing webhook signature")
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise NexusError("NX-GH-AUTH", "invalid webhook signature")
