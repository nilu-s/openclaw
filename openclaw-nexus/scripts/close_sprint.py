#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASES = ROOT / ".chatgpt" / "state" / "phases.md"
ARCHIVE_DIR = ROOT / "docs" / ("arch" + "iv") / "sprints"

REQUIRED_CLOSE_MARKERS = [
    "Current-State-Delta",
    "LLM-Doublecheck",
    "Prüfumfang",
    "Ergebnis",
    "CURRENT_STATE.md",
]


def missing_close_markers(content: str) -> list[str]:
    return [marker for marker in REQUIRED_CLOSE_MARKERS if marker not in content]


def main() -> int:
    if not PHASES.exists():
        print(".chatgpt/state/phases.md does not exist")
        return 1

    content = PHASES.read_text(encoding="utf-8")
    if not content.strip():
        print("No active sprint log to archive; .chatgpt/state/phases.md is already empty.")
        return 0

    missing = missing_close_markers(content)
    if missing:
        print("Refusing to close sprint before the LLM doublecheck is documented.")
        print("Missing required close markers:")
        for marker in missing:
            print(f"- {marker}")
        return 1

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = ARCHIVE_DIR / f"{stamp}-phases.md"
    archive_path.write_text(content, encoding="utf-8")
    PHASES.write_text("", encoding="utf-8")
    print(f"Archived sprint log to {archive_path.relative_to(ROOT)}")
    print("Reset .chatgpt/state/phases.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
