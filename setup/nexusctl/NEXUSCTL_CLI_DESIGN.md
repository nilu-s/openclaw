# nexusctl CLI Design

All GitHub adapter actions live under `nexusctl github`. The CLI intentionally has no legacy issue-linking or PR-linking commands outside that namespace.

## Authentication

```bash
nexusctl auth [--agent-token TOKEN] [--output table|json]
```

Without `--agent-token`, reads `NEXUS_AGENT_TOKEN` or falls back to the seed token file (`NEXUSCTL_SEED_TOKENS_FILE`). Creates a server-side session and persists it locally under `.nexusctl/sessions/`. If `NEXUS_AGENT_TOKEN` is set, every command re-authenticates automatically.

## Context

```bash
nexusctl context [--output table|json]
```

Returns the calling agent's aggregated context including systems, goals, capabilities, runtime tools, requests, work, repos, reviews and allowed actions. The shape depends on the agent's role and scope grants.

## Systems Commands

```bash
nexusctl systems list [--status all|planned|active|paused|retired] [--output table|json]
nexusctl systems show <system_id> [--output table|json]
```

## Goals Commands

```bash
nexusctl goals list [--system-id ID] [--status all|proposed|active|blocked|achieved|deprecated] [--limit N] [--output table|json]
nexusctl goals show <goal_id> [--output table|json]
nexusctl goals create --goal-id ID --title TEXT --objective TEXT --risk-class low|medium|high|critical \
  --priority P0|P1|P2|P3 [--system-id ID] [--success-metric TEXT]... [--constraint TEXT]... \
  [--owner-agent-id ID] [--status STATUS] [--parent-goal-id ID] [--output table|json]
nexusctl goals update-status <goal_id> --to proposed|active|blocked|achieved|deprecated --reason TEXT [--output table|json]
```

## Scopes Commands

```bash
nexusctl scopes list [--agent-id ID] [--output table|json]
nexusctl scopes effective [--output table|json]
```

`scopes list` returns all grants for the specified agent (or current agent). `scopes effective` returns the resolved effective scopes for the current session.

## Capabilities Commands

```bash
nexusctl capabilities list [--status all|planned|in_progress|available|blocked|deprecated] [--system-id ID] [--output table|json]
nexusctl capabilities show <capability_id> [--output table|json]
nexusctl capabilities set-status <capability_id> --to planned|available --reason TEXT [--output table|json]
```

`set-status` is restricted to `sw-techlead`. `--reason` must be between 10 and 500 characters. MVP only allows transition to `available`.

## Runtime Tools Commands

```bash
nexusctl runtime-tools list [--system-id ID] [--status all|planned|in_progress|available|blocked|deprecated] [--output table|json]
nexusctl runtime-tools show <tool_id> [--output table|json]
```

## Request Commands

```bash
nexusctl request create --objective TEXT --missing-capability TEXT --business-impact TEXT \
  --expected-behavior TEXT --acceptance-criteria TEXT... --risk-class low|medium|high|critical \
  --priority P0|P1|P2|P3 --goal-ref ID [--output table|json]
nexusctl request list [--status STATUS] [--limit N] [--output table|json]
nexusctl request show <request_id> [--output table|json]
nexusctl request transition <request_id> --to STATUS --reason TEXT [--output table|json]
```

`request create` is restricted to `trading-strategist` and `trading-sentinel`. `request transition` is restricted to `nexus` and `trading-strategist`.

Request statuses: `draft`, `submitted`, `gate-rejected`, `accepted`, `needs-planning`, `ready-to-build`, `in-build`, `in-review`, `approved`, `review-failed`, `state-update-needed`, `done`, `adoption-pending`, `closed`, `cancelled`.

## Repositories Commands

```bash
nexusctl repos list [--output table|json]
nexusctl repos assigned [--output table|json]
nexusctl repos show <repo_id> [--output table|json]
```

`repos assigned` returns only repositories assigned to the current agent.

## Work Commands

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

