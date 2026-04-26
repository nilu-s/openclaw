# HEARTBEAT
Owner: sw-reviewer
Last Reviewed: 2026-04-25

## Mandatory Checks
- Find open in-review PRs.
- Check stale review-failed items.

## Priority Order
- Security/correctness blockers
- Then throughput

## Alert Thresholds
- Escalate to nexus after repeated failed review cycles.

## No-Op Rule
- If no in-review PR exists, stop with no label churn.
