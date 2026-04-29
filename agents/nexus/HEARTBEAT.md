# HEARTBEAT
Owner: nexus
Last Reviewed: 2026-04-27

## Mandatory Checks
- Scan new/submitted handoffs requiring gate decision.
- Scan submitted handoffs without `issue_ref` and create linkage before downstream routing.
- Scan active handoffs for missed SLA deadlines (gate reaction and SW-triage start).
- Scan blocked handoffs with unresolved owner or missing escalation payload.
- Scan parent issues where all children are done and closure is now valid.

## Priority Order
- Risk/incident blockers first.
- Then submitted handoffs missing GitHub issue linkage.
- Then SLA-breaching handoffs.
- Then stale blocked work.
- Then throughput optimization.

## Alert Thresholds
- Use the stricter SLA when `priority` and `risk_class` differ.
- Gate reaction threshold:
- `P0|critical`: 30 minutes.
- `P1|high`: 4 hours.
- `P2|medium`: 1 business day.
- `P3|low`: 2 business days.
- SW-triage start threshold:
- `P0|critical`: 4 hours.
- `P1|high`: 1 business day.
- `P2|medium`: 2 business days.
- `P3|low`: 5 business days.
- Any missed threshold triggers immediate escalation.

## Escalation Actions
- Gate or triage SLA missed -> escalate to `nexus` and `sw-techlead`.
- Scope/ownership conflict -> coordinate `nexus + sw-architect + trading-strategist`.
- Critical blocker without resolution window -> escalate to `main` with deadline and options.

## No-Op Rule
- If no actionable lifecycle transition is available, leave state unchanged and stop cleanly.
