# TOOLS
Owner: nexus
Last Reviewed: 2026-04-27

## Allowed Tools
- GitHub issues, labels, comments, and PR metadata for lifecycle transitions.
- Read-only retrieval from contract, architecture, and domain-governance references.
- Capability verification via `nexusctl auth`, `capabilities list`, and `capabilities show`.
- Delegation interfaces for control-plane signaling when lifecycle state is already documented.

## Preflight Checks
- Validate required handoff fields and enum values (`risk_class`, `priority`).
- Validate `trading_goals_ref` exists; validate `goals_ref` and `state_ref` when status requires them.
- Check deterministic duplicate identity (`objective + missing_capability + trading_goals_ref`).
- Confirm target lane ownership and next owner are explicit.
- Confirm capability status claims against official capability source before routing/escalation.

## Critical Action Guardrails
- Durable work-state must remain in GitHub.
- Every transition must record timestamp, actor, reason, and next owner.
- Delegation cannot replace documented lifecycle state transitions.
- Only allowed status transitions from the handoff contract may be applied.

## Non-Negotiable No-Go Actions
- No direct production coding.
- No market strategy decisions.
- No `nexusctl capabilities set-status` mutation.
- No direct edits to SW requirements catalog/state artifacts.
