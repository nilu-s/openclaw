# OpenClaw Autonomy Stabilization Verification

Date: 2026-04-29
Target Host: `root@100.102.209.68`
Scope: Task 6 verification gate from `docs/superpowers/plans/2026-04-29-openclaw-autonomy-stabilization.md`

## KPI Snapshot

- Active jobs: **7**
- Jobs with `lastRunStatus=error`: **7**
- Jobs with `lastErrorReason=auth`: **7**
- Jobs with `consecutiveErrors>0`: **7**
- `openclaw-gateway` health: **healthy**
- `nexusctl-server` health: **healthy**

## Cron Session Ownership Evidence

Session files currently show runtime ownership concentrated under `main`:

- `/opt/openclaw/state/agents/main/sessions/sessions.json` -> **8** entries
- `/opt/openclaw/state/agents/nexus/sessions/sessions.json` -> **0**
- `/opt/openclaw/state/agents/sw-architect/sessions/sessions.json` -> **0**
- `/opt/openclaw/state/agents/sw-builder/sessions/sessions.json` -> **0**
- `/opt/openclaw/state/agents/sw-reviewer/sessions/sessions.json` -> **0**
- `/opt/openclaw/state/agents/sw-techlead/sessions/sessions.json` -> **0**
- `/opt/openclaw/state/agents/trading-sentinel/sessions/sessions.json` -> **0**
- `/opt/openclaw/state/agents/trading-strategist/sessions/sessions.json` -> **0**

Conclusion: Role-aligned session ownership is **not** achieved yet.

## `nexusctl` Contract Validation (Explicit Scope)

All checks executed with explicit scope (`NEXUSCTL_AGENT_DIR=/opt/openclaw/state/agents/nexus/agent`).

Allow path:

- Command: `nexusctl request list --status all --limit 5 --output json`
- Result: success; returned handoff list including `HC-2026-10b095963d1a538b` and `HC-2026-d9a832ce7675b956`

Deny/precondition path:

- Command: `nexusctl request set-issue HC-2026-10b095963d1a538b --issue-ref issue://github/example/repo#999 --issue-number 999 --issue-url https://github.com/example/repo/issues/999 --output json`
- Result: blocked with `NX-PRECONDITION-003: issue linkage is only allowed in accepted status`

Conclusion: Contract checks behave correctly when scope is explicit.

## What Is Fixed

- Service health is stable (`openclaw-gateway`, `nexusctl-server` both healthy).
- Lifecycle guardrail remains enforceable (`NX-PRECONDITION-003` reproduced on invalid mutation).
- Explicit scope operation for `nexusctl` is working for valid read paths.

## What Remains Blocked

- Autonomy loop remains failed at runtime: all active cron jobs are in error with `lastErrorReason=auth`.
- Cron session ownership still collapses to `main` rather than role-specific agent session files.

## Concrete Blocker Cause

Current unattended cron executions still resolve model/auth context through `main` session/auth state, and provider auth for requested fallback model (`openai/gpt-5.5`) is not available in that runtime path. This keeps all jobs in persistent auth failure and prevents role-isolated autonomous execution.

## Exact Manual Next Step Required From Operator

Run an interactive auth bootstrap inside the gateway container for the runtime path used by cron:

```bash
ssh -t root@100.102.209.68 "docker exec -it openclaw-gateway openclaw models auth --agent main add"
```

After completing the interactive auth flow, wait one cron cycle and re-check:

- `/opt/openclaw/state/cron/jobs-state.json` for reduction of `lastErrorReason=auth`
- `/opt/openclaw/state/agents/*/sessions/sessions.json` for movement away from `main`-only ownership

## Verdict

**Partially stabilized**: control-plane and contract behavior are healthy, but end-to-end autonomous execution is not stabilized due to unresolved runtime auth/session routing.
