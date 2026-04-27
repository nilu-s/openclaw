# HEARTBEAT
Owner: sw-reviewer
Last Reviewed: 2026-04-27

## Mandatory Checks
- Find open in-review PRs.
- Check stale `review-failed` items awaiting rework.
- Check `state-update-needed` items waiting on governance updates.
- Check in-review PRs with failed required checks.

## Priority Order
- Security and correctness blockers first.
- Then merge-gate blocked PRs near SLA risk.
- Then normal review throughput.

## Alert Thresholds
- Escalate after two consecutive failed review cycles on the same PR without material improvement.
- Immediate escalation on critical flaw with operational or security impact.
- Escalate if required governance update (`state-update-needed`) is unresolved for one business day.

## Escalation Actions
- Repeated rework loop -> escalate to `nexus` and `sw-architect` with concrete blocker summary.
- Architecture-level defect -> escalate to `sw-techlead` and `sw-architect`.
- Ownership/policy deadlock -> escalate to `nexus` with options and recommendation.

## No-Op Rule
- If no in-review PR exists, stop with no label churn.
