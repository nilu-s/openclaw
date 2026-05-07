# OpenClaw + Nexusctl Optimized Setup

This package is an optimized replacement for the uploaded setup.

## Structure

- `config/openclaw.json` — schema-conscious optimized OpenClaw config
- `agents/<id>/` — lean agent contracts
- `skills/<skill>/SKILL.md` — shared reusable procedures
- `profiles/` — human-readable tool/skill policy snippets
- `tools/nexusctl/` — Nexusctl tool contract and command map
- `nexusctl/` — cleaned Nexusctl source/docs/tests without runtime caches
- `scripts/` — install and validation helpers

## Design principles

1. Nexus is source of truth for lifecycle, requests, work, goals, scopes, and evidence.
2. GitHub remains source of truth for code, issues, pull requests, reviews, and CI.
3. Skills hold repeatable workflows; agent files stay small.
4. `nexusctl github ...` is the default adapter path for GitHub state.
5. High-risk config/security/live-trading changes require explicit same-task approval.

## Install

```bash
unzip openclaw_nexusctl_got_names.zip
cd openclaw_nexusctl_optimized
python3 scripts/validate_optimized_setup.py .
OPENCLAW_WORKSPACE_ROOT=/workspace ./scripts/install_optimized.sh
```

Then restart the OpenClaw Gateway and verify agent/tool visibility.

## Manual copy alternative

- Copy `config/openclaw.json` to `~/.openclaw/openclaw.json` after backing up the old file.
- Copy `agents/*` to `~/.openclaw/agents/`.
- Copy `skills/*` to `/workspace/skills/` or adjust `skills.load.extraDirs`.
- Copy `tools/`, `profiles/`, and `nexusctl/` to `/workspace/`.




## Agent names

This version uses Game-of-Thrones-style display names while keeping canonical agent ids stable for routing and lifecycle ownership. See `profiles/agent-name-roster.md`.

The names are intentionally lightweight: they shape tone, working style, and handoff signatures. They are not roleplay instructions and must never override Nexus lifecycle state, OpenClaw tool policy, safety gates, or Luis' explicit instructions.
