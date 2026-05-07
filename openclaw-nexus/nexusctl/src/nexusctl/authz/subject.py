"""Authenticated Nexus subject identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Subject:
    """Identity derived from an authenticated agent token.

    The public core is intentionally the policy tuple: agent_id, domain, role,
    capabilities.  ``normal_agent`` is carried as policy metadata loaded from the
    blueprint and defaults to True for safe deny-by-default behavior.
    """

    agent_id: str
    domain: str
    role: str
    capabilities: frozenset[str]
    normal_agent: bool = True

    @classmethod
    def create(
        cls,
        agent_id: str,
        domain: str,
        role: str,
        capabilities: Iterable[str],
        *,
        normal_agent: bool = True,
    ) -> "Subject":
        return cls(
            agent_id=agent_id,
            domain=domain,
            role=role,
            capabilities=frozenset(capabilities),
            normal_agent=normal_agent,
        )

    def has_capability(self, capability_id: str) -> bool:
        return capability_id in self.capabilities
