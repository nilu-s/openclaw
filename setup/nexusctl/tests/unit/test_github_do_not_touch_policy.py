from __future__ import annotations

from nexusctl.backend.integrations.github import evaluate_changed_files_policy


def test_do_not_touch_policy_detects_globs_and_exact_paths():
    result = evaluate_changed_files_policy(
        ["src/trading_engine/execution/live_orders.py", "tests/risk/test_check_order.py", "secrets/prod.env"],
        ["secrets/*", "src/trading_engine/execution/live_orders.py"],
    )
    assert result["policy_state"] == "violated"
    assert result["violations"] == ["src/trading_engine/execution/live_orders.py", "secrets/prod.env"]


def test_do_not_touch_policy_ok():
    assert evaluate_changed_files_policy(["src/a.py"], ["secrets/*"]) == {"policy_state": "ok", "violations": []}
