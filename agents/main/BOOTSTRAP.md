# BOOTSTRAP
Owner: main
Last Reviewed: 2026-04-27

## First Run Steps
1. Read all 8 core files: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `MEMORY.md`.
2. Confirm runtime workspace path: prefer `/workspace`; otherwise use current runtime workspace and log it.
3. Load current lifecycle context and user-impact queue (escalations, approvals, blocked loops).
4. Run preflight checks for owner/status clarity, approval requirements, and risk urgency.
5. Pick exactly one highest-impact user-facing lifecycle action in scope.

## Recovery Steps
1. Re-check role boundaries and must-not rules.
2. Reconstruct state from durable sources (GitHub lifecycle + approved runtime state only).
3. Re-validate ownership, escalation status, and pending approvals before acting.
4. If ownership, policy, or risk is unclear, escalate and stop.

## Baseline Validation
- All 8 core files exist and are readable.
- Legacy files (`PROFILE.md`, `BOOT.md`, `OPERATIONS.md`, `DREAMS.md`) are absent.
- No critical contradictions with `TRADING_SYSTEM.md`, `SOFTWARE_DEVELOPMENT_SYSTEM.md`, and `HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md`.
