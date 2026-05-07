from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(rel: str):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def test_validator_passes():
    spec = importlib.util.spec_from_file_location("validate_project", ROOT / "scripts" / "validate_project.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert module.validate() == []


def test_all_agents_have_exactly_one_known_domain():
    domains = {d["id"] for d in load_yaml("nexus/domains.yml")["domains"]}
    agents = load_yaml("nexus/agents.yml")["agents"]
    assert len(agents) == 11
    assert {a["id"] for a in agents} == {
        "operator", "control-router", "merge-applier", "platform-maintainer", "software-architect", "software-techlead",
        "software-builder", "software-reviewer", "trading-strategist", "trading-analyst", "trading-sentinel",
    }
    for agent in agents:
        assert agent["domain"] in domains
        assert isinstance(agent["domain"], str)
        assert not isinstance(agent["domain"], list)


def test_blueprint_security_capability_boundaries():
    capabilities = load_yaml("nexus/capabilities.yml")
    agents = {a["id"]: a for a in load_yaml("nexus/agents.yml")["agents"]}
    cap_by_id = {c["id"]: c for c in capabilities["capabilities"]}
    software_code_caps = set(capabilities["classification"]["software_code_capabilities"])
    trading_strategy_caps = set(capabilities["classification"]["trading_strategy_mutation_capabilities"])

    for agent in agents.values():
        caps = set(agent["capabilities"])
        if agent["normal_agent"]:
            assert not [c for c in caps if cap_by_id[c]["cross_domain_mutating"]]
        if agent["domain"] == "trading":
            assert not (caps & software_code_caps)
        if agent["domain"] == "software":
            assert not (caps & trading_strategy_caps)
        assert agent["github"]["direct_write"] is False
        assert agent["repo"]["direct_apply"] is False

    assert "patch.submit" in agents["software-builder"]["capabilities"]
    assert "review.approve" not in agents["software-builder"]["capabilities"]
    assert "repo.apply" not in agents["software-builder"]["capabilities"]
    assert "feature_request.create" in agents["trading-strategist"]["capabilities"]
    assert "patch.submit" not in agents["trading-strategist"]["capabilities"]
    assert "review.approve" not in agents["control-router"]["capabilities"]
    assert "repo.apply" in agents["merge-applier"]["capabilities"]
    assert agents["merge-applier"]["repo"]["direct_apply"] is False


def test_github_is_projection_not_authority():
    github = load_yaml("nexus/github.yml")["github"]
    assert github["role"] == "projection"
    assert github["source_of_truth"] == "nexusctl"
    assert github["lifecycle_authority"] is False
    assert github["agents_have_direct_write_tokens"] is False
    assert github["mappings"]["feature_request"]["github_type"] == "issue"
    assert github["mappings"]["feature_request"]["identity_label"] == "nexus:<feature_request_id>"


def test_required_goals_and_schedules_exist():
    goals = {g["id"]: g for g in load_yaml("nexus/goals.yml")["goals"]}
    assert set(goals) >= {"trade_success_quality", "software_delivery_quality", "runtime_integrity"}
    trade_metrics = {m["id"]: m for m in goals["trade_success_quality"]["metrics"]}
    assert trade_metrics["win_rate"]["operator"] == ">=" and trade_metrics["win_rate"]["target"] == 60
    assert trade_metrics["average_profit_pct"]["operator"] == ">=" and trade_metrics["average_profit_pct"]["target"] == 5
    assert trade_metrics["max_drawdown_pct"]["operator"] == "<=" and trade_metrics["max_drawdown_pct"]["target"] == 12
    assert trade_metrics["min_sample_size"]["operator"] == ">=" and trade_metrics["min_sample_size"]["target"] == 50
    assert goals["trade_success_quality"]["window"] == "rolling_90d"

    schedules = {s["id"]: s for s in load_yaml("nexus/schedules.yml")["schedules"]}
    assert set(schedules) >= {
        "control_router_domain_inbox_triage", "control_router_scope_expiry_guard", "software_review_queue_check",
        "software_release_readiness", "trading_goal_daily_evaluation", "trading_risk_daily_audit",
        "trading_feature_need_detection", "platform_generated_runtime_drift", "platform_db_backup",
    }
    assert all(s["agent"] != "software-builder" for s in schedules.values())



def test_authority_contract_names_nexusctl_as_only_mutation_boundary():
    blueprint = load_yaml("nexus/blueprint.yml")
    contract = blueprint["authority_contract"]

    assert contract["authoritative_mutations"] == "nexusctl_services_only"
    assert contract["control_config_mutation"] == "reviewed_repository_change_via_nexusctl_flow"
    assert contract["control_store_mutation"] == "nexusctl_app_services_only"
    assert contract["generated_runtime_config_mutation"] == "nexusctl_generation_only"
    assert contract["schedule_cron_mutation"] == "nexusctl_schedule_control_flow_only"
    assert "mutate_control_config_directly" in contract["agents_may_not"]
    assert "change_runtime_cronjobs_directly" in contract["agents_may_not"]

    openclaw = blueprint["authorities"]["openclaw"]
    assert openclaw["role"] == "runtime"
    assert openclaw["lifecycle_authority"] is False
    assert openclaw["configuration"] == "generated_openclaw_runtime_config"
    assert openclaw["generated_from"] == "control_config_via_nexusctl"
    assert openclaw["cronjobs_mutated_by"] == "nexusctl_schedule_control_flow"

    assert "control_config_mutated_only_via_nexusctl_flow" in blueprint["hard_invariants"]
    assert "generated_runtime_config_mutated_only_by_nexusctl_generation" in blueprint["hard_invariants"]
    assert "schedules_mutated_only_via_nexusctl_control_flow" in blueprint["hard_invariants"]


def test_historical_setup_tree_is_not_active_input():
    assert not (ROOT / "referenzen" / "setup").exists()
    assert not list(ROOT.rglob("*.zip"))
