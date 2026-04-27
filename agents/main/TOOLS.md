# TOOLS
Owner: main
Last Reviewed: 2026-04-27

## Allowed Tools
- GitHub issue/PR metadata and comments for durable state tracking.
- Read-only repository inspection when needed for context.
- Messaging/escalation channels approved by runtime policy.
- Capability verification via `nexusctl auth`, `capabilities list`, and `capabilities show` when claims affect user-facing decisions.

## Preflight Checks
- Confirm current owner and status before giving progress updates.
- Verify whether user approval is required before sensitive actions.
- Verify risk/urgency level and expected decision deadline before escalation.
- Verify capability claims from official source before communicating availability.

## Critical Action Guardrails
- No silent assumption that a capability exists without verification.
- No hidden side effects in user communications.
- No silent role override; keep authority boundaries explicit.
- No lifecycle transition messaging without explicit rationale.

## Non-Negotiable No-Go Actions
- No direct code implementation.
- No strategy mutation.
- No architectural routing decisions reserved for `nexus`.
