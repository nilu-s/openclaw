# TOOLS
Owner: trading-strategist
Last Reviewed: 2026-04-25

## Allowed Tools
- Trading research outputs
- Capability interface
- GitHub requirement handoff

## Preflight Checks
- Check TRADING_STATE mode and limits.
- Check capability status (`available` required).

## Critical Action Guardrails
- Paper mode is default and strict.
- No real order behavior in paper mode.

## Non-Negotiable No-Go Actions
- No direct code changes.
- No capability assumption from memory alone.
