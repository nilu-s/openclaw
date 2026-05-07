from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

import pytest
import yaml

from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.domain.errors import PolicyDeniedError
from nexusctl.domain.models import FeatureRequest, GitHubLink, Goal, ScopeLease, WorkItem
from nexusctl.domain.states import GitHubLinkKind, ScopeLeaseStatus


def load_yaml(rel: str):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> CapabilityMatrix:
    return CapabilityMatrix.from_project_root(ROOT)


@pytest.fixture(scope="module")
def policy(matrix: CapabilityMatrix) -> PolicyEngine:
    return PolicyEngine(matrix)


def test_policy_domain_models_construct_from_blueprint(matrix: CapabilityMatrix) -> None:
    assert set(matrix.domains) >= {"control", "platform", "software", "trading"}
    assert matrix.agents["software-builder"].domain == "software"
    assert matrix.agents["trading-strategist"].normal_agent is True
    assert matrix.capabilities["feature_request.create"].target_domain_allowed is True

    trade_goal = next(
        Goal.from_mapping(goal)
        for goal in __import__("yaml").safe_load((ROOT / "nexus/goals.yml").read_text(encoding="utf-8"))["goals"]
        if goal["id"] == "trade_success_quality"
    )
    assert trade_goal.domain == "trading"
    assert {metric.id for metric in trade_goal.metrics} >= {"win_rate", "max_drawdown_pct"}


def test_policy_core_entities_are_available() -> None:
    request = FeatureRequest(
        id="fr-trading-software-001",
        source_domain="trading",
        target_domain="software",
        created_by="trading-strategist",
        summary="Need a new backtest report export.",
    )
    work = WorkItem(id="work-001", domain="software", feature_request_id=request.id)
    lease = ScopeLease(
        id="lease-001",
        work_item_id=work.id,
        agent_id="software-builder",
        domain="software",
        capabilities=("patch.submit",),
        granted_by="control-router",
        status=ScopeLeaseStatus.ACTIVE,
    )
    link = GitHubLink(
        id="gh-001",
        nexus_entity_id=request.id,
        kind=GitHubLinkKind.ISSUE,
        repository_id="primary",
        external_id="42",
    )

    assert request.target_domain == "software"
    assert work.feature_request_id == request.id
    assert lease.capabilities == ("patch.submit",)
    assert link.kind is GitHubLinkKind.ISSUE


def test_trading_strategist_can_request_software_but_cannot_submit_patch(
    matrix: CapabilityMatrix, policy: PolicyEngine
) -> None:
    strategist = matrix.subject_for_agent("trading-strategist")

    allowed = policy.authorize(strategist, "feature_request.create", target_domain="software")
    assert allowed.allowed is True

    denied = policy.authorize(strategist, "patch.submit", resource_domain="software")
    assert denied.allowed is False
    assert denied.rule_id in {"capability_not_granted", "domain_capability_denied"}


def test_software_builder_can_submit_patch_but_cannot_review_or_apply(
    matrix: CapabilityMatrix, policy: PolicyEngine
) -> None:
    builder = matrix.subject_for_agent("software-builder")

    assert policy.authorize(builder, "patch.submit", resource_domain="software").allowed is True

    review = policy.authorize(builder, "review.approve", resource_domain="software")
    assert review.allowed is False

    repo_apply = policy.authorize(builder, "repo.apply", resource_domain="software")
    assert repo_apply.allowed is False


def test_control_router_routes_and_grants_scopes_but_does_not_approve_reviews(
    matrix: CapabilityMatrix, policy: PolicyEngine
) -> None:
    nexus = matrix.subject_for_agent("control-router")

    assert policy.authorize(nexus, "feature_request.route", target_domain="software").allowed is True
    assert policy.authorize(nexus, "scope.lease.grant", target_domain="software").allowed is True

    denied = policy.authorize(nexus, "review.approve", resource_domain="software")
    assert denied.allowed is False


def test_normal_agent_domain_override_is_forbidden(matrix: CapabilityMatrix, policy: PolicyEngine) -> None:
    builder = matrix.subject_for_agent("software-builder")

    denied = policy.authorize(
        builder,
        "patch.submit",
        resource_domain="software",
        requested_domain="trading",
    )
    assert denied.allowed is False
    assert denied.rule_id == "agent_domain_is_auth_derived"

    with pytest.raises(PolicyDeniedError):
        policy.require(builder, "patch.submit", resource_domain="software", requested_domain="trading")


def test_policy_contract_covers_authority_boundaries() -> None:
    policies = load_yaml("nexus/policies.yml")
    policy_ids = {rule["id"] for rule in policies["rules"]}

    assert "control_config_mutations_via_nexusctl_flow" in policy_ids
    assert "control_store_mutations_via_nexusctl_services" in policy_ids
    assert "generated_runtime_config_mutations_via_nexusctl_generation" in policy_ids
    assert "schedules_mutated_via_nexusctl_control_flow" in policy_ids

    capabilities = load_yaml("nexus/capabilities.yml")
    cap_by_id = {cap["id"]: cap for cap in capabilities["capabilities"]}
    assert cap_by_id["runtime.generate"]["authority_boundary"] == "nexusctl_generation_only"
    assert cap_by_id["schedule.run"]["authority_boundary"] == "trigger_existing_schedule_only"
    assert cap_by_id["schedule.run"]["direct_cron_mutation_allowed"] is False
    assert capabilities["classification"]["nexusctl_generation_capabilities"] == ["runtime.generate"]
    assert capabilities["classification"]["schedule_control_capabilities"] == ["schedule.run"]
