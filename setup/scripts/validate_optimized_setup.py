#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
violations: list[str] = []


def fail(message: str) -> None:
    violations.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")



# Packaging/release hygiene: generated runtime/cache artifacts must never ship.
for p in root.rglob("*"):
    rel = p.relative_to(root)
    parts = set(rel.parts)
    if p.is_dir() and p.name in {"__pycache__", ".pytest_cache"}:
        fail(f"Generated cache directory must not be packaged: {rel}")
    if p.is_file() and (p.suffix == ".pyc" or p.name == ".coverage"):
        fail(f"Generated runtime artifact must not be packaged: {rel}")
    if p.is_file() and p.suffix in {".sqlite", ".sqlite3", ".db"} and "tests" not in parts:
        fail(f"Runtime database must not be packaged: {rel}")


# Documentation hygiene: keep active documentation consolidated. Agent and skill
# Markdown files are runtime contracts; the files below are historical notes or
# split docs that were intentionally folded into README files.
legacy_doc_paths = [
    "MIGRATION_NOTES.md",
    "PATCH_NOTES.md",
    "PATCH_NOTES_NEXT6.md",
    "nexusctl/NEXUSCTL_CLI_DESIGN.md",
    "nexusctl/docs/API_CONTRACT.md",
    "nexusctl/docs/GITHUB_INTEGRATION.md",
    "nexusctl/docs/SOURCE_OF_TRUTH_V1.md",
    "nexusctl/docs/SOURCE_OF_TRUTH_V2.md",
    "nexusctl/docs/TESTING.md",
    "tools/README.md",
    "tools/nexusctl/TOOL_CONTRACT.md",
    "profiles/agent-name-roster.md",
    "profiles/skill-allowlists.md",
]
for rel in legacy_doc_paths:
    if (root / rel).exists():
        fail(f"Legacy/split documentation must stay consolidated, remove: {rel}")

try:
    command_map = json.loads(read(root / "tools" / "nexusctl" / "commands.json"))
except Exception as exc:
    fail(f"Invalid tools/nexusctl/commands.json: {exc}")
else:
    required_command_keys = {
        "scopes_lease",
        "events",
        "db_backup",
        "runtime_tools_check",
        "work_plan",
        "work_transition",
        "github_alerts",
        "github_repos_sync",
    }
    missing_keys = sorted(required_command_keys - set(command_map))
    if missing_keys:
        fail(f"tools/nexusctl/commands.json is missing current command templates: {', '.join(missing_keys)}")
    if "work_plan" in command_map and "--reviewer" not in command_map["work_plan"]:
        fail("tools/nexusctl/commands.json work_plan must include --reviewer")
    if "work_transition" in command_map and "--approved-by" not in command_map["work_transition"]:
        fail("tools/nexusctl/commands.json work_transition must include --approved-by for overrides")

# JSON / config sanity
try:
    config = json.loads(read(root / "config" / "openclaw.json"))
except Exception as exc:
    raise SystemExit(f"Invalid config/openclaw.json: {exc}")

required_skills: set[str] = set(config.get("agents", {}).get("defaults", {}).get("skills", []))
agent_ids: set[str] = set()
for agent in config.get("agents", {}).get("list", []):
    agent_id = agent.get("id")
    if isinstance(agent_id, str):
        if agent_id in agent_ids:
            fail(f"Duplicate agent id in openclaw.json: {agent_id}")
        agent_ids.add(agent_id)
    required_skills.update(agent.get("skills", []))

for skill in sorted(required_skills):
    if not (root / "skills" / skill / "SKILL.md").exists():
        fail(f"Missing skill: {skill}")


# Agent tool profile hardening: only roles that implement or operate the platform
# should retain broad coding/mutating capabilities by default.
mutating_tool_agents = {"platform-optimizer", "sw-techlead", "sw-builder"}
for agent in config.get("agents", {}).get("list", []):
    agent_id = agent.get("id")
    tools = agent.get("tools", {}) if isinstance(agent.get("tools"), dict) else {}
    profile = tools.get("profile")
    if agent_id in mutating_tool_agents:
        if profile != "coding":
            fail(f"{agent_id} must retain coding profile for controlled implementation/platform work")
        if not tools.get("denyProtectedPaths"):
            fail(f"{agent_id} coding profile must deny protected paths")
    else:
        if profile == "coding":
            fail(f"{agent_id} must not use broad coding profile")
        if tools.get("denyMutatingFilesystem") is not True:
            fail(f"{agent_id} read-mostly profile must deny filesystem mutation")
        if tools.get("denyShellExec") is not True:
            fail(f"{agent_id} read-mostly profile must deny shell execution")

