from __future__ import annotations

import pytest

from nexusctl.interfaces.cli.main import build_parser, main


def test_legacy_import_is_not_registered_in_cli_help() -> None:
    parser = build_parser()

    help_text = parser.format_help()

    assert "legacy-import" not in help_text


def test_legacy_import_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["legacy-import", "--json"])

    assert excinfo.value.code == 2
