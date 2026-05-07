"""Runtime tool registry and guardrail service for runtime-tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.subject import Subject
from nexusctl.domain.errors import ValidationError
from nexusctl.domain.runtime_tools import RuntimeTool, RuntimeToolCheck, RuntimeToolDecision, RuntimeToolSideEffect
from nexusctl.storage.event_store import EventStore

RUNTIME_TOOL_ACCESS_CAPABILITY = "runtime.tool.invoke"

TRADING_MVP_ALLOWED = {
    RuntimeToolSideEffect.READ_ONLY,
    RuntimeToolSideEffect.SIMULATION,
    RuntimeToolSideEffect.PAPER_TRADE,
}


class RuntimeToolRegistry:
    """Blueprint-backed runtime tool registry."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        path = self.project_root / "nexus" / "runtime-tools.yml"
        if not path.is_file():
            raise ValidationError(f"missing runtime tool registry: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValidationError("runtime-tools.yml must contain a mapping")
        self.guardrails: dict[str, Any] = dict(data.get("guardrails") or {})
        self.side_effect_levels = tuple(data.get("side_effect_levels") or ())
        self.tools: dict[str, RuntimeTool] = {}
        for item in data.get("tools") or []:
            tool = RuntimeTool.from_mapping(item)
            if tool.id in self.tools:
                raise ValidationError(f"duplicate runtime tool id: {tool.id}")
            self.tools[tool.id] = tool

    def list(self) -> list[RuntimeTool]:
        return sorted(self.tools.values(), key=lambda tool: tool.id)

    def get(self, tool_id: str) -> RuntimeTool:
        try:
            return self.tools[tool_id]
        except KeyError as exc:
            raise ValidationError(f"unknown runtime tool: {tool_id}") from exc

    def validate(self, matrix: CapabilityMatrix) -> None:
        allowed_levels = set(self.side_effect_levels)
        for tool in self.tools.values():
            if tool.domain not in matrix.domains:
                raise ValidationError(f"runtime tool {tool.id} references unknown domain {tool.domain}")
            if tool.capability not in matrix.capabilities:
                raise ValidationError(f"runtime tool {tool.id} references unknown capability {tool.capability}")
            if tool.side_effect.value not in allowed_levels:
                raise ValidationError(f"runtime tool {tool.id} uses undeclared side effect {tool.side_effect.value}")


class RuntimeToolService:
    """Evaluates runtime tool access through Nexusctl guardrails."""

    def __init__(self, project_root: str | Path, matrix: CapabilityMatrix, event_store: EventStore | None = None) -> None:
        self.registry = RuntimeToolRegistry(project_root)
        self.matrix = matrix
        self.event_store = event_store
        self.registry.validate(matrix)

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in self.registry.list()]

    def show_tool(self, tool_id: str) -> dict[str, Any]:
        return self.registry.get(tool_id).to_dict()

    def check_tool(self, subject: Subject, tool_id: str) -> dict[str, Any]:
        tool = self.registry.get(tool_id)
        check = self._decide(subject, tool)
        if self.event_store is not None:
            self.event_store.append(
                aggregate_type="runtime_tool",
                aggregate_id=tool.id,
                event_type="runtime_tool.checked",
                actor_id=subject.agent_id,
                payload=check.to_dict(),
            )
        return check.to_dict()

    def _decide(self, subject: Subject, tool: RuntimeTool) -> RuntimeToolCheck:
        reasons: list[str] = []
        decision = RuntimeToolDecision.ALLOW

        if not tool.enabled:
            reasons.append("tool_disabled")
            decision = RuntimeToolDecision.DENY

        access_capability = str(self.registry.guardrails.get("runtime_tool_access_capability") or RUNTIME_TOOL_ACCESS_CAPABILITY)
        if access_capability in self.matrix.capabilities and access_capability not in subject.capabilities:
            reasons.append("missing_runtime_tool_invoke_capability")
            decision = RuntimeToolDecision.DENY

        if tool.capability not in subject.capabilities:
            reasons.append("missing_required_capability")
            decision = RuntimeToolDecision.DENY

        if subject.domain != tool.domain and subject.domain != "control":
            reasons.append("agent_domain_mismatch")
            decision = RuntimeToolDecision.DENY

        if subject.domain == "trading" and tool.domain == "software":
            reasons.append("trading_agents_cannot_invoke_software_tools")
            decision = RuntimeToolDecision.DENY

        if subject.domain == "trading" and tool.side_effect not in TRADING_MVP_ALLOWED:
            reasons.append("trading_mvp_allows_only_read_simulation_or_paper_trade")
            decision = RuntimeToolDecision.DENY

        if tool.side_effect == RuntimeToolSideEffect.DESTRUCTIVE:
            reasons.append("destructive_tools_blocked_by_default")
            decision = RuntimeToolDecision.DENY

        if tool.side_effect == RuntimeToolSideEffect.LIVE_TRADE and decision != RuntimeToolDecision.DENY:
            reasons.append("live_trade_requires_human_approval")
            decision = RuntimeToolDecision.APPROVAL_REQUIRED

        if tool.approval_required and decision == RuntimeToolDecision.ALLOW:
            reasons.append("tool_requires_human_approval")
            decision = RuntimeToolDecision.APPROVAL_REQUIRED

        if not reasons:
            reasons.append("guardrails_passed")

        return RuntimeToolCheck(
            tool_id=tool.id,
            agent_id=subject.agent_id,
            agent_domain=subject.domain,
            decision=decision,
            reasons=tuple(reasons),
            side_effect=tool.side_effect,
            required_capability=tool.capability,
        )
