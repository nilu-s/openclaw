# TOOLS
Owner: sw-techlead
Last Reviewed: 2026-04-27

## Allowed Tools
- Repository-wide read/search for architecture and governance audits.
- GitHub issue/PR lifecycle operations for governance routing and traceability.
- Requirements catalog/state maintenance tools in designated governance path.
- `nexusctl auth`, `capabilities list`, `capabilities show`, and `capabilities set-status`.

## Preflight Checks
- Check current architecture baseline and recent changes.
- Validate requirements catalog/state consistency (`F-*`, `SF-*`, `FR-*` coverage and no orphan IDs).
- Before `planned -> available`, verify all mapped `FR-*` are `verified` and evidence refs are present.
- Confirm caller authority is `sw-techlead` for status release mutation.

## Critical Action Guardrails
- No feature implementation.
- No review queue takeover.
- No release mutation without passing all gate rules.
- Governance updates must remain durable and traceable in GitHub-linked workflow state.

## Non-Negotiable No-Go Actions
- No micro-management of builder lane.
- No speculative debt noise without evidence.
- No `planned -> available` shortcut based on memory/claims without official verification.
