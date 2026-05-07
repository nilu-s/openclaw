# nexusctl

`nexusctl` is the local CLI and HTTP control plane for Nexus v2 inside the OpenClaw setup.

Nexus is the source of truth for systems, goals, requests, work, scopes, lifecycle and evidence. GitHub remains the source of truth for code, issues, pull requests, reviews and CI. The GitHub adapter is a synchronization and evidence layer, not a second work database.

## Environment

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `NEXUSCTL_API_BASE_URL` | no | `http://127.0.0.1:8080` | Nexusctl server URL |
| `NEXUS_AGENT_TOKEN` | no | — | Agent token for automatic authentication |
| `NEXUSCTL_AGENT_ID` | no | — | Agent identity override; also reads `OPENCLAW_AGENT_ID` |
| `NEXUSCTL_AGENT_DIR` | no | — | Agent-local session directory |
| `NEXUSCTL_SESSION_BASE` | no | `~/.openclaw/agents` | Base directory for sessions |
| `NEXUSCTL_SEED_TOKENS_FILE` | no | `/home/node/.openclaw/nexusctl/seed_tokens.env` | Seed token file |
| `NEXUSCTL_ALLOW_INSECURE_REMOTE` | no | false | Allows non-loopback HTTP targets only when explicitly enabled |
| `NEXUSCTL_TIMEOUT_SECONDS` | no | conservative default | CLI request timeout override |
| `NEXUSCTL_AUTH_TIMEOUT_SECONDS` | no | conservative default | Auth request timeout override |
| `NEXUS_GITHUB_TOKEN` | no | — | GitHub token read by the server-side GitHub auth provider only |
| `NEXUS_GITHUB_API_BASE` | no | `https://api.github.com` | GitHub API base URL |
| `NEXUS_GITHUB_WEBHOOK_SECRET` | no | — | HMAC secret for webhook verification |

Worker agents should talk to Nexusctl with Nexus-scoped commands. They should not receive `GH_TOKEN`, `GITHUB_TOKEN` or broad repository credentials.

## Authentication

```bash
nexusctl auth --agent-token <TOKEN>
nexusctl auth --output json
```

Authentication creates a server-side session and stores it locally for the active agent. If `NEXUS_AGENT_TOKEN` is present, commands can re-authenticate automatically.

## CLI reference

All commands support `--output table|json` unless noted. Agent-facing automation should prefer `--output json`.

### Context and maintenance

```bash
nexusctl context [--output table|json]
nexusctl rotate-token --agent-id AGENT_ID [--new-token TOKEN] [--output table|json]
nexusctl events [--target-type TYPE] [--target-id ID] [--limit N] [--output table|json]
nexusctl db backup [--path PATH] [--output table|json]
nexusctl db restore-check BACKUP_PATH [--output table|json]
```

### Systems, goals, capabilities and runtime tools

```bash
nexusctl systems list [--status all|planned|active|paused|retired] [--output table|json]
nexusctl systems show SYSTEM_ID [--output table|json]

nexusctl goals list [--system-id ID] [--status all|proposed|active|blocked|achieved|deprecated] [--limit N] [--output table|json]
nexusctl goals show GOAL_ID [--output table|json]
nexusctl goals create --goal-id ID --title TEXT --objective TEXT --risk-class low|medium|high|critical --priority P0|P1|P2|P3 \
  [--system-id ID] [--success-metric TEXT]... [--constraint TEXT]... [--owner-agent-id ID] [--status STATUS] [--parent-goal-id ID] [--output table|json]
nexusctl goals update-status GOAL_ID --to proposed|active|blocked|achieved|deprecated --reason TEXT [--output table|json]

nexusctl capabilities list [--status all|planned|in_progress|available|blocked|deprecated] [--system-id ID] [--output table|json]
nexusctl capabilities show CAPABILITY_ID [--output table|json]
nexusctl capabilities set-status CAPABILITY_ID --to planned|available --reason TEXT [--output table|json]

nexusctl runtime-tools list [--system-id ID] [--status all|planned|in_progress|available|blocked|deprecated] [--output table|json]
nexusctl runtime-tools show TOOL_ID [--output table|json]
nexusctl runtime-tools check TOOL_ID [--request-id REQ_ID] [--side-effect-level LEVEL] [--human-approved] [--output table|json]
```

