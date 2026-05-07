# nexusctl

`nexusctl` is the command line and HTTP control plane for Nexus v2. Nexus is the source of truth for systems, goals, requests, work, scopes, lifecycle and evidence. GitHub remains the source of truth for code, issues, pull requests, reviews and CI.

## Setup

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NEXUSCTL_API_BASE_URL` | no | `http://127.0.0.1:8080` | Base URL of the nexusctl-server backend |
| `NEXUS_AGENT_TOKEN` | no | — | Agent token for automatic authentication (skips `nexusctl auth`) |
| `NEXUSCTL_AGENT_ID` | no | — | Override the agent identity (also reads `OPENCLAW_AGENT_ID`) |
| `NEXUSCTL_AGENT_DIR` | no | — | Path to agent directory for session storage |
| `NEXUSCTL_SESSION_BASE` | no | `~/.openclaw/agents` | Base path for agent session directories |
| `NEXUSCTL_SEED_TOKENS_FILE` | no | `/home/node/.openclaw/nexusctl/seed_tokens.env` | Path to seed token file for automatic auth |
| `NEXUSCTL_ALLOW_INSECURE_REMOTE` | no | — | Allow insecure HTTP to non-loopback hosts |
| `NEXUS_GITHUB_TOKEN` | no | — | GitHub personal access token (read by GitHub auth provider only) |
| `NEXUS_GITHUB_API_BASE` | no | `https://api.github.com` | GitHub API base URL |
| `NEXUS_GITHUB_WEBHOOK_SECRET` | no | — | HMAC secret for webhook signature verification |

Only the GitHub auth provider reads `NEXUS_GITHUB_TOKEN`. Worker agents receive Nexus-scoped views and commands, not global GitHub orchestration rights.

## Authentication

```bash
nexusctl auth --agent-token <TOKEN>
nexusctl auth                          # reads NEXUS_AGENT_TOKEN or seed token file
```

Authentication creates a server-side session and persists it locally. All subsequent commands reuse the active session. If `NEXUS_AGENT_TOKEN` is set, every command automatically re-authenticates.

## Commands

### Context

```bash
nexusctl context [--output table|json]
```

Returns an aggregated view of the calling agent's systems, goals, capabilities, work, repos, reviews and allowed actions.

### Systems

```bash
nexusctl systems list [--status all|planned|active|paused|retired] [--output table|json]
nexusctl systems show <system_id> [--output table|json]
```

### Goals

```bash
nexusctl goals list [--system-id ID] [--status all|proposed|active|blocked|achieved|deprecated] [--limit N] [--output table|json]
nexusctl goals show <goal_id> [--output table|json]
nexusctl goals create --goal-id ID --title TEXT --objective TEXT --risk-class low|medium|high|critical --priority P0|P1|P2|P3 \
  [--system-id ID] [--success-metric TEXT]... [--constraint TEXT]... [--owner-agent-id ID] [--status STATUS] [--parent-goal-id ID] [--output table|json]
nexusctl goals update-status <goal_id> --to proposed|active|blocked|achieved|deprecated --reason TEXT [--output table|json]
```

### Scopes

```bash
nexusctl scopes list [--agent-id ID] [--output table|json]
nexusctl scopes effective [--output table|json]
```

### Capabilities

```bash
nexusctl capabilities list [--status all|planned|in_progress|available|blocked|deprecated] [--system-id ID] [--output table|json]
nexusctl capabilities show <capability_id> [--output table|json]
nexusctl capabilities set-status <capability_id> --to planned|available --reason TEXT [--output table|json]
```

`set-status` is restricted to `sw-techlead`. MVP only allows transition to `available`.

### Runtime Tools

```bash
nexusctl runtime-tools list [--system-id ID] [--status all|planned|in_progress|available|blocked|deprecated] [--output table|json]
nexusctl runtime-tools show <tool_id> [--output table|json]
```

### Requests

