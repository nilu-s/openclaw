from __future__ import annotations

import ast
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "nexusctl" / "src"
sys.path.insert(0, str(SRC))

from nexusctl.app.generation_service import GenerationService


pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _py_files_under(path: Path) -> list[Path]:
    return [item for item in path.rglob("*.py") if "__pycache__" not in item.parts]


def test_architecture_cli_entrypoint_has_no_concrete_storage_imports() -> None:
    imports = _imports(SRC / "nexusctl" / "interfaces" / "cli" / "main.py")

    assert "sqlite3" not in imports
    assert not any(module.startswith("nexusctl.storage.sqlite") for module in imports)


def test_architecture_interface_storage_bootstrap_is_limited_to_composition_roots() -> None:
    interface_root = SRC / "nexusctl" / "interfaces"
    allowed = {
        Path("cli/runtime.py"),
        Path("http/routes.py"),
        Path("http/server.py"),
    }
    offenders: dict[str, list[str]] = {}

    for path in _py_files_under(interface_root):
        rel = path.relative_to(interface_root)
        imports = _imports(path)
        concrete_storage = sorted(module for module in imports if module.startswith("nexusctl.storage.sqlite"))
        if concrete_storage and rel not in allowed:
            offenders[str(rel)] = concrete_storage

    assert offenders == {}


def test_architecture_cli_main_is_a_router_not_a_storage_composition_module() -> None:
    source = (SRC / "nexusctl" / "interfaces" / "cli" / "main.py").read_text(encoding="utf-8")

    assert "def build_parser" in source
    assert "def main" in source
    assert "connect_database" not in source
    assert "init_database" not in source
    assert len(source.splitlines()) < 1200


def test_architecture_generated_artifact_contract_covers_every_expected_file(repo_project_copy: Path) -> None:
    project = repo_project_copy

    checks = GenerationService(project).doctor()["checks"]
    paths = {item["path"] for item in checks}

    generated_files = {
        path.relative_to(project).as_posix()
        for path in (project / "generated").rglob("*")
        if path.is_file()
        and path.name != ".gitkeep"
        and path.relative_to(project).parts[:2] != ("generated", "imports")
    }

    assert generated_files <= paths
    assert all(item["status"] == "ok" for item in checks)
