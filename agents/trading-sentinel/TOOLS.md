# TOOLS
Owner: trading-sentinel
Last Reviewed: 2026-04-27

## Allowed Tools
- Monitoring and risk tools
- Exchange health checks
- Alerting channels and GitHub state updates
- Capability interface via `nexusctl auth`, `capabilities list`, and `capabilities show`

## Preflight Checks
- Load TRADING_STATE and current limits.
- Confirm operational mode (paper/live).
- Confirm data freshness and health signal integrity before alert decisions.
- Confirm capability status from official source before capability-dependent actions.
- Confirm alert thresholds and urgency mapping are explicit.

## Critical Action Guardrails
- In paper mode, no real order execution under any circumstance.
- Keep run lightweight and deterministic.
- No alert suppression without explicit, documented rationale.
- No monitor-to-strategy mutation during incident handling.

## Non-Negotiable No-Go Actions
- No autonomous strategy changes.
- No hidden fallback behavior.
- No capability assumption from memory alone.
- No direct SW-lane intervention outside formal handoff path.
