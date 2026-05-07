"""policy Nexusctl policy engine.

This engine checks blueprint capabilities against hard MVP guardrails.  It is
pure and persistence-free so later services can call it before any mutation.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexusctl.domain.errors import PolicyDeniedError
from nexusctl.domain.models import Capability

from .capability_matrix import CapabilityMatrix
from .subject import Subject


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    rule_id: str | None = None
    capability_id: str | None = None

    def raise_if_denied(self) -> None:
        if not self.allowed:
            raise PolicyDeniedError(self.reason, rule_id=self.rule_id)


class PolicyEngine:
    """Authorize agent actions from authenticated subject identity."""

    def __init__(self, matrix: CapabilityMatrix) -> None:
        self.matrix = matrix

    def authorize(
        self,
        subject: Subject,
        capability_id: str,
        *,
        target_domain: str | None = None,
        resource_domain: str | None = None,
        requested_domain: str | None = None,
    ) -> PolicyDecision:
        """Return whether ``subject`` may exercise ``capability_id``.

        ``requested_domain`` represents an explicit domain override supplied by a
        caller.  Normal agents may not provide an override that differs from the
        authenticated domain.  ``target_domain`` is allowed for feature requests
        when the capability explicitly marks target domains as allowed.
        """

        self.matrix.assert_domain(target_domain)
        self.matrix.assert_domain(resource_domain)
        self.matrix.assert_domain(requested_domain)
        capability = self.matrix.capability(capability_id)

        denied = self._deny_if_domain_override(subject, requested_domain)
        if denied:
            return denied

        if not subject.has_capability(capability_id):
            return self._deny(
                f"{subject.agent_id} does not have capability {capability_id}",
                "capability_not_granted",
                capability_id,
            )

        if capability_id in self.matrix.deny_capabilities_for_agent(subject.agent_id):
            return self._deny(
                f"{subject.agent_id} is explicitly forbidden to use {capability_id}",
                "agent_capability_denied",
                capability_id,
            )

        if capability_id in self.matrix.deny_capabilities_for_domain(subject.domain):
            return self._deny(
                f"domain {subject.domain} is explicitly forbidden to use {capability_id}",
                "domain_capability_denied",
                capability_id,
            )

        if capability_id == "repo.apply" and subject.agent_id != "merge-applier":
            return self._deny(
                "only the Merge Applier Agent may apply or merge repository changes",
                "merge_only_merge_applier",
                capability_id,
            )

        denied = self._deny_if_forbidden_role_combination(subject, capability_id)
        if denied:
            return denied

        denied = self._deny_if_goal_read_cross_domain(subject, capability_id, resource_domain)
        if denied:
            return denied

        denied = self._deny_if_cross_domain_mutation(subject, capability, target_domain, resource_domain)
        if denied:
            return denied

        return PolicyDecision(True, "allowed", capability_id=capability_id)

    def require(
        self,
        subject: Subject,
        capability_id: str,
        *,
        target_domain: str | None = None,
        resource_domain: str | None = None,
        requested_domain: str | None = None,
    ) -> None:
        self.authorize(
            subject,
            capability_id,
            target_domain=target_domain,
            resource_domain=resource_domain,
            requested_domain=requested_domain,
        ).raise_if_denied()

    def _deny_if_domain_override(self, subject: Subject, requested_domain: str | None) -> PolicyDecision | None:
        if requested_domain is None or requested_domain == subject.domain:
            return None
        if subject.normal_agent and not self.matrix.normal_domain_override_allowed:
            return self._deny(
                "normal agent domain override is forbidden; domain is derived from auth token",
                "agent_domain_is_auth_derived",
            )
        return None

    def _deny_if_forbidden_role_combination(self, subject: Subject, capability_id: str) -> PolicyDecision | None:
        if subject.agent_id == "software-builder" and capability_id in {
            "scope.lease.grant",
            "scope.lease.revoke",
            "review.submit",
            "review.approve",
            "repo.apply",
            "github.pr.create",
        }:
            return self._deny(
                "software-builder may submit patches only; no scope grant, review, merge, or direct apply",
                "builder_no_repo_apply_or_review",
                capability_id,
            )
        if subject.agent_id == "control-router" and capability_id in {"patch.submit", "review.approve", "repo.apply"}:
            return self._deny(
                "control-router routes and grants scopes but does not implement, approve review, or apply repo changes",
                "control_router_no_implementation_or_review_approval",
                capability_id,
            )
        return None

    def _deny_if_goal_read_cross_domain(
        self, subject: Subject, capability_id: str, resource_domain: str | None
    ) -> PolicyDecision | None:
        if capability_id != "goal.read" or resource_domain in (None, subject.domain):
            return None
        if not subject.normal_agent:
            return None
        return self._deny(
            "normal agents may read only goals in their authenticated domain unless a FeatureRequest context grants visibility",
            "goal_visibility_own_domain_only",
            capability_id,
        )

    def _deny_if_cross_domain_mutation(
        self,
        subject: Subject,
        capability: Capability,
        target_domain: str | None,
        resource_domain: str | None,
    ) -> PolicyDecision | None:
        # Feature Requests are the allowed cross-domain channel. The source-domain
        # mutation remains local while target_domain documents the requested owner.
        if capability.target_domain_allowed:
            return None

        affected_domain = resource_domain or target_domain
        if not capability.mutating or affected_domain in (None, subject.domain):
            return None

        if capability.cross_domain_mutating:
            if subject.normal_agent:
                return self._deny(
                    "normal agents may not perform cross-domain mutations",
                    "normal_agents_no_cross_domain_mutation",
                    capability.id,
                )
            return None

        return self._deny(
            f"{capability.id} may mutate only the authenticated domain {subject.domain}",
            "cross_domain_work_uses_feature_requests",
            capability.id,
        )

    @staticmethod
    def _deny(reason: str, rule_id: str, capability_id: str | None = None) -> PolicyDecision:
        return PolicyDecision(False, reason, rule_id=rule_id, capability_id=capability_id)
