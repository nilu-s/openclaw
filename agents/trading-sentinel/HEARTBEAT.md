# HEARTBEAT
Owner: trading-sentinel
Last Reviewed: 2026-04-27

## Mandatory Checks
- Positions and limit utilization.
- Exchange/system health and anomaly signals.
- Capability blockers affecting monitoring controls.
- Mode safety checks before potentially unsafe actions.

## Priority Order
- Risk breach first.
- Mode safety second.
- Exchange anomaly third.
- Routine status last.

## Alert Thresholds
- Immediate alert on limit breach or severe exchange anomaly.
- Immediate escalation on unclear mode state with unsafe-action potential.
- Escalate near-breach conditions when projected breach risk is material.
- Escalate recurring capability blocker after two consecutive cycles.

## Escalation Actions
- Limit breach/near-breach -> escalate to `trading-strategist` and `main` with urgency.
- Mode uncertainty -> escalate to `main` and `trading-strategist` for explicit decision.
- Capability blocker -> provide formal handoff draft context for strategist submission via `nexus`.

## No-Op Rule
- If all checks are healthy, log concise status and stop.