`capabilities set-status` is intentionally narrow; the MVP path promotes or reverts availability under lifecycle control.

### Scopes

```bash
nexusctl scopes list [--agent-id AGENT_ID] [--output table|json]
nexusctl scopes effective [--output table|json]
nexusctl scopes lease --agent-id AGENT_ID --scope SCOPE [--system-id ID|*] [--resource PATTERN] [--request-id REQ_ID] --reason TEXT [--ttl-minutes N] [--approved-by AGENT_ID] [--output table|json]
nexusctl scopes leases [--agent-id AGENT_ID] [--all] [--output table|json]
nexusctl scopes revoke-lease LEASE_ID --reason TEXT [--output table|json]
```

Leases are temporary scope extensions. Use them instead of widening permanent agent permissions.

### Requests

```bash
nexusctl request create --objective TEXT --missing-capability TEXT --business-impact TEXT \
  --expected-behavior TEXT --acceptance-criteria TEXT... --risk-class low|medium|high|critical \
  --priority P0|P1|P2|P3 --goal-ref ID [--output table|json]

nexusctl request list [--status STATUS] [--limit N] [--output table|json]
nexusctl request show REQUEST_ID [--output table|json]
nexusctl request transition REQUEST_ID --to STATUS_OR_ALIAS --reason TEXT [--output table|json]
```

The deterministic dedupe key for new requests is `objective + missing_capability + goal_ref`. `goal_ref` must resolve through a Nexus goal alias such as `TG-003` or `trading-goal://risk/limit-hard-stop`.

Direct request transitions cannot move software work through work-managed statuses; use `nexusctl work transition` for implementation lifecycle.

### Repositories and work

```bash
nexusctl repos list [--output table|json]
nexusctl repos assigned [--output table|json]
nexusctl repos show REPO_ID [--output table|json]

nexusctl work list [--status STATUS] [--limit N] [--output table|json]
nexusctl work show REQUEST_ID [--output table|json]
nexusctl work plan REQUEST_ID --repo REPO_ID [--branch NAME] [--assign BUILDER_AGENT_ID] [--reviewer REVIEWER_AGENT_ID] [--sanitized-summary TEXT] [--output table|json]
nexusctl work set-implementation-context REQUEST_ID [--context-file PATH] [--component NAME] \
  [--entrypoint PATH]... [--likely-file PATH]... [--do-not-touch PATTERN]... [--interface NAME]... \
  [--acceptance-criteria TEXT]... [--test-command CMD]... [--notes TEXT] [--output table|json]
nexusctl work approve-plan REQUEST_ID [--output table|json]
nexusctl work assign REQUEST_ID --agent AGENT_ID [--output table|json]
nexusctl work transition REQUEST_ID --to STATUS_OR_ALIAS --reason TEXT [--override --approved-by AGENT_ID] [--output table|json]
nexusctl work submit-evidence REQUEST_ID --kind KIND --summary TEXT [--ref REF] [--output table|json]
```

Builder and reviewer ownership are separate fields. `--assign` sets the builder (`assigned_agent_id`); `--reviewer` sets the reviewer (`reviewer_agent_id`).

Manual override is restricted to `sw-techlead` and `nexus`, cannot skip lifecycle gates, requires a durable reason and a second approver via `--approved-by`, and records `manual_override` evidence.

### GitHub adapter

```bash
nexusctl github issue create REQUEST_ID [--dry-run] [--title TEXT] [--label LABEL]... [--assignee USER]... [--output table|json]
nexusctl github issue sync REQUEST_ID [--output table|json]

nexusctl github pr link REQUEST_ID --url URL [--output table|json]
nexusctl github pr sync REQUEST_ID [--output table|json]

nexusctl github status REQUEST_ID [--output table|json]
nexusctl github sync REQUEST_ID [--output table|json]
nexusctl github alerts [--all] [--limit N] [--output table|json]

nexusctl github repos list [--output table|json]
nexusctl github repos sync [--output table|json]
```

