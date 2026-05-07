"""Output helpers shared by Nexusctl CLI command handlers."""

from __future__ import annotations

import json
from typing import Any, TextIO
import sys


def print_json(payload: dict[str, Any], *, stream: TextIO | None = None) -> None:
    """Emit stable, machine-readable JSON for CLI callers and tests."""

    target = sys.stdout if stream is None else stream
    print(json.dumps(payload, sort_keys=True), file=target)


def error_payload(exc: Exception) -> dict[str, Any]:
    """Build the stable JSON error shape used by ``nexusctl``."""

    return {
        "ok": False,
        "error": exc.__class__.__name__,
        "message": str(exc),
        "rule_id": getattr(exc, "rule_id", None),
    }
