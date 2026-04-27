# BOOTSTRAP
Owner: sw-architect
Last Reviewed: 2026-04-27

## First Run Steps
1. Read all 8 core files: `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `MEMORY.md`.
2. Confirm runtime workspace path: prefer `/workspace/software/repos`; otherwise use current runtime workspace and log it.
3. Load current GitHub lifecycle context and planning queue (`accepted`, `needs-planning`).
4. Run preflight checks for schema completeness, reference resolvability, capability truth, and ownership clarity.
5. Pick exactly one highest-impact planning lifecycle action in scope.

## Recovery Steps
1. Re-check role boundaries and must-not rules.
2. Reconstruct state from durable sources (GitHub lifecycle + approved runtime state only).
3. Re-validate current status against allowed contract transitions before acting.
4. If ownership, policy, or risk is unclear, escalate and stop.

## Baseline Validation
- All 8 core files exist and are readable.
- Legacy files (`PROFILE.md`, `BOOT.md`, `OPERATIONS.md`, `DREAMS.md`) are absent.
- No critical contradictions with `HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md`, `SOFTWARE_DEVELOPMENT_SYSTEM.md`, and `TRADING_SYSTEM.md`.
