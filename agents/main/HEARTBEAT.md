# HEARTBEAT
Owner: main
Last Reviewed: 2026-04-25

## Mandatory Checks
- Check if unresolved escalations require user update.
- Check if blocked items need re-triage by nexus.

## Priority Order
- Critical user-risk alerts first.
- Then unresolved blockers.
- Then routine status summaries.

## Alert Thresholds
- Immediate alert for high-risk unresolved conflict.
- Escalate if blocked > 2 hours without owner response.

## No-Op Rule
- If no new user-impacting event exists, post no update and leave durable state unchanged.
