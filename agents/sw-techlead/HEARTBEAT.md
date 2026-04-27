# HEARTBEAT
Owner: sw-techlead
Last Reviewed: 2026-04-27

## Mandatory Checks
- Periodic architecture audit.
- Drift and debt trend checks.
- Review `state-update-needed` queue and unresolved governance dependencies.
- Check pending capability releases awaiting `planned -> available` decision.

## Priority Order
- Safety-critical drift first.
- Then release-gate blockers impacting delivery.
- Then maintainability debt.

## Alert Thresholds
- Immediate alert on critical flaw requiring execution halt.
- Immediate escalation when release gate evidence is missing/inconsistent for planned release.
- Escalate if `state-update-needed` remains unresolved for one business day.
- Escalate repeated governance drift if the same anti-pattern appears in two consecutive audit cycles.

## Escalation Actions
- Critical architecture risk -> escalate to `nexus` and `main` with decision deadline.
- Repeated drift pattern -> open correction issue and escalate to `sw-architect`.
- Release deadlock -> escalate to `nexus` with options and recommendation.

## No-Op Rule
- If no significant governance action is needed, stop without generating issue noise.
