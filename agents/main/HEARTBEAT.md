# HEARTBEAT
Owner: main
Last Reviewed: 2026-04-27

## Mandatory Checks
- Check if unresolved escalations require user update.
- Check if blocked items need re-triage by nexus.
- Check whether decision deadlines are at risk or already missed.
- Check if high-risk conflicts require immediate user-facing clarification.

## Priority Order
- Critical user-risk alerts first.
- Then unresolved blockers.
- Then routine status summaries.
- Then informational updates.

## Alert Thresholds
- Immediate alert for high-risk unresolved conflict.
- Escalate if blocked > 2 hours without owner response.
- Immediate alert when mode/risk uncertainty could lead to unsafe action.
- Escalate repeated coordination loop after two consecutive cycles without net progress.

## Escalation Actions
- Cross-domain decision conflict -> escalate to user with options and recommendation.
- SLA or response miss -> escalate to `nexus` plus impacted owner with deadline reset.
- Final deadlock -> `main` issues explicit decision and records rationale.

## No-Op Rule
- If no new user-impacting event exists, post no update and leave durable state unchanged.
