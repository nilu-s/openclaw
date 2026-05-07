from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nexusctl.interfaces.cli.main import build_parser, main

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "nexusctl" / "src"
def _active_source_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in {"__pycache__", ".pytest_cache", ".venv", "venv"} for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _source_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_removed_import_cli_command_is_not_public() -> None:
    parser = build_parser()

    assert "legacy-import" not in parser.format_help()
    with pytest.raises(SystemExit) as excinfo:
        main(["legacy-import", "--json"])
    assert excinfo.value.code == 2


def test_removed_import_service_is_not_active() -> None:
    forbidden_module = ".".join(["nexusctl", "app", "legacy_import_service"])
    forbidden_symbol = "Legacy" + "Import" + "Service"

    offenders: list[str] = []
    for path in _active_source_files(SRC_ROOT):
        tree = ast.parse(_source_text(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == forbidden_module:
                    offenders.append(path.relative_to(ROOT).as_posix())
                if any(alias.name == forbidden_symbol for alias in node.names):
                    offenders.append(path.relative_to(ROOT).as_posix())
            elif isinstance(node, ast.Import):
                if any(alias.name == forbidden_module for alias in node.names):
                    offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_active_runtime_and_tests_do_not_reference_archived_setup_tree() -> None:
    forbidden = "/".join(["referenzen", "setup"])

    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _active_source_files(SRC_ROOT, ROOT / "tests")
        if forbidden in _source_text(path)
    ]

    assert offenders == []


def test_active_source_has_no_removed_http_or_command_aliases() -> None:
    forbidden_fragments = [
        "backward-compatible",
        "backwards-compatible",
        "backward compatible",
        "backwards compatible",
        "/github" + "/webhook",
        "Nexusctl" + "Webhook" + "Handler",
        "COMMAND" + "_CAPABILITY" + "_MAP",
        "AGENT" + "_ALIASES",
    ]

    offenders: list[str] = []
    for path in _active_source_files(SRC_ROOT):
        text = _source_text(path).lower()
        for fragment in forbidden_fragments:
            if fragment.lower() in text:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {fragment}")

    assert offenders == []


def test_active_code_does_not_load_archived_import_report() -> None:
    forbidden_report = "legacy" + "_import" + "_report.json"

    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _active_source_files(SRC_ROOT)
        if forbidden_report in _source_text(path)
    ]

    assert offenders == []
