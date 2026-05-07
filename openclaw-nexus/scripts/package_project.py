#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT.parent / f"{ROOT.name}.zip"
EXCLUDE_DIRS = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", ".venv", "venv"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip", ".db", ".sqlite", ".sqlite3"}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        rel_parts = path.relative_to(ROOT).parts
        if any(part in EXCLUDE_DIRS for part in rel_parts):
            continue
        if path.is_file() and path.suffix not in EXCLUDE_SUFFIXES:
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the OpenClaw Nexus project.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-validate", action="store_true")
    args = parser.parse_args()

    if not args.skip_validate:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_project.py")],
            cwd=ROOT,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in iter_files():
            arcname = Path(ROOT.name) / file_path.relative_to(ROOT)
            zf.write(file_path, arcname.as_posix())
    print(f"Packaged {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
