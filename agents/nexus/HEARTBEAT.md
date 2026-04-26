# HEARTBEAT
Owner: nexus
Last Reviewed: 2026-04-25

## Mandatory Checks
- Scan for unlabeled/new issues requiring triage.
- Scan blocked issues older than threshold.
- Scan parent issues where all children are done.

## Priority Order
- Risk/incident blockers first.
- Then stale blocked work.
- Then throughput optimization.

## Alert Thresholds
- Immediate escalation on unresolved high-risk blocker.
- Escalate stale blocked issue older than policy threshold.

## No-Op Rule
- If no actionable lifecycle transition is available, leave state unchanged and stop cleanly.