```bash
nexusctl request create --objective TEXT --missing-capability TEXT --business-impact TEXT \
  --expected-behavior TEXT --acceptance-criteria TEXT... --risk-class low|medium|high|critical \
  --priority P0|P1|P2|P3 --goal-ref ID [--output table|json]

nexusctl request list [--status STATUS] [--limit N] [--output table|json]
nexusctl request show <request_id> [--output table|json]
nexusctl request transition <request_id> --to STATUS --reason TEXT [--output table|json]
```

`request create` is restricted to `trading-strategist` and `trading-sentinel`. `request transition` is restricted to `nexus` and `trading-strategist`.

### Repositories

```bash
nexusctl repos list [--output table|json]
nexusctl repos assigned [--output table|json]
nexusctl repos show <repo_id> [--output table|json]
```

### Work

```bash
nexusctl work list [--status STATUS] [--limit N] [--output table|json]
nexusctl work show <request_id> [--output table|json]
nexusctl work plan <request_id> --repo REPO_ID [--branch NAME] [--assign AGENT_ID] [--sanitized-summary TEXT] [--output table|json]
nexusctl work set-implementation-context <request_id> [--context-file PATH] [--component NAME] \
  [--entrypoint PATH]... [--likely-file PATH]... [--do-not-touch PATTERN]... [--interface NAME]... \
  [--acceptance-criteria TEXT]... [--test-command CMD]... [--notes TEXT] [--output table|json]
nexusctl work approve-plan <request_id> [--output table|json]
nexusctl work assign <request_id> --agent AGENT_ID [--output table|json]
nexusctl work transition <request_id> --to STATUS --reason TEXT [--override] [--output table|json]
nexusctl work submit-evidence <request_id> --kind KIND --summary TEXT [--ref REF] [--output table|json]
```

`work show` may display embedded GitHub status but never performs GitHub actions.

Manual override is limited to `sw-techlead` and `nexus` and always writes `manual_override` evidence:

```bash
nexusctl work transition REQ-123 --to done --override --reason "manual verification"
```

### GitHub Commands

```bash
nexusctl github issue create <request_id> [--dry-run] [--title TEXT] [--label LABEL]... [--assignee USER]... [--output table|json]
nexusctl github issue sync <request_id> [--output table|json]

nexusctl github pr link <request_id> --url URL [--output table|json]
nexusctl github pr sync <request_id> [--output table|json]

nexusctl github status <request_id> [--output table|json]
nexusctl github sync <request_id> [--output table|json]

nexusctl github repos list [--output table|json]
nexusctl github repos sync [--output table|json]
```

`github repos list` and `github repos sync` are restricted to `sw-techlead` and `nexus`.

### Reviews

```bash
nexusctl reviews list [--status STATUS] [--limit N] [--output table|json]
nexusctl reviews submit <request_id> --verdict approved|changes-requested|rejected --summary TEXT [--output table|json]
```

## Common Flow

```bash
nexusctl request create --objective "..." --missing-capability "..." --business-impact "..." \
  --expected-behavior "..." --acceptance-criteria "..." --risk-class high --priority P1 --goal-ref TG-003

nexusctl request transition REQ-123 --to accepted --reason "accepted"
nexusctl work plan REQ-123 --repo trading-engine --branch feature/req-123 --sanitized-summary "Implement deterministic risk limit checker"
nexusctl work set-implementation-context REQ-123 --component risk --likely-file src/trading_engine/risk/check_order.py --do-not-touch src/trading_engine/execution/live_orders.py --test-command "pytest tests/risk"
nexusctl work approve-plan REQ-123

nexusctl github issue create REQ-123 --dry-run
nexusctl github issue create REQ-123 --label nexus --assignee alice
nexusctl github pr link REQ-123 --url https://github.com/org/repo/pull/78
nexusctl github pr sync REQ-123
nexusctl github status REQ-123
nexusctl work transition REQ-123 --to in-review --reason "PR ready"
nexusctl work transition REQ-123 --to approved --reason "review and CI passed"
nexusctl work transition REQ-123 --to done --reason "PR merged"
```