# Legacy/prompt-contract hygiene
banned = [
    "trading_goals_ref",
    "nexusctl handoff set-issue",
    "request set-issue",
    "gh issue create",
    "agent_persona_contract",
    "alias:",
]
for folder in ["agents", "skills"]:
    for p in (root / folder).rglob("*.md"):
        text = read(p)
        for term in banned:
            if term in text:
                fail(f"{p.relative_to(root)} contains legacy term: {term}")

# Python syntax sanity for backend/CLI/scripts
for p in list((root / "nexusctl" / "src").rglob("*.py")) + list((root / "scripts").rglob("*.py")):
    try:
        ast.parse(read(p), filename=str(p))
    except SyntaxError as exc:
        fail(f"Python syntax error in {p.relative_to(root)}: {exc}")

# Env/secret hygiene
if (root / "config" / ".env").exists():
    fail("config/.env must not be packaged; ship config/.env.example only")
example = root / "config" / ".env.example"
if not example.exists():
    fail("config/.env.example is required")
else:
    env_text = read(example)
    secret_keys = ["OPENCLAW_GATEWAY_TOKEN", "NEXUS_GITHUB_TOKEN", "NEXUS_GITHUB_WEBHOOK_SECRET"]
    for key in secret_keys:
        match = re.search(rf"^{re.escape(key)}=(.+)$", env_text, flags=re.MULTILINE)
        if match and match.group(1).strip():
            fail(f"config/.env.example must not contain a real/default value for {key}")
    if re.search(r"^OPENCLAW_REMOTE_SSH_TARGET=\S+", env_text, flags=re.MULTILINE):
        fail("config/.env.example must not include a concrete remote SSH target")

# Docker/Compose hardening
compose_path = root / "config" / "docker-compose.yml"
dockerfile_path = root / "config" / "Dockerfile"
compose = read(compose_path)
dockerfile = read(dockerfile_path)
if "--allow-insecure-remote" in compose:
    fail("docker-compose.yml must not enable --allow-insecure-remote by default")
if "- 0.0.0.0" in compose or "--host\n      - 0.0.0.0" in compose:
    fail("nexusctl-server must not bind 0.0.0.0 by default")
if "nexusctl-server:8080" in compose:
    fail("Compose should access nexusctl-server via shared loopback, not an insecure service hostname")
if re.search(r"ghcr\.io/openclaw/openclaw:latest\b", dockerfile):
    fail("Dockerfile must not pin to mutable :latest base image")
if "ARG OPENCLAW_BASE_IMAGE" not in dockerfile or "FROM ${OPENCLAW_BASE_IMAGE}" not in dockerfile:
    fail("Dockerfile must require OPENCLAW_BASE_IMAGE so deployments can pin by digest")
if re.search(r"image:\s+.*:latest\b", compose):
    fail("docker-compose.yml must not use mutable :latest image tags")
if "OPENCLAW_BASE_IMAGE:?" not in compose:
    fail("docker-compose.yml must require a digest-pinned OPENCLAW_BASE_IMAGE build arg")
if "@sha256:" not in compose:
    fail("docker-compose.yml must require OPENCLAW_BASE_IMAGE to include @sha256 digest guidance")
actual_base_image = os.environ.get("OPENCLAW_BASE_IMAGE", "").strip()
if actual_base_image and "@sha256:" not in actual_base_image:
    fail("OPENCLAW_BASE_IMAGE must be digest-pinned with @sha256 when provided to the validator")
if actual_base_image and actual_base_image.endswith(":latest"):
    fail("OPENCLAW_BASE_IMAGE must not use mutable :latest tags")
if "OPENCLAW_GATEWAY_TOKEN:?" not in compose:
    fail("docker-compose.yml must fail fast when OPENCLAW_GATEWAY_TOKEN is unset")
if re.search(r"(^|\n)\s+(GH_TOKEN|GITHUB_TOKEN):", compose):
    fail("worker compose services must not receive broad GitHub tokens; use NEXUS_GITHUB_TOKEN only on nexusctl-server")
if "NEXUS_GITHUB_TOKEN" not in compose:
    fail("nexusctl-server must receive NEXUS_GITHUB_TOKEN for the GitHub auth provider")

