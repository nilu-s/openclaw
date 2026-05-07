from __future__ import annotations

from nexusctl.backend.integrations.github import derive_checks_state


def test_checks_state_failing_wins():
    assert derive_checks_state({"check_runs": [{"status": "completed", "conclusion": "failure"}]}, {"state": "success"}) == "failing"


def test_checks_state_pending():
    assert derive_checks_state({"check_runs": [{"status": "in_progress", "conclusion": None}]}, None) == "pending"


def test_checks_state_passing():
    assert derive_checks_state({"check_runs": [{"status": "completed", "conclusion": "success"}]}, {"state": "success"}) == "passing"


def test_checks_state_unknown_without_data():
    assert derive_checks_state(None, None) == "unknown"