## GitHub Adapter Overview

The Nexus GitHub Adapter v2.1 is a controlled synchronization and evidence layer. It does not clone repositories, edit code, commit, push, resolve merge conflicts, merge pull requests, crawl global repositories or give worker agents broad GitHub credentials.

GitHub metadata is stored only in dedicated adapter tables:

- `github_issues`
- `github_pull_requests`
- `github_events`

`requests` stays clean and contains only Nexus work-routing fields such as `target_repo_id`, `branch`, assignment and implementation context.

## Request Lifecycle

Requests follow a 14-status state machine with enforced transition rules:

```
draft → submitted → accepted → needs-planning → ready-to-build → in-build → in-review → approved → done → adoption-pending → closed
                  ↘ gate-rejected → draft                                                ↘ review-failed → in-build
                                                                                          ↘ state-update-needed → in-review
```

Valid transitions:

| From | Allowed To |
|---|---|
| `draft` | `submitted`, `cancelled` |
| `submitted` | `accepted`, `gate-rejected` |
| `gate-rejected` | `draft`, `cancelled` |
| `accepted` | `needs-planning` |
| `needs-planning` | `ready-to-build`, `cancelled` |
| `ready-to-build` | `in-build` |
| `in-build` | `in-review`, `cancelled` |
| `in-review` | `approved`, `review-failed`, `state-update-needed` |
| `approved` | `done`, `state-update-needed` |
| `review-failed` | `in-build` |
| `state-update-needed` | `in-review` |
| `done` | `adoption-pending`, `closed` |
| `adoption-pending` | `closed`, `needs-planning` |
| `closed` | — |
| `cancelled` | — |

## Lifecycle Gates

Transition to `in-review` requires approved implementation context and a linked PR.

Transition to `approved` requires GitHub review state `approved`, checks state `passing`, and policy state `ok`.

Transition to `done` requires a merged PR, a merge commit SHA, review evidence, checks evidence and no do-not-touch violation.

Override (`--override`) is limited to `sw-techlead` and `nexus` and always writes `manual_override` evidence.

## Agent Roles

| Role | Domain | Key Permissions |
|---|---|---|
| `main` | Control | Read-only across all systems |
| `nexus` | Control | Full lifecycle, scope and system management |
| `trading-strategist` | Trading | Create requests, read trading-system |
| `trading-analyst` | Trading | Evidence, market data, read trading-system |
| `trading-sentinel` | Trading | Draft requests, alerts, monitoring |
| `sw-architect` | Software | Plan work, create issues, assign |
| `sw-techlead` | Software | Full work lifecycle, override gates, capability set-status |
| `sw-builder` | Software | Build assigned work, link assigned PRs |
| `sw-reviewer` | Software | Review assigned work, submit verdicts |
| `platform-optimizer` | Control | Process optimization on agent-platform |

Builders and reviewers receive assigned-only visibility. Tech leads and Nexus can inspect broader adapter status.

## Server

```bash
nexusctl-server --host 127.0.0.1 --port 8080 --db-path .nexusctl/nexusctl.sqlite3 [--seed] \
  [--tls-cert-file PATH] [--tls-key-file PATH] [--allow-insecure-remote]
```

- `--seed` initializes agent registry, systems, goals, capabilities and runtime tools.
- `--tls-cert-file` and `--tls-key-file` enable TLS. Both must be provided together.
- `--allow-insecure-remote` permits non-loopback bind without TLS.
- `GET /healthz` returns `{"ok": true, "service": "nexusctl-server"}`.

## Documentation

See:

- `docs/API_CONTRACT.md`
- `docs/SOURCE_OF_TRUTH_V2.md`
- `docs/GITHUB_INTEGRATION.md`
- `NEXUSCTL_CLI_DESIGN.md`
