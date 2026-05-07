from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = [
    ROOT / "nexusctl" / "src",
    ROOT / "scripts",
    ROOT / "tests",
]
ENFORCEMENT_FILE = Path(__file__).resolve()


def _active_python_files() -> list[Path]:
    files: list[Path] = []
    for root in ACTIVE_ROOTS:
        for path in root.rglob("*.py"):
            if path.resolve() == ENFORCEMENT_FILE:
                continue
            if any(part in {"__pycache__", ".pytest_cache", ".venv", "venv"} for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def test_archive_rule_is_documented() -> None:
    readme = ROOT / "docs" / "archiv" / "README.md"

    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "ausschließlich historisches Material" in text
    assert "Nichts daraus ist Teil der Runtime" in text
    assert "Nichts daraus ist Teil der Tests" in text
    assert "Nichts daraus ist Teil des öffentlichen CLI- oder API-Contracts" in text


def test_active_python_does_not_depend_on_archive_material() -> None:
    forbidden_fragments = [
        "docs" + "/" + "archiv",
        "docs" + '" / "' + "archiv",
        "docs" + "' / '" + "archiv",
    ]

    offenders: list[str] = []
    for path in _active_python_files():
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {fragment}")

    assert offenders == []
