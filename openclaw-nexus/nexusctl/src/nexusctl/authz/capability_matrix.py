"""Blueprint-backed capability matrix for policy authorization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from nexusctl.domain.errors import UnknownAgentError, UnknownCapabilityError, UnknownDomainError, ValidationError
from nexusctl.domain.models import Agent, Capability, Domain

from .subject import Subject


@dataclass(frozen=True, slots=True)
class CapabilityMatrix:
    domains: Mapping[str, Domain]
    agents: Mapping[str, Agent]
    capabilities: Mapping[str, Capability]
    policies: Mapping[str, Any]
    classifications: Mapping[str, tuple[str, ...]]
    normal_domain_override_allowed: bool = False

    @classmethod
    def from_project_root(cls, root: str | Path) -> "CapabilityMatrix":
        root_path = Path(root)
        nexus_dir = root_path / "nexus"
        domains_yml = _load_yaml(nexus_dir / "domains.yml")
        agents_yml = _load_yaml(nexus_dir / "agents.yml")
        capabilities_yml = _load_yaml(nexus_dir / "capabilities.yml")
        policies_yml = _load_yaml(nexus_dir / "policies.yml")

        domains = {d.id: d for d in (Domain.from_mapping(item) for item in domains_yml.get("domains", []))}
        capabilities = {
            c.id: c for c in (Capability.from_mapping(item) for item in capabilities_yml.get("capabilities", []))
        }
        agents = {a.id: a for a in (Agent.from_mapping(item) for item in agents_yml.get("agents", []))}
        classifications = {
            key: tuple(value or ())
            for key, value in (capabilities_yml.get("classification") or {}).items()
        }
        normal_override = bool(
            (agents_yml.get("agent_identity") or {}).get("normal_domain_override_allowed", False)
        )
        matrix = cls(
            domains=domains,
            agents=agents,
            capabilities=capabilities,
            policies=policies_yml,
            classifications=classifications,
            normal_domain_override_allowed=normal_override,
        )
        matrix.validate_references()
        return matrix

    def validate_references(self) -> None:
        for agent in self.agents.values():
            if agent.domain not in self.domains:
                raise UnknownDomainError(f"agent {agent.id} references unknown domain {agent.domain}")
            for capability_id in agent.capabilities:
                if capability_id not in self.capabilities:
                    raise UnknownCapabilityError(f"agent {agent.id} references unknown capability {capability_id}")

    def subject_for_agent(self, agent_id: str) -> Subject:
        try:
            agent = self.agents[agent_id]
        except KeyError as exc:
            raise UnknownAgentError(f"unknown agent {agent_id}") from exc
        return Subject.create(
            agent_id=agent.id,
            domain=agent.domain,
            role=agent.role,
            capabilities=agent.capabilities,
            normal_agent=agent.normal_agent,
        )

    def capability(self, capability_id: str) -> Capability:
        try:
            return self.capabilities[capability_id]
        except KeyError as exc:
            raise UnknownCapabilityError(f"unknown capability {capability_id}") from exc

    def agent(self, agent_id: str) -> Agent:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise UnknownAgentError(f"unknown agent {agent_id}") from exc

    def assert_domain(self, domain_id: str | None) -> None:
        if domain_id is not None and domain_id not in self.domains:
            raise UnknownDomainError(f"unknown domain {domain_id}")

    def deny_capabilities_for_agent(self, agent_id: str) -> set[str]:
        denied: set[str] = set()
        for rule in self.policies.get("rules", []):
            if agent_id in (rule.get("deny_agents") or []):
                denied.update(rule.get("deny_capabilities") or [])
        return denied

    def deny_capabilities_for_domain(self, domain_id: str) -> set[str]:
        denied: set[str] = set()
        for rule in self.policies.get("rules", []):
            if domain_id in (rule.get("deny_domains") or []):
                denied.update(rule.get("deny_capabilities") or [])
        return denied


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"missing blueprint file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValidationError(f"{path} must contain a mapping")
    return data
