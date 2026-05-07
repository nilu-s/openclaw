from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_package_metadata_names_current_control_plane() -> None:
    pyproject = (ROOT / "nexusctl" / "pyproject.toml").read_text(encoding="utf-8")
    package_init = (ROOT / "nexusctl" / "src" / "nexusctl" / "__init__.py").read_text(encoding="utf-8")

    assert "OpenClaw Nexus control-plane implementation" in pyproject
    assert "OpenClaw Nexus control-plane package" in package_init
    assert "Greenfield" not in pyproject
    assert "Greenfield" not in package_init
