# HEARTBEAT
Owner: sw-architect
Last Reviewed: 2026-04-27

## Mandatory Checks
- Find `accepted` and `needs-planning` items requiring decomposition.
- Find planning items missing `goals_ref` or `state_ref`.
- Find stale planning blockers (missing intent, unresolved architecture, ownership ambiguity).
- Find items at risk of missing SW-triage start SLA.

## Priority Order
- Critical blockers.
- SLA-breaching or SLA-at-risk planning items.
- High-impact planning.
- Routine backlog.

## Alert Thresholds
- Use the stricter SLA when `priority` and `risk_class` differ.
- SW-triage start threshold:
- `P0|critical`: 4 hours.
- `P1|high`: 1 business day.
- `P2|medium`: 2 business days.
- `P3|low`: 5 business days.
- Missing/non-resolvable `goals_ref` or `state_ref` triggers immediate escalation.

## Escalation Actions
- Missing business intent or invalid planning input -> escalate to `nexus` with canonical reason.
- Architecture ambiguity with material risk -> escalate to `nexus` and `sw-techlead`.
- Missed SW-triage start SLA -> escalate to `nexus` and `sw-techlead` with deadline/options.

## No-Op Rule
- If no plannable issue exists, stop with no state mutation.
