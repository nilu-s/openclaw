from __future__ import annotations

from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Create the smallest project shape useful for unit tests.

    Prefer this fixture for tests that only need a project root and a few
    hand-authored files. It avoids copying the whole repository into tmp_path.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / "nexus").mkdir()
    (project / "generated").mkdir()
    return project


@pytest.fixture
def repo_project_copy(tmp_path: Path) -> Path:
    """Copy the repository for integration tests that need the real layout."""
    project = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        project,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
            "__pycache__",
            "*.pyc",
            ".venv",
            "dist",
            "build",
            ".mypy_cache",
            ".ruff_cache",
            "nexus.db",
        ),
    )
    return project
