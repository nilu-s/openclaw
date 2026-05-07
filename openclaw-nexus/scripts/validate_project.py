#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
ARCHIVED_TEST_NAME_RE = re.compile(r"test_(?:" + "pha" + "se|" + "v" + "p)\\d|test_" + "pha" + "se_|test_" + "v" + "p", re.IGNORECASE)
ARCHIVED_ROOT_DOC_FILES = {"P" + "HASES.md", "pha" + "sen.md", "PROJECT" + "_STATE.json", "endzustand.md"}

REQUIRED_PATHS = [
    "README.md",
    ".chatgpt/state/CURRENT_STATE.md",
    ".chatgpt/README.md",
    ".chatgpt/skills/sprint-workflow/SKILL.md",
    ".chatgpt/state/phases.md",
    "nexus/blueprint.yml",
    "nexus/domains.yml",
    "nexus/agents.yml",
    "nexus/capabilities.yml",
    "nexus/goals.yml",
    "nexus/schedules.yml",
    "nexus/github.yml",
    "nexus/policies.yml",
    "nexus/standing-orders.yml",
    "nexus/runtime-tools.yml",
    "nexusctl/pyproject.toml",
    "pytest.ini",
    "config/docker-compose.yml",
    "config/Dockerfile.openclaw",
    "config/Dockerfile.nexusctl",
    "config/.env.example",
    "generated/openclaw/openclaw.json",
    "scripts/package_project.py",
    "scripts/run_tests.sh",
    "scripts/validate_project.py",
    "scripts/close_sprint.py",
    "tests/test_blueprint_contract.py",
    "tests/test_policy_contract.py",
    "tests/test_storage_sqlite.py",
    "tests/test_auth_identity.py",
    "tests/test_goals_evidence.py",
    "tests/test_feature_requests.py",
    "tests/test_github_projection.py",
    "tests/test_work_scopes.py",
    "tests/test_patch_proposals.py",
    "tests/test_policy_checks.py",
    "tests/test_review_acceptance.py",
    "tests/test_merge_gate.py",
    "tests/test_webhooks_reconciliation.py",
    "tests/test_openclaw_generation.py",
    "tests/test_schedules.py",
    "tests/test_docker_runtime.py",
    "tests/test_runtime_tools.py",
    "tests/test_http_api.py",
    "tests/test_e2e_delivery_flow.py",
    "tests/test_http_cli_client.py",
    "tests/test_http_cli_parity.py",
    "tests/test_operational_hardening.py",
    "tests/test_github_hardening.py",
    "tests/test_test_strategy.py",
    "tests/test_doctor_reports.py",
    "tests/test_architecture_contracts.py",
    "nexusctl/src/nexusctl/domain/models.py",
    "nexusctl/src/nexusctl/domain/states.py",
    "nexusctl/src/nexusctl/domain/runtime_tools.py",
    "nexusctl/src/nexusctl/domain/errors.py",
    "nexusctl/src/nexusctl/authz/subject.py",
    "nexusctl/src/nexusctl/authz/capability_matrix.py",
    "nexusctl/src/nexusctl/authz/policy_engine.py",
    "nexusctl/src/nexusctl/authz/token_registry.py",
    "nexusctl/src/nexusctl/app/acceptance_service.py",
    "nexusctl/src/nexusctl/app/goal_service.py",
    "nexusctl/src/nexusctl/app/feature_request_service.py",
    "nexusctl/src/nexusctl/app/github_service.py",
    "nexusctl/src/nexusctl/app/work_service.py",
    "nexusctl/src/nexusctl/app/scope_service.py",
    "nexusctl/src/nexusctl/app/patch_service.py",
    "nexusctl/src/nexusctl/app/check_service.py",
    "nexusctl/src/nexusctl/app/review_service.py",
    "nexusctl/src/nexusctl/app/merge_service.py",
    "nexusctl/src/nexusctl/app/reconciliation_service.py",
    "nexusctl/src/nexusctl/app/generation_service.py",
    "nexusctl/src/nexusctl/app/schedule_service.py",
    "nexusctl/src/nexusctl/app/runtime_tool_service.py",
    "nexusctl/src/nexusctl/interfaces/cli/main.py",
    "nexusctl/src/nexusctl/interfaces/http/auth.py",
    "nexusctl/src/nexusctl/interfaces/http/routes.py",
    "nexusctl/src/nexusctl/interfaces/http/schemas.py",
    "nexusctl/src/nexusctl/interfaces/http/server.py",
    "nexusctl/src/nexusctl/storage/event_store.py",
    "nexusctl/src/nexusctl/storage/sqlite/connection.py",
    "nexusctl/src/nexusctl/storage/sqlite/schema.py",
    "nexusctl/src/nexusctl/storage/sqlite/migrations.py",
    "nexusctl/src/nexusctl/storage/sqlite/repositories.py",
    "nexusctl/src/nexusctl/adapters/github/app_auth.py",
    "nexusctl/src/nexusctl/adapters/github/client.py",
    "nexusctl/src/nexusctl/adapters/github/checks.py",
    "nexusctl/src/nexusctl/adapters/github/reviews.py",
    "nexusctl/src/nexusctl/adapters/github/pulls.py",
    "nexusctl/src/nexusctl/adapters/github/webhooks.py",
    "nexusctl/src/nexusctl/adapters/git/worktree.py",
    "nexusctl/src/nexusctl/adapters/git/diff.py",
    "nexusctl/src/nexusctl/adapters/git/applier.py",
    "nexusctl/src/nexusctl/adapters/openclaw/config_writer.py",
    "nexusctl/src/nexusctl/adapters/openclaw/agent_writer.py",
    "nexusctl/src/nexusctl/adapters/openclaw/skill_writer.py",
    "nexusctl/src/nexusctl/adapters/openclaw/schedule_writer.py",
]
REQUIRED_DIRS = [
    "nexus",
    "nexusctl",
    "nexusctl/src/nexusctl/domain",
    "nexusctl/src/nexusctl/authz",
    "nexusctl/src/nexusctl/app",
    "nexusctl/src/nexusctl/storage/sqlite",
    "nexusctl/src/nexusctl/adapters/github",
    "nexusctl/src/nexusctl/adapters/git",
    "nexusctl/src/nexusctl/adapters/openclaw",
    "nexusctl/src/nexusctl/interfaces/cli/commands",
    "nexusctl/src/nexusctl/interfaces/http",
    "generated/openclaw",
    "generated/agents",
    "generated/skills",
    "config",
    "scripts",
    "tests",
    "docs/" + "arch" + "iv/sprints",
]
FORBIDDEN_ACTIVE_LEGACY_PATHS = [
    "referenzen",
    "referenzen/setup",
    "generated/imports",
]
FORBIDDEN_REQUIRED_LEGACY_PATHS = [
    "tests/test_legacy_import.py",
    "referenzen",
    "referenzen/setup",
    "generated/imports",
]
EXPECTED_AGENTS = {
    "operator", "control-router", "merge-applier", "platform-maintainer", "software-architect", "software-techlead",
    "software-builder", "software-reviewer", "trading-strategist", "trading-analyst", "trading-sentinel",
}
EXPECTED_DOMAINS = {"control", "platform", "software", "trading", "research"}
REQUIRED_POLICY_IDS = {
    "agent_domain_is_auth_derived",
    "normal_agents_no_cross_domain_mutation",
    "cross_domain_work_uses_feature_requests",
    "trading_no_software_code_capabilities",
    "software_no_trading_strategy_mutation",
    "builder_no_repo_apply_or_review",
    "github_projection_not_authority",
    "github_writes_only_via_app",
    "no_direct_agent_github_write",
    "no_direct_builder_repo_apply",
    "events_append_only",
    "merge_only_merge_applier",
    "github_webhook_signatures_required",
    "github_reconciliation_alerts_unknown_drift",
    "control_config_mutations_via_nexusctl_flow",
    "control_store_mutations_via_nexusctl_services",
    "generated_runtime_config_mutations_via_nexusctl_generation",
    "schedules_mutated_via_nexusctl_control_flow",
}
REQUIRED_RUNTIME_ARTIFACTS = [
    "generated/openclaw/openclaw.json",
    "generated/skills/nexusctl_goal_ops.json",
    "generated/skills/nexusctl_feature_request_ops.json",
    "generated/skills/nexusctl_patch_proposal.json",
    "generated/skills/nexusctl_review.json",
    "generated/skills/nexusctl_acceptance.json",
    "generated/skills/nexusctl_merge_apply.json",
    "generated/skills/nexusctl_github_reconciliation.json",
    "generated/skills/runtime_integrity.json",
]