`github repos list` and `github repos sync` are restricted to `sw-techlead` and `nexus`. Builders and reviewers only see/sync GitHub state for assigned work.

### Reviews

```bash
nexusctl reviews list [--status STATUS] [--limit N] [--output table|json]
nexusctl reviews submit REQUEST_ID --verdict approved|changes-requested|rejected --summary TEXT [--output table|json]
```

## Lifecycle model

Canonical statuses:

```text
draft -> submitted -> accepted -> needs-planning -> ready-to-build -> in-build -> in-review -> approved -> done -> adoption-pending -> closed
            |              |                     |             |             |            |
            v              v                     v             v             v            v
       gate-rejected    cancelled             cancelled     cancelled  review-failed  state-update-needed
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

Aliases accepted by transition commands:

| Alias | Status |
|---|---|
| `intake` | `submitted` |
| `planned` | `needs-planning` |
| `build-ready` | `ready-to-build` |
| `building` | `in-build` |
| `review` | `in-review` |
| `approve` | `approved` |
| `complete` | `done` |
| `close` | `closed` |

Lifecycle gates:

- `in-review` requires approved implementation context and a linked PR.
- `approved` requires fresh PR sync, review state `approved`, checks state `passing`, and policy state `ok`.
- `done` requires a merged PR, merge commit SHA, fresh review/check evidence and no do-not-touch policy violation.
- Manual override can resolve exceptional cases but still must satisfy lifecycle gates.

## GitHub integration

The adapter creates sanitized issues, links PRs, syncs issue/PR/review/check/file state, records evidence and accepts webhook delivery events.

### Storage boundaries

GitHub metadata is stored in dedicated tables:

- `github_issues`
- `github_pull_requests`
- `github_events`

Requests remain Nexus work-routing records: source/target systems, `goal_ref`, objective, status, priority, risk, target repo, branch, builder/reviewer assignment and implementation context.

### Auth and transport

The server-side GitHub client sends the configured token with GitHub API headers and a `nexusctl` user agent. Worker agents do not call GitHub directly and do not receive the GitHub token.

### Repository registry

Nexus repositories map `repo_id` to GitHub owner/repo metadata. PR URLs must match the `target_repo_id` repository before linking.

### Issue creation

`github issue create` renders a sanitized issue body from Nexus request and implementation context. `--dry-run` returns the rendered body and writes nothing to GitHub or adapter tables.

### PR sync

`github pr sync` reads paginated PR files, reviews, commits and check-runs. Latest review per reviewer determines review state; failing checks dominate pending/passing aggregation. Stale approvals older than the latest commit are rejected for lifecycle gates.

### Policy checks

The do-not-touch policy evaluates changed files and renamed files via `previous_filename`. Default sensitive patterns block common secret, key and env-file paths even if a work item forgot to list them explicitly.

### Evidence kinds

GitHub synchronization emits work evidence such as:

- `github_issue`
- `github_issue_sync`
- `github_pr_linked`
- `github_pr_sync`
- `github_reviews`
- `github_checks`
- `github_policy_violation`
- `github_sync`
- `github_webhook`
- `manual_override`

### Webhooks

`POST /v1/github/webhooks` verifies `X-Hub-Signature-256` against the raw request body, stores idempotent delivery events and returns `202 Accepted`. Processing is explicit through the authenticated worker endpoint. Failed processing is persisted as `dead_letter` so `nexusctl github alerts` can surface it.

### What the adapter does not do

It does not clone, edit, commit, push, merge, resolve conflicts, crawl arbitrary repositories or give worker agents global GitHub rights.

### Failure modes

GitHub and adapter failures map to stable errors such as `NX-GH-AUTH`, `NX-GH-NOT-FOUND`, `NX-GH-DISABLED`, `NX-GH-VALIDATION`, `NX-GH-RATE-LIMIT` and `NX-GH-UPSTREAM`. Raw GitHub tracebacks are not exposed to agents.

## HTTP API

The CLI is the default interface. These HTTP routes back it:

```http
POST /v1/nexus/auth
GET  /v1/nexus/context
GET  /v1/nexus/systems
GET  /v1/nexus/systems/{system_id}
GET  /v1/nexus/goals
POST /v1/nexus/goals
GET  /v1/nexus/goals/{goal_id}
POST /v1/nexus/goals/{goal_id}/status
GET  /v1/nexus/scopes
GET  /v1/nexus/scopes/effective
GET  /v1/nexus/scopes/leases
POST /v1/nexus/scopes/leases
POST /v1/nexus/scopes/leases/{lease_id}/revoke
GET  /v1/nexus/events
POST /v1/nexus/db/backup
POST /v1/nexus/db/restore-check
GET  /v1/nexus/runtime-tools
GET  /v1/nexus/runtime-tools/{tool_id}
POST /v1/nexus/runtime-tools/{tool_id}/guardrail
GET  /v1/nexus/capabilities
GET  /v1/nexus/capabilities/{capability_id}
POST /v1/nexus/capabilities/{capability_id}/status
GET  /v1/nexus/requests
POST /v1/nexus/requests
GET  /v1/nexus/requests/{request_id}
POST /v1/nexus/requests/{request_id}/transition
GET  /v1/nexus/repos
GET  /v1/nexus/repos/{repo_id}
GET  /v1/nexus/work
GET  /v1/nexus/work/{request_id}
POST /v1/nexus/work/{request_id}/plan
POST /v1/nexus/work/{request_id}/implementation-context
POST /v1/nexus/work/{request_id}/approve-plan
POST /v1/nexus/work/{request_id}/assign
POST /v1/nexus/work/{request_id}/transition
POST /v1/nexus/work/{request_id}/evidence
GET  /v1/nexus/reviews
POST /v1/nexus/reviews/{request_id}
POST /v1/nexus/github/issues/{request_id}
POST /v1/nexus/github/issues/{request_id}/sync
POST /v1/nexus/github/pull-requests/{request_id}/link
POST /v1/nexus/github/pull-requests/{request_id}/sync
GET  /v1/nexus/github/status/{request_id}
POST /v1/nexus/github/sync/{request_id}
GET  /v1/nexus/github/alerts
GET  /v1/nexus/github/repositories
POST /v1/nexus/github/repositories/sync
POST /v1/nexus/github/webhooks/process
POST /v1/github/webhooks
```

`GET /healthz` returns a simple health payload. The server should bind to `127.0.0.1` unless TLS and explicit remote exposure are configured.

## Output and errors

Table output is for humans; JSON output is stable for agents and wrappers. Common error classes:

| Code | Exit Code | Meaning |
|---|---:|---|
| `NX-VAL-001` | 2 | Validation error |
| `NX-VAL-002` | 2 | Missing required credential |
| `NX-NOTFOUND-001` | 3 | Resource not found |
| `NX-PERM-001` | 4 | Permission denied |
| `NX-PRECONDITION-001` | 6 | Missing precondition or session |
| `NX-PRECONDITION-002` | 6 | Session expired |
| `NX-PRECONDITION-003` | 6 | State precondition failed |
| `NX-INFRA-001` | 10 | Backend not reachable |
| `NX-INFRA-002` | 10 | Unexpected infrastructure error |

## Testing

The suite uses markers so fast logic tests do not need embedded HTTP servers:

- `unit` — fast tests without an embedded HTTP server.
- `integration` — tests that start `nexusctl-server` through `ThreadingHTTPServer`.
- `networkish` — tests around unreachable-network behavior; timeouts should be explicit and short.
- `slow` — slower tests on constrained machines.

Recommended commands:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -ra
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -m unit -q -ra
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -m integration -q -ra
./scripts/run_tests.sh
```

`./scripts/run_tests.sh` disables ambient pytest plugin autoloading and wraps the suite in a process-level timeout.

## Packaging hygiene

Do not package generated caches, runtime DBs, `.env`, `.coverage`, `*.pyc`, `.pytest_cache`, `__pycache__` or local logs. The root validator checks this before deployment.
