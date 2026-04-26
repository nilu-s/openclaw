# TOOLS
Owner: trading-sentinel
Last Reviewed: 2026-04-25

## Allowed Tools
- Monitoring and risk tools
- Exchange health checks
- Alerting channels and GitHub state updates

## Preflight Checks
- Load TRADING_STATE and current limits.
- Confirm operational mode (paper/live).

## Critical Action Guardrails
- In paper mode, no real order execution under any circumstance.
- Keep run lightweight and deterministic.

## Non-Negotiable No-Go Actions
- No autonomous strategy changes.
- No hidden fallback behavior.
