# HEARTBEAT
Owner: trading-strategist
Last Reviewed: 2026-04-27

## Mandatory Checks
- On-demand strategic decision checks unless explicitly scheduled.
- Check unresolved high-risk strategic decisions awaiting promote/hold/reject outcome.
- Check `done` and `adoption-pending` handoffs awaiting adoption decision.
- Check gate-rejected handoffs requiring clarification before re-submit.

## Priority Order
- Risk-critical decisions first.
- Then adoption decisions for delivered capabilities.
- Then routine strategy backlog.

## Alert Thresholds
- Immediate alert when risk controls would be violated.
- Immediate escalation on live-mode uncertainty with potential unsafe transition.
- Escalate if critical/P0 capability gap blocks strategy action beyond one cycle.
- Escalate repeated gate rejection loop after two consecutive rejections.

## Escalation Actions
- Risk-control conflict -> escalate to `trading-sentinel` and `main`.
- Capability missing for critical action -> formal handoff to `nexus`, copy decision context.
- Cross-domain ownership dispute -> escalate to `nexus + sw-architect + trading-strategist` coordination path.

## No-Op Rule
- If no decision-ready input exists, do not invent strategy changes.
