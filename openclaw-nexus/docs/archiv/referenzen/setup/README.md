# OpenClaw + Nexusctl Personal Setup

This package is the cleaned personal first draft for Luis' OpenClaw runtime. It keeps one coherent operating model instead of preserving migration history.

## Active documentation

Only these Markdown files are intended as human documentation:

- `README.md` — package overview, install, OpenClaw layout, validation.
- `nexusctl/README.md` — Nexusctl source of truth, CLI/API/GitHub adapter, lifecycle, testing.
- `profiles/README.md` — agent display names, role boundaries and skill allowlists.

The many `agents/**.md` and `skills/**/SKILL.md` files are runtime prompt/skill contracts, not historical documentation. They are kept because OpenClaw consumes them as agent behavior.

## Runtime structure

```text
config/openclaw.json              OpenClaw gateway, model, tool and agent config
config/docker-compose.yml         hardened local compose setup
config/Dockerfile                 OpenClaw image wrapper; base image must be digest-pinned
agents/<agent-id>/                runtime agent contracts
skills/<skill>/SKILL.md           shared reusable procedures
tools/nexusctl/commands.json      compact command templates for agents/wrappers
nexusctl/                         Nexus control-plane source, tests and technical README
profiles/                         human-readable role/profile summary
scripts/                          install and validation helpers
```

## Design rules

1. Nexus is source of truth for systems, goals, requests, work, scopes, lifecycle and evidence.
2. GitHub is source of truth for code, issues, pull requests, reviews and CI.
3. GitHub integration is mediated through `nexusctl github ...`; worker agents do not receive broad GitHub credentials.
4. OpenClaw controls runtime isolation, available tools, agents and skill loading.
5. High-risk config, credential, security and live-trading changes require explicit same-task approval.
6. Historical migration/patch notes are not part of the active runtime package.

## Install

```bash
unzip openclaw_nexusctl_clean.zip
cd openclaw_nexusctl_clean
python3 scripts/validate_optimized_setup.py .
OPENCLAW_WORKSPACE_ROOT=/workspace ./scripts/install_optimized.sh
```

Then restart the OpenClaw Gateway and verify agent/tool visibility.

## Manual copy alternative

```bash
mkdir -p ~/.openclaw
cp config/openclaw.json ~/.openclaw/openclaw.json
cp -R agents/* ~/.openclaw/agents/
cp -R skills /workspace/skills
cp -R tools nexusctl profiles /workspace/
```

Back up existing local files before replacing them.

## Environment and secrets

`config/.env` is intentionally not shipped. Copy the example locally and fill real values outside source control:

```bash
cp config/.env.example config/.env
```

Important variables:

- `OPENCLAW_GATEWAY_TOKEN` — required gateway token.
- `OPENCLAW_BASE_IMAGE` — must be a versioned image pinned by digest with `@sha256:`.
- `NEXUS_GITHUB_TOKEN` — only for `nexusctl-server`, not worker agents.
- `NEXUS_GITHUB_WEBHOOK_SECRET` — optional webhook HMAC secret.

## Current security posture

- Gateway and Nexusctl server bind to loopback by default.
- Docker Compose does not enable `--allow-insecure-remote`.
- Example env files contain no real secrets or usable default tokens.
- GitHub credentials are scoped to the Nexusctl server environment.
- Webhook HMAC validation uses the raw request body.
- Software lifecycle changes use `nexusctl work transition` so GitHub/CI/policy gates cannot be bypassed by direct request transitions.
- Builder and reviewer assignments are separate: `assigned_agent_id` and `reviewer_agent_id`.
- Webhook events are queued, deduplicated and persisted as `dead_letter` on processing failure.

## Normal operating flow

```bash
nexusctl context --output json
nexusctl request list --status submitted --output json
nexusctl work list --status all --output json
nexusctl github alerts --output json
```

For software work:

```bash
nexusctl work show REQ-123 --output json
nexusctl work plan REQ-123 --repo trading-engine --assign sw-builder --reviewer sw-reviewer --sanitized-summary "..." --output json
nexusctl work set-implementation-context REQ-123 --likely-file src/module.py --test-command "pytest" --output json
nexusctl work approve-plan REQ-123 --output json
nexusctl github issue create REQ-123 --dry-run --output json
nexusctl github pr link REQ-123 --url https://github.com/OWNER/REPO/pull/123 --output json
nexusctl github sync REQ-123 --output json
```

## Validation

Run before packaging or deployment:

```bash
python3 scripts/validate_optimized_setup.py .
cd nexusctl
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

For the bounded test runner:

```bash
cd nexusctl
./scripts/run_tests.sh
```

## Documentation cleanup applied

The following historical or duplicate docs were folded into the active docs and removed from the package:

- `MIGRATION_NOTES.md`
- `PATCH_NOTES.md`
- `PATCH_NOTES_NEXT6.md`
- `nexusctl/NEXUSCTL_CLI_DESIGN.md`
- `nexusctl/docs/API_CONTRACT.md`
- `nexusctl/docs/GITHUB_INTEGRATION.md`
- `nexusctl/docs/SOURCE_OF_TRUTH_V1.md`
- `nexusctl/docs/SOURCE_OF_TRUTH_V2.md`
- `nexusctl/docs/TESTING.md`
- `tools/README.md`
- `tools/nexusctl/TOOL_CONTRACT.md`
- `profiles/agent-name-roster.md`
- `profiles/skill-allowlists.md`