def fail(errors: list[str], msg: str) -> None:
    errors.append(msg)


def load_yaml(rel: str, errors: list[str]) -> dict[str, Any]:
    path = ROOT / rel
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(errors, f"{rel}: cannot parse YAML: {exc}")
        return {}
    if not isinstance(data, dict):
        fail(errors, f"{rel}: top-level YAML must be a mapping")
        return {}
    return data


def as_list(data: dict[str, Any], key: str, rel: str, errors: list[str]) -> list[dict[str, Any]]:
    items = data.get(key)
    if not isinstance(items, list):
        fail(errors, f"{rel}: missing list '{key}'")
        return []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            fail(errors, f"{rel}: {key}[{idx}] must be a mapping")
        else:
            out.append(item)
    return out


def check_unique_ids(items: list[dict[str, Any]], label: str, errors: list[str]) -> set[str]:
    ids: set[str] = set()
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not ID_RE.match(item_id):
            fail(errors, f"{label}: invalid id {item_id!r}")
            continue
        if item_id in ids:
            fail(errors, f"{label}: duplicate id {item_id}")
        ids.add(item_id)
    return ids


def check_required_structure_is_target_version(errors: list[str]) -> None:
    required_entries = set(REQUIRED_PATHS) | set(REQUIRED_DIRS)
    legacy_entries = required_entries & set(FORBIDDEN_REQUIRED_LEGACY_PATHS)
    if legacy_entries:
        fail(errors, f"project validation still requires legacy paths: {sorted(legacy_entries)}")


