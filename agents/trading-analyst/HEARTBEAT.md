# HEARTBEAT
Owner: trading-analyst
Last Reviewed: 2026-04-27

## Mandatory Checks
- On-demand by strategist/user unless explicit schedule is configured.
- Check critical requested research items blocked by data/capability issues.
- Check stale analyst outputs awaiting strategist consumption.
- Check open handoff drafts requiring clarification before submission.

## Priority Order
- Critical requested research first.
- Then decision-blocking evidence refresh.
- Then routine research backlog.

## Alert Thresholds
- Escalate when evidence quality cannot support a decision.
- Immediate escalation when risk controls would be violated by a proposed action.
- Escalate if required data integrity issues persist for two consecutive cycles.
- Escalate if a capability gap blocks critical research for one full cycle.

## Escalation Actions
- Data quality blocker -> escalate to `trading-strategist` and `trading-sentinel` with mitigation options.
- Capability gap blocker -> provide handoff draft context to `trading-strategist` for formal submission.
- Cross-domain ambiguity -> escalate through `nexus` orchestration path.

## No-Op Rule
- If no research task exists, do not generate synthetic reports.
