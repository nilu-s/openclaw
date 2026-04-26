# HEARTBEAT
Owner: sw-builder
Last Reviewed: 2026-04-25

## Mandatory Checks
- Find highest-priority build issue.
- Check assigned review-failed rework.

## Priority Order
- Fix failing review first
- Then new ready-to-build work

## Alert Thresholds
- Escalate if issue remains blocked for multiple cycles due to external dependencies.

## No-Op Rule
- If no eligible issue exists, do not open speculative PRs.
