# Nexus Source of Truth v1.2

## Responsibilities

Nexus stores the domain source of truth for OpenClaw agents:

- systems
- goals
- capabilities
- runtime tools
- requests / handoffs
- repositories
- work assignments
- reviews
- evidence
- scopes

OpenClaw controls runtime isolation and tool availability. GitHub controls code, issues, PRs and CI artifacts.

## Internal rule

`system_id` is persisted for every domain object. Agents do not need to provide it when the backend can infer exactly one default/visible system from their effective scopes.

## Visibility rule

Domain agents see their domain. Software agents see the software lane and assigned implementation work. Builders/reviewers do not see full trading goals by default.

## Work item rule

A software agent never scans all repos as its normal entrypoint. It starts from:

```bash
nexusctl work list
nexusctl work show <request_id>
nexusctl repos assigned
```

## GitHub rule

GitHub issues and PRs are linked artifacts. They are not the leading source of truth for cross-agent lifecycle.

## Trading safety rule

Agents create intents/requests. Deterministic services perform risk checks and any side-effectful execution. Live trading remains blocked until policy, evidence and explicit approval exist.
