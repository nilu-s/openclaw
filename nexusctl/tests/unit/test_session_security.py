from __future__ import annotations

from pathlib import Path

from nexusctl.session import SessionStore


def test_session_store_writes_restrictive_file_permissions(monkeypatch, tmp_path):
    calls: list[int] = []

    def _capture_chmod(self: Path, mode: int) -> None:
        calls.append(mode)

    monkeypatch.setattr(Path, "chmod", _capture_chmod, raising=True)
    path = tmp_path / "current.json"
    SessionStore._write_json(path, {"session_id": "S-1"})

    assert any(mode == 0o600 for mode in calls)
