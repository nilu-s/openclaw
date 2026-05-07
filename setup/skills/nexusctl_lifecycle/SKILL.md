---
name: nexusctl_lifecycle
description: Use Nexus v2 as the source of truth for goals, requests, work, scopes, lifecycle, and evidence through nexusctl.
---

# Nexusctl Lifecycle

Use this skill whenever the task mentions Nexus, lifecycle state, goals, requests, work, reviews, capabilities, evidence, or handoffs.

## Start Here

```bash
nexusctl context --output json
```

Use Nexus as source of truth for systems, goals, requests, work, scopes, lifecycle, ownership, and evidence. Use GitHub as source of truth for code, issues, pull requests, reviews, and CI only through the Nexus GitHub adapter by default.

## Canonical Commands

- Context: `nexusctl context --output json`
- Goals: `nexusctl goals list|show|create|update-status ... --output json`
- Capabilities: `nexusctl capabilities list|show|set-status ... --output json`
- Runtime tools: `nexusctl runtime-tools list|show ... --output json`
- Requests: `nexusctl request list|show|create|transition ... --output json`
- Work: `nexusctl work list|show|plan|set-implementation-context|approve-plan|assign|transition|submit-evidence ... --output json`
- Reviews: `nexusctl reviews list|submit ... --output json`

## Lifecycle Statuses

`draft`, `submitted`, `gate-rejected`, `accepted`, `needs-planning`, `ready-to-build`, `in-build`, `in-review`, `approved`, `review-failed`, `state-update-needed`, `done`, `adoption-pending`, `closed`, `cancelled`.

Before transition, check the current object with `show --output json`; do not guess valid transitions.

## Field Names

Use `goal_ref` and CLI flag `--goal-ref`. Do not use legacy names for goal references.