# Backend enforcement checks by source patterns. These are intentionally textual so
# regressions in the critical gates are caught even before integration tests run.
storage = read(root / "nexusctl" / "src" / "nexusctl" / "backend" / "storage.py")
server = read(root / "nexusctl" / "src" / "nexusctl" / "backend" / "server.py")
github = read(root / "nexusctl" / "src" / "nexusctl" / "backend" / "integrations" / "github.py")
github_event_module = read(root / "nexusctl" / "src" / "nexusctl" / "backend" / "storage_modules" / "github_events.py")
for needle, description in [
    ("_WORK_MANAGED_STATUSES", "work-managed request statuses must be explicitly defined"),
    ("_via_work_gate", "request transition bypass protection must exist"),
    ("software work status transitions must use nexus work transition gates", "direct request transition must reject software work statuses"),
    ("_scope_resource_matches", "resource_pattern matching must be enforced"),
    ("github_webhook_queued", "webhooks must enqueue/sync rather than remain passive"),
    ("process_queued_github_events", "webhooks must be processed by an explicit worker path, not synchronously in HTTP delivery"),
    ("dead_letter", "webhook sync failures must be persisted as dead letters"),
    ("reviewer_agent_id", "software reviewer assignment must be modelled separately from builder assignment"),
    ("goal_ref_aliases", "request creation must validate resolvable goal_ref aliases"),
    ("manual override cannot skip lifecycle gates", "manual override must not skip lifecycle gates"),
    ("_GITHUB_PR_SYNC_MAX_AGE", "approved/done gates must enforce fresh GitHub PR sync"),
    ("_require_fresh_github_pr_sync", "approved/done gates must reject stale GitHub PR state"),
]:
    if needle not in storage:
        fail(description)
for needle, description in [
    ("raw_body, payload = self._read_json_with_raw()", "server must preserve raw body for webhook HMAC"),
    ("verify_webhook_signature(secret=secret, body=raw_body", "webhook HMAC must use raw body"),
    ("/v1/nexus/github/webhooks/process", "server must expose an authenticated webhook worker endpoint"),
    ("self._send_json(202, storage.record_github_event", "webhook HTTP delivery should enqueue and return 202 Accepted"),
]:
    if needle not in server:
        fail(description)
for needle, description in [
    ("event_target_from_payload", "GitHub webhook target resolution must be modularized out of Storage"),
    ("GitHubEventTarget", "GitHub webhook target resolution must use an explicit event target model"),
]:
    if needle not in github_event_module:
        fail(description)
for needle, description in [
    ("_paginated_request", "GitHub client must support pagination"),
    ("latest_commit_at", "review gate must detect stale approvals"),
    ("previous_filename", "do-not-touch policy must inspect renamed files"),
    ("sensitive_defaults", "do-not-touch policy must include secret/env defaults"),
]:
    if needle not in github:
        fail(description)

# Test harness hygiene
pyproject = read(root / "nexusctl" / "pyproject.toml")
conftest = read(root / "nexusctl" / "tests" / "conftest.py")
security_tests = read(root / "nexusctl" / "tests" / "integration" / "test_security_hardening.py")
api_source = read(root / "nexusctl" / "src" / "nexusctl" / "api.py")
for needle, description in [
    ("markers = [", "pytest markers must be declared for selectable test layers"),
    ("faulthandler_timeout", "pytest faulthandler timeout must be enabled"),
]:
    if needle not in pyproject:
        fail(description)
for needle, description in [
    ("def agent_env", "unit CLI tests need a no-server env fixture"),
    ("def cli_env", "integration CLI tests need a live-server env fixture"),
]:
    if needle not in conftest:
        fail(description)
for needle, description in [
    ("Connection", "HTTP integration tests should close connections explicitly"),
    ("NEXUSCTL_AUTH_TIMEOUT_SECONDS", "networkish tests must shorten auth timeout"),
    ("test_embedded_server_stops_without_requests", "server stop without requests must be covered"),
]:
    if needle not in security_tests:
        fail(description)
for needle, description in [
    ("NEXUSCTL_TIMEOUT_SECONDS", "CLI timeout must be configurable for tests/CI"),
    ("NEXUSCTL_AUTH_TIMEOUT_SECONDS", "CLI auth timeout must be configurable for tests/CI"),
]:
    if needle not in api_source:
        fail(description)

if violations:
    raise SystemExit("\n".join(violations))

print("OK: config, skills, Python syntax, env hygiene, Docker hardening, test harness and critical Nexus/GitHub enforcement checks passed.")
