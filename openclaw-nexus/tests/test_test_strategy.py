from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_test_strategy_pytest_markers_are_declared() -> None:
    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    for marker in ["unit", "integration", "e2e", "slow", "timeout_risk"]:
        assert f"{marker}:" in pytest_ini


def test_test_strategy_runner_exposes_isolated_modes_without_shell_timeout() -> None:
    runner = (ROOT / "scripts" / "run_tests.sh").read_text(encoding="utf-8")
    for mode in ["smoke", "fast", "unit", "integration", "slow", "timeout-risk", "all", "debug", "ci"]:
        assert mode in runner
    assert 'PYTHON_BIN="${PYTHON_BIN:-}"' in runner
    assert "command -v python3" in runner
    assert "command -v timeout" not in runner
    assert "OPENCLAW_TEST_TIMEOUT" not in runner
    assert "timeout --verbose" not in runner
    assert "Outer shell timeout fired" not in runner
    assert runner.rstrip().endswith('exec "$PYTHON_BIN" "${PYTHON_OPTS[@]}" -m pytest "${PYTEST_ARGS[@]}"')
    assert "smoke)" in runner
    assert "tests/test_blueprint_contract.py" in runner
    assert "fast|unit)" in runner
    assert "not integration and not slow and not timeout_risk" in runner
    assert 'PYTHONFAULTHANDLER=1' in runner
    assert '"-X" "faulthandler"' in runner
    assert '"--full-trace"' in runner
    assert "No timeout-risk tests are currently registered." in runner


def test_test_strategy_collection_hooks_classify_risky_paths() -> None:
    hooks = (ROOT / "conftest.py").read_text(encoding="utf-8")
    for filename in [
        "test_e2e_delivery_flow.py",
        "test_http_api.py",
        "test_http_cli_client.py",
    ]:
        assert filename in hooks
    assert "pytest_collection_modifyitems" in hooks
    assert "TIMEOUT_RISK_TESTS" in hooks
    assert "pytest.mark.timeout_risk" in hooks
    assert "TIMEOUT_RISK_TESTS: set[str] = set()" in hooks
    for filename in [
        "test_auth_identity.py",
        "test_cli_command_modules.py",
        "test_goals_evidence.py",
    ]:
        assert filename not in hooks.partition("TIMEOUT_RISK_TESTS: set[str] = set()")[2]


def test_test_strategy_internal_production_docs_define_restore_drill_contract() -> None:
    docs = (ROOT / "docs" / "operations" / "internal-production.md").read_text(encoding="utf-8")

    assert "nexusctl db restore-drill" in docs
    assert '--backup-dir "$NEXUSCTL_BACKUP_DIR"' in docs
    assert "--json" in docs
    assert "Vor-Inbetriebnahme" in docs
    assert "Nach-Restore" in docs
    assert "ok` `true`" in docs
    assert "doctor_status` `ok`" in docs
    assert "failed_checks` leer" in docs
    assert "überschreibt keine Betreiber-Ziel-DB" in docs
    assert "Restore-Übungen bleiben Betriebsaufgabe außerhalb des aktuellen MVP" not in docs
    assert "der lokale Restore-Drill ist aktiver Produktbestandteil" in docs
    assert "Recovery Evidence Pack" in docs
    assert "--evidence-path" in docs
    assert "NEXUSCTL_RECOVERY_EVIDENCE_DIR" in docs
    assert "NEXUSCTL_BACKUP_RETENTION_DAYS" in docs
    assert "NEXUSCTL_BACKUP_RETENTION_MIN_COPIES" in docs
    assert "NEXUSCTL_OFFSITE_BACKUP_TARGET" in docs
    assert "Offsite-Kopie" in docs
    assert "Retention" in docs
    assert "keine echte Offsite-Absicherung" not in docs
