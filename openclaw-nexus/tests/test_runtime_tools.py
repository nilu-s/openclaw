from __future__ import annotations

import json
from pathlib import Path

from nexusctl.app.runtime_tool_service import RuntimeToolRegistry, RuntimeToolService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.domain.runtime_tools import RuntimeToolDecision
from nexusctl.interfaces.cli.main import main

ROOT = Path(__file__).resolve().parents[1]


def service() -> RuntimeToolService:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    return RuntimeToolService(ROOT, matrix)


def test_runtime_tool_registry_models_side_effect_levels() -> None:
    registry = RuntimeToolRegistry(ROOT)
    assert {"read_only", "simulation", "paper_trade", "live_trade", "destructive"}.issubset(set(registry.side_effect_levels))
    tools = {tool.id: tool for tool in registry.list()}
    assert "trading.backtest.simulate" in tools
    assert "trading.live.order" in tools
    assert tools["trading.paper.order"].side_effect.value == "paper_trade"


def test_guardrails_allow_read_simulation_and_paper_trading_tools() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    svc = RuntimeToolService(ROOT, matrix)

    analyst = matrix.subject_for_agent("trading-analyst")
    backtest = svc.check_tool(analyst, "trading.backtest.simulate")
    assert backtest["decision"] == RuntimeToolDecision.ALLOW.value

    strategist = matrix.subject_for_agent("trading-strategist")
    paper = svc.check_tool(strategist, "trading.paper.order")
    assert paper["decision"] == RuntimeToolDecision.ALLOW.value


def test_trading_agent_cannot_invoke_software_tool() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    check = RuntimeToolService(ROOT, matrix).check_tool(
        matrix.subject_for_agent("trading-strategist"),
        "software.test.run",
    )
    assert check["decision"] == RuntimeToolDecision.DENY.value
    assert "trading_agents_cannot_invoke_software_tools" in check["reasons"]


def test_live_and_destructive_tools_are_not_auto_allowed() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    svc = RuntimeToolService(ROOT, matrix)

    live = svc.check_tool(matrix.subject_for_agent("trading-strategist"), "trading.live.order")
    assert live["decision"] == RuntimeToolDecision.DENY.value
    assert "trading_mvp_allows_only_read_simulation_or_paper_trade" in live["reasons"]

    destructive = svc.check_tool(matrix.subject_for_agent("merge-applier"), "nexus.repo.apply")
    assert destructive["decision"] == RuntimeToolDecision.DENY.value
    assert "destructive_tools_blocked_by_default" in destructive["reasons"]


def test_runtime_tools_cli_json_commands(capsys) -> None:
    assert main(["runtime-tools", "list", "--project-root", str(ROOT), "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["ok"] is True
    assert any(tool["id"] == "trading.marketdata.read" for tool in listed["runtime_tools"])

    assert main(["runtime-tools", "show", "trading.marketdata.read", "--project-root", str(ROOT), "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["runtime_tool"]["side_effect"] == "read_only"

    assert main([
        "runtime-tools", "check", "software.test.run",
        "--agent", "trading-strategist",
        "--project-root", str(ROOT),
        "--json",
    ]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["runtime_tool_check"]["decision"] == "deny"
