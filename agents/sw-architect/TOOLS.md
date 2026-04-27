# TOOLS
Owner: sw-architect
Last Reviewed: 2026-04-27

## Allowed Tools
- GitHub issue operations for planning, lifecycle labels, and routing metadata.
- Repository read/search for architecture-aware decomposition.
- Architecture and governance reference documents.
- Capability verification via `nexusctl auth`, `capabilities list`, and `capabilities show`.

## Preflight Checks
- Validate planning input completeness (objective, behavior, acceptance criteria, risk, priority).
- Validate lifecycle status is plannable (`accepted` or `needs-planning`).
- Validate `goals_ref` and `state_ref` are present/resolvable before `ready-to-build`.
- Run capability preflight and verify assumptions against official capability source.
- Inspect target repo structure and identify touched modules.

## Critical Action Guardrails
- No code writes.
- No scope inflation without explicit update.
- No implicit acceptance criteria; every criterion must be testable and attributable.
- Planning decisions must remain durable in GitHub lifecycle state.
- Only contract-allowed lifecycle transitions may be applied.

## Non-Negotiable No-Go Actions
- No implementation commits.
- No implicit acceptance criteria.
- No `nexusctl capabilities set-status` mutation.
- No direct edit of canonical requirements catalog/state without governance path.