def check_forbidden_active_legacy_paths(errors: list[str]) -> None:
    for rel in FORBIDDEN_ACTIVE_LEGACY_PATHS:
        if (ROOT / rel).exists():
            fail(errors, f"legacy path must not be active in target version: {rel}")


def root_file_exists_with_exact_name(filename: str) -> bool:
    return any(path.name == filename and path.is_file() for path in ROOT.iterdir())


def check_active_documentation(errors: list[str]) -> None:
    for filename in ARCHIVED_ROOT_DOC_FILES:
        if root_file_exists_with_exact_name(filename):
            fail(errors, f"historical root document must be archived, not active: {filename}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    state = (ROOT / ".chatgpt" / "state" / "CURRENT_STATE.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".chatgpt" / "skills" / "sprint-workflow" / "SKILL.md").read_text(encoding="utf-8")
    if "OpenClaw Nexus" not in readme or "Nexusctl ist die Source of Truth" not in readme:
        fail(errors, "README.md must describe the OpenClaw Nexus product goal")
    forbidden_readme_process_terms = [
        "Produktions-Sprint-Workflow",
        "Führe die nächste Phase aus",
        "Akzeptanzkriterien",
        "Standardvalidierung",
        "Übergabeprozess",
    ]
    for term in forbidden_readme_process_terms:
        if term in readme:
            fail(errors, f"README.md must stay product-focused and not describe process term: {term}")
    if "Ist-Zustand" not in state:
        fail(errors, "CURRENT_STATE.md must describe the current state")
    required_workflow_terms = [
        "openclaw-nexus.zip",
        "phases.md",
        "Akzeptanzkriterien",
        "Führe die nächste Phase aus",
        "kein Kompatibilitätszwang",
        "maximal Fast-Tests",
        "vier Stunden",
        "./scripts/run_tests.sh fast",
        "Nicht als Standardvalidierung ausführen",
        "Clear-Up-Funktion",
        "Schließe den aktuellen Sprint ab",
        "clear Sprint",
        "LLM-Doublecheck",
        "Abschluss-Doublecheck",
        "Current-State-Delta",
        "CURRENT_STATE.md` beschreibt nur den zuletzt abgeschlossenen",
        "docs/" + "arch" + "iv/sprints/",
        "python scripts/close_sprint.py",
    ]
    for term in required_workflow_terms:
        if term not in workflow:
            fail(errors, f".chatgpt/skills/sprint-workflow/SKILL.md must define workflow term: {term}")
    if not workflow.startswith("---\n"):
        fail(errors, ".chatgpt/skills/sprint-workflow/SKILL.md must start with YAML frontmatter")
    else:
        try:
            frontmatter = workflow.split("---", 2)[1]
            skill_meta = yaml.safe_load(frontmatter)
        except Exception as exc:
            fail(errors, f".chatgpt/skills/sprint-workflow/SKILL.md: cannot parse YAML frontmatter: {exc}")
            skill_meta = {}
        if not isinstance(skill_meta, dict):
            fail(errors, ".chatgpt/skills/sprint-workflow/SKILL.md: YAML frontmatter must be a mapping")
        else:
            if skill_meta.get("name") != "sprint-workflow":
                fail(errors, ".chatgpt/skills/sprint-workflow/SKILL.md must define name: sprint-workflow")
            if not isinstance(skill_meta.get("description"), str) or not skill_meta.get("description", "").strip():
                fail(errors, ".chatgpt/skills/sprint-workflow/SKILL.md must define a non-empty description")
    close_script = (ROOT / "scripts" / "close_sprint.py").read_text(encoding="utf-8")
    for term in ["LLM-Doublecheck", "Current-State-Delta", "Refusing to close sprint"]:
        if term not in close_script:
            fail(errors, f"scripts/close_sprint.py must enforce close-sprint marker: {term}")

    phases = (ROOT / ".chatgpt" / "state" / "phases.md").read_text(encoding="utf-8")
    if phases.strip():
        required_phase_terms = ["Sprint-Log", "aktuelle_phase", "Akzeptanzkriterien", "Validierung", "Current-State-Delta"]
        for term in required_phase_terms:
            if term not in phases:
                fail(errors, f"non-empty phases.md must contain sprint-log term: {term}")


