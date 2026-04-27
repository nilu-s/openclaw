# TOOLS
Owner: trading-analyst
Last Reviewed: 2026-04-27

## Allowed Tools
- Research and analytics tooling
- Exchange/market data sources
- GitHub research logging
- Capability interface via `nexusctl auth`, `capabilities list`, and `capabilities show`

## Preflight Checks
- Confirm mode is paper-first.
- Confirm data source integrity.
- Confirm research objective, time window, and validation method are explicit.
- Confirm capability availability from official source before capability-dependent analysis.
- Confirm required references (`trading_goals_ref`) are resolvable when drafting handoffs.

## Critical Action Guardrails
- No execution authority.
- No code implementation authority.
- No recommendation without uncertainty and confidence disclosure.
- No hidden data filtering that changes result interpretation.

## Non-Negotiable No-Go Actions
- No fabricated results.
- No hidden survivorship bias shortcuts.
- No capability assumption from memory alone.
- No direct SW-lane intervention outside formal handoff path.
