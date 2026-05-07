"""Runtime tool registry models and guardrail decisions for runtime-tool."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from nexusctl.domain.errors import ValidationError


class RuntimeToolDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


class RuntimeToolSideEffect(StrEnum):
    READ_ONLY = "read_only"
    SIMULATION = "simulation"
    PAPER_TRADE = "paper_trade"
    LIVE_TRADE = "live_trade"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True, slots=True)
class RuntimeTool:
    id: str
    name: str
    domain: str
    capability: str
    side_effect: RuntimeToolSideEffect
    command: str
    description: str = ""
    enabled: bool = True
    approval_required: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RuntimeTool":
        for field in ("id", "domain", "capability", "side_effect", "command"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                raise ValidationError(f"runtime tool missing non-empty {field}")
        return cls(
            id=data["id"].strip(),
            name=str(data.get("name") or data["id"]).strip(),
            domain=data["domain"].strip(),
            capability=data["capability"].strip(),
            side_effect=RuntimeToolSideEffect(data["side_effect"].strip()),
            command=data["command"].strip(),
            description=str(data.get("description") or ""),
            enabled=bool(data.get("enabled", True)),
            approval_required=bool(data.get("approval_required", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "capability": self.capability,
            "side_effect": self.side_effect.value,
            "command": self.command,
            "description": self.description,
            "enabled": self.enabled,
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True, slots=True)
class RuntimeToolCheck:
    tool_id: str
    agent_id: str
    agent_domain: str
    decision: RuntimeToolDecision
    reasons: tuple[str, ...]
    side_effect: RuntimeToolSideEffect
    required_capability: str

    @property
    def allowed(self) -> bool:
        return self.decision == RuntimeToolDecision.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "agent_id": self.agent_id,
            "agent_domain": self.agent_domain,
            "decision": self.decision.value,
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "side_effect": self.side_effect.value,
            "required_capability": self.required_capability,
        }
