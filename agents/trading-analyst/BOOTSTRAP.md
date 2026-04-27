# BOOTSTRAP
Owner: trading-analyst
Last Reviewed: 2026-04-27

## First Run Steps
1. Read all 8 core files: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `MEMORY.md`.
2. Confirm runtime workspace path: prefer `/workspace/software/repos/trading-system`; otherwise use current runtime workspace and log it.
3. Load current lifecycle context and analyst queue (research requests, evidence refreshes, handoff draft support).
4. Run preflight checks for mode/limits, data integrity, capability truth, and objective clarity.
5. Pick exactly one highest-impact research lifecycle action in scope.

## Recovery Steps
1. Re-check role boundaries and must-not rules.
2. Reconstruct state from durable sources (GitHub lifecycle + approved runtime state only).
3. Re-validate role authority and evidence assumptions before acting.
4. If ownership, policy, or risk is unclear, escalate and stop.

## Baseline Validation
- All 8 core files exist and are readable.
- Legacy files (`PROFILE.md`, `BOOT.md`, `OPERATIONS.md`, `DREAMS.md`) are absent.
- No critical contradictions with `TRADING_SYSTEM.md`, `HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md`, and `NEXUSCTL_FUNCTIONS.md`.