def check_test_names(errors: list[str]) -> None:
    for path in (ROOT / "tests").glob("test_*.py"):
        if ARCHIVED_TEST_NAME_RE.search(path.name):
            fail(errors, f"test file is still named after implementation history: {path.relative_to(ROOT)}")
        text = path.read_text(encoding="utf-8")
        for match in re.findall(r"def\s+(test_[a-zA-Z0-9_]+)", text):
            if ARCHIVED_TEST_NAME_RE.search(match):
                fail(errors, f"test function is still named after implementation history: {path.relative_to(ROOT)}::{match}")


def validate() -> list[str]:
    errors: list[str] = []

    for rel in REQUIRED_DIRS:
        if not (ROOT / rel).is_dir():
            fail(errors, f"missing required directory: {rel}")
    for rel in REQUIRED_PATHS:
        if not (ROOT / rel).is_file():
            fail(errors, f"missing required file: {rel}")

    check_required_structure_is_target_version(errors)
    check_forbidden_active_legacy_paths(errors)
    check_active_documentation(errors)
    check_test_names(errors)

    blueprint = load_yaml("nexus/blueprint.yml", errors)
    domains_yml = load_yaml("nexus/domains.yml", errors)
    agents_yml = load_yaml("nexus/agents.yml", errors)
    capabilities_yml = load_yaml("nexus/capabilities.yml", errors)
    policies_yml = load_yaml("nexus/policies.yml", errors)
    goals_yml = load_yaml("nexus/goals.yml", errors)
    schedules_yml = load_yaml("nexus/schedules.yml", errors)
    github_yml = load_yaml("nexus/github.yml", errors)
    runtime_tools_yml = load_yaml("nexus/runtime-tools.yml", errors)

    domain_ids = check_unique_ids(as_list(domains_yml, "domains", "nexus/domains.yml", errors), "domains", errors)
    agent_items = as_list(agents_yml, "agents", "nexus/agents.yml", errors)
    agent_ids = check_unique_ids(agent_items, "agents", errors)
    capability_ids = check_unique_ids(as_list(capabilities_yml, "capabilities", "nexus/capabilities.yml", errors), "capabilities", errors)
    policy_ids = check_unique_ids(as_list(policies_yml, "rules", "nexus/policies.yml", errors), "policies", errors)
    goal_ids = check_unique_ids(as_list(goals_yml, "goals", "nexus/goals.yml", errors), "goals", errors)
    schedule_ids = check_unique_ids(as_list(schedules_yml, "schedules", "nexus/schedules.yml", errors), "schedules", errors)
    tool_ids = check_unique_ids(as_list(runtime_tools_yml, "tools", "nexus/runtime-tools.yml", errors), "runtime tools", errors)

    if not EXPECTED_DOMAINS.issubset(domain_ids):
        fail(errors, f"domains missing expected ids: {sorted(EXPECTED_DOMAINS - domain_ids)}")
    if not EXPECTED_AGENTS.issubset(agent_ids):
        fail(errors, f"agents missing expected ids: {sorted(EXPECTED_AGENTS - agent_ids)}")
    if not REQUIRED_POLICY_IDS.issubset(policy_ids):
        fail(errors, f"policies missing expected ids: {sorted(REQUIRED_POLICY_IDS - policy_ids)}")
    if "runtime.tool.invoke" not in capability_ids:
        fail(errors, "capabilities must include runtime.tool.invoke")
    if not goal_ids:
        fail(errors, "at least one goal must be declared")
    if not schedule_ids:
        fail(errors, "at least one schedule must be declared")
    if not tool_ids:
        fail(errors, "at least one runtime tool must be declared")

    for agent in agent_items:
        agent_id = agent.get("id")
        domain = agent.get("domain")
        role = agent.get("role")
        caps = agent.get("capabilities", [])
        if domain not in domain_ids:
            fail(errors, f"agent {agent_id}: unknown domain {domain!r}")
        if not isinstance(role, str) or not role:
            fail(errors, f"agent {agent_id}: missing role")
        if not isinstance(caps, list):
            fail(errors, f"agent {agent_id}: capabilities must be a list")
            continue
        unknown = set(caps) - capability_ids
        if unknown:
            fail(errors, f"agent {agent_id}: unknown capabilities {sorted(unknown)}")

    if blueprint.get("project") != "openclaw-nexus":
        fail(errors, "nexus/blueprint.yml must identify project openclaw-nexus")

    github_repos = as_list(github_yml.get("github", {}) if isinstance(github_yml.get("github"), dict) else {}, "repositories", "nexus/github.yml", errors)
    if not github_repos:
        fail(errors, "nexus/github.yml must define at least one repository projection")

    for rel in REQUIRED_RUNTIME_ARTIFACTS:
        path = ROOT / rel
        if not path.is_file():
            fail(errors, f"missing runtime artifact: {rel}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(errors, f"{rel}: invalid JSON: {exc}")

    openclaw = ROOT / "generated/openclaw/openclaw.json"
    if openclaw.exists():
        data = json.loads(openclaw.read_text(encoding="utf-8"))
        metadata = data.get("_generated", {})
        if not isinstance(metadata, dict) or metadata.get("generated_by") != "nexusctl":
            fail(errors, "generated/openclaw/openclaw.json must include nexusctl generated metadata")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Project validation failed:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1
    print("Project validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
