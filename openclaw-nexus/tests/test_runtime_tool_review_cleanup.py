from __future__ import annotations

from pathlib import Path

from nexusctl.app.runtime_tool_service import RuntimeToolRegistry, RuntimeToolService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.subject import Subject
from nexusctl.domain.runtime_tools import RuntimeToolDecision

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_tool_capability_source_is_target_runtime_configuration() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    registry = RuntimeToolRegistry(ROOT)

    access_capability = registry.guardrails["runtime_tool_access_capability"]

    assert access_capability == "runtime.tool.invoke"
    assert access_capability in matrix.capabilities
    assert registry.tools
    assert {tool.capability for tool in registry.tools.values()} <= set(matrix.capabilities)


def test_runtime_tool_review_does_not_depend_on_generated_legacy_import_reports() -> None:
    assert not (ROOT / "generated" / "imports").exists()
    assert not (ROOT / "generated" / "imports" / "legacy_import_report.json").exists()
    assert not (ROOT / "generated" / "imports" / "legacy_import_review_decisions.json").exists()


def test_runtime_tool_review_runtime_tool_invoke_capability_is_explicit_and_assigned() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    assert "runtime.tool.invoke" in matrix.capabilities

    for agent_id in (
        "operator",
        "control-router",
        "merge-applier",
        "platform-maintainer",
        "software-builder",
        "trading-analyst",
        "trading-strategist",
        "trading-sentinel",
    ):
        assert "runtime.tool.invoke" in matrix.agent(agent_id).capabilities


def test_runtime_tool_review_runtime_tool_check_requires_guardrail_capability() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    subject_without_runtime_boundary = Subject.create(
        agent_id="trading-strategist-without-runtime-boundary",
        domain="trading",
        role="strategy_owner",
        capabilities=("system.status.read", "goal.read", "trading.strategy.mutate"),
        normal_agent=True,
    )

    check = RuntimeToolService(ROOT, matrix).check_tool(subject_without_runtime_boundary, "trading.paper.order")

    assert check["decision"] == RuntimeToolDecision.DENY.value
    assert "missing_runtime_tool_invoke_capability" in check["reasons"]


def test_runtime_tool_review_runtime_guardrails_still_block_cross_domain_and_destructive_tools() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    service = RuntimeToolService(ROOT, matrix)

    software_tool = service.check_tool(matrix.subject_for_agent("trading-strategist"), "software.test.run")
    assert software_tool["decision"] == RuntimeToolDecision.DENY.value
    assert "trading_agents_cannot_invoke_software_tools" in software_tool["reasons"]

    destructive_tool = service.check_tool(matrix.subject_for_agent("merge-applier"), "nexus.repo.apply")
    assert destructive_tool["decision"] == RuntimeToolDecision.DENY.value
    assert "destructive_tools_blocked_by_default" in destructive_tool["reasons"]
