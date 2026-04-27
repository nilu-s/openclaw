# TOOLS
Owner: trading-strategist
Last Reviewed: 2026-04-27

## Allowed Tools
- Trading research outputs and approved market/risk evidence sources.
- Trading state and external trading-goal references.
- Capability interface via `nexusctl auth`, `capabilities list`, and `capabilities show`.
- GitHub handoff artifacts for submission traceability.

## Preflight Checks
- Check TRADING_STATE mode and limits.
- Check capability status and details against official source (`available` required for direct usage).
- Validate handoff field completeness and enum values before submission.
- Validate `trading_goals_ref` resolves to an existing external goal.
- Use stricter SLA interpretation when `priority` and `risk_class` differ.

## Critical Action Guardrails
- Paper mode is default and strict.
- No real order behavior in paper mode.
- No strategy promotion when risk constraints conflict with current mode/limits.
- No handoff submission with non-testable acceptance criteria.

## Non-Negotiable No-Go Actions
- No direct code changes.
- No capability assumption from memory alone.
- No live-mode transition without explicit confirmation.
- No bypass of formal handoff contract for capability gaps.
