# HEARTBEAT
Owner: sw-builder
Last Reviewed: 2026-04-27

## Mandatory Checks
- Check assigned `review-failed` rework first.
- Find highest-priority `ready-to-build` issue if no rework is pending.
- Check active `in-build` items for blockers and stale progress.
- Check whether PR state is consistent with issue lifecycle labels.

## Priority Order
- Fix `review-failed` items first.
- Then critical/high-risk new `ready-to-build` work.
- Then routine `ready-to-build` backlog.

## Alert Thresholds
- Immediate escalation if acceptance criteria or references are non-resolvable.
- Escalate if the same external blocker persists for two consecutive cycles.
- Escalate if CI/test failures repeat three consecutive runs without a clear fix path.

## Escalation Actions
- Requirement ambiguity -> escalate to `sw-architect` and `nexus` with concrete clarification request.
- Architecture-level blocker -> escalate to `sw-architect` and `sw-techlead`.
- Persistent external dependency blocker -> escalate to `nexus` with options and recommended path.

## No-Op Rule
- If no eligible issue exists, do not open speculative PRs.
