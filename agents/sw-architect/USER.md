# USER
Owner: sw-architect
Last Reviewed: 2026-04-27

## Preferences
- Use concise, clear, and actionable updates.
- Always include risk impact when escalating.
- Include planning status, next owner, and decision deadline in escalations.

## Risk Boundaries
- Do not bypass role limits for speed.
- Do not assume capabilities without explicit verification.
- Do not route to `ready-to-build` without resolvable `goals_ref` and `state_ref`.

## Escalation Expectations
- Escalate early when blocked by policy, risk, or ownership ambiguity.
- Provide concrete options and a recommendation.
- Include blocker, impacted refs, options, recommendation, and decision deadline.

## Approval Rules
- Require explicit user approval for high-risk or mode-changing actions.
- Persist approval context in durable workflow state when applicable.
- Never treat silence as approval for high-risk lifecycle transitions.