`--override` on `work transition` is restricted to `sw-techlead` and `nexus` and always writes `manual_override` evidence.

`--context-file` accepts a JSON file containing the full implementation context object. CLI flags override/merge with the file content.

## GitHub Commands

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

## Reviews Commands

```bash
nexusctl reviews list [--status STATUS] [--limit N] [--output table|json]
nexusctl reviews submit <request_id> --verdict approved|changes-requested|rejected --summary TEXT [--output table|json]
```

## Role Boundaries

| Role | Domain | Permissions Summary |
|---|---|---|
| `main` | Control | Read-only context across all systems |
| `nexus` | Control | Full lifecycle, scope, system and repository management; sync adapter records; override gates |
| `trading-strategist` | Trading | Create and submit requests; read trading-system context |
| `trading-analyst` | Trading | Create evidence; read market data and trading-system context |
| `trading-sentinel` | Trading | Draft requests; create alerts; monitoring reads |
| `sw-architect` | Software | Plan work, assign, set implementation context; create/sync GitHub issues |
| `sw-techlead` | Software | Full work lifecycle; capability set-status; create/sync issues and PRs; sync repos; override gates |
| `sw-builder` | Software | Build assigned work; link and sync assigned PRs; create evidence |
| `sw-reviewer` | Software | Review assigned work; submit review verdicts; sync assigned PRs |
| `platform-optimizer` | Control | Process optimization on agent-platform |

`sw-builder` can link, sync and read GitHub status only for assigned work. `sw-reviewer` can sync and read assigned review context. `sw-techlead` can create/sync issues, link/sync PRs, sync repository metadata and override policy gates. `nexus` can read broad status and sync existing GitHub adapter records.

## Request Lifecycle State Machine

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

### Lifecycle Gates

Transition to `in-review` requires approved implementation context and a linked PR.

Transition to `approved` requires GitHub review state `approved`, checks state `passing`, and policy state `ok`.

Transition to `done` requires a merged PR, a merge commit SHA, review evidence, checks evidence and no do-not-touch violation.

## Output Shape

All commands support `--output table|json`. Default is `table`.

`nexusctl work show REQ-123 --output json` includes:

```json
{
  "request_id": "REQ-123",
  "status": "in-review",
  "objective": "...",
  "missing_capability": "...",
  "acceptance_criteria": ["..."],
  "target_repo_id": "trading-engine",
  "branch": "feature/req-123",
  "assigned_agent_id": "sw-builder-01",
  "sanitized_summary": "...",
  "implementation_context_approved_by": "sw-techlead-01",
  "implementation_context_approved_at": "2026-01-01T00:00:00Z",
  "implementation_context": {
    "component": "risk",
    "entrypoints": [],
    "likely_files": ["src/risk.py"],
    "do_not_touch": ["secrets/*"],
    "interfaces": [{"name": "check_order", "signature": "check_order"}],
    "acceptance_criteria": ["..."],
    "test_commands": ["pytest tests/risk"],
    "notes": null
  },
  "github": {
    "issue": {"number": 45, "state": "open", "url": "https://github.com/org/repo/issues/45"},
    "pull_request": {"number": 78, "state": "open", "draft": false, "merged": false, "review_state": "approved", "checks_state": "passing", "policy_state": "ok", "changed_files": ["src/risk.py"]}
  }
}
```

## Error Codes

| Code | Exit Code | Meaning |
|---|---|---|
| `NX-VAL-001` | 2 | Validation error (bad input) |
| `NX-VAL-002` | 2 | Missing required credential |
| `NX-NOTFOUND-001` | 3 | Resource not found |
| `NX-PERM-001` | 4 | Permission denied |
| `NX-PRECONDITION-001` | 6 | Precondition failed (e.g. no session) |
| `NX-PRECONDITION-002` | 6 | Session expired |
| `NX-PRECONDITION-003` | 6 | State precondition failed |
| `NX-INFRA-001` | 10 | Backend not reachable |
| `NX-INFRA-002` | 10 | Unexpected infrastructure error |
