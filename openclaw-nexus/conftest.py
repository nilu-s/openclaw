from __future__ import annotations

from pathlib import Path

import pytest


E2E_TESTS = {"test_e2e_delivery_flow.py"}
INTEGRATION_TESTS = {
    "test_architecture_contracts.py",
    "test_doctor_reports.py",
    "test_openclaw_generation.py",
    "test_schedules.py",
    "test_webhooks_reconciliation.py",
    "test_http_api.py",
    "test_http_cli_client.py",
    "test_http_cli_parity.py",
    "test_operational_hardening.py",
}
TIMEOUT_RISK_TESTS: set[str] = set()

# Add filenames here only after a concrete timeout or hang-prone behavior has
# been reproduced and documented with the specific hang trigger. Historically
# quarantined CLI/auth/goal-evidence tests were rechecked in P2 and are now
# covered by the default fast/unit selection. Timeout-risk tests are excluded
# from the default unit mode and can be run deliberately with
# scripts/run_tests.sh timeout-risk when this set is non-empty.

SLOW_OR_BROAD_TESTS = {
    "test_storage_sqlite.py",
    "test_feature_requests.py",
    "test_work_scopes.py",
    "test_patch_proposals.py",
    "test_policy_checks.py",
    "test_review_acceptance.py",
    "test_merge_gate.py",
    "test_openclaw_generation.py",
    "test_schedules.py",
    "test_docker_runtime.py",
    "test_runtime_tools.py",
    "test_github_hardening.py",
    "test_runtime_tool_contract.py",
    "test_doctor_reports.py",
}


def _marker_for_path(path: Path) -> str:
    name = path.name
    if name in E2E_TESTS:
        return "e2e"
    if name in INTEGRATION_TESTS:
        return "integration"
    return "unit"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(str(item.fspath))
        marker = _marker_for_path(path)
        item.add_marker(getattr(pytest.mark, marker))
        if path.name in SLOW_OR_BROAD_TESTS or marker in {"integration", "e2e"}:
            item.add_marker(pytest.mark.slow)
        if path.name in TIMEOUT_RISK_TESTS:
            item.add_marker(pytest.mark.timeout_risk)
