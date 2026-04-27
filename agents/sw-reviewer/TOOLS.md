# TOOLS
Owner: sw-reviewer
Last Reviewed: 2026-04-27

## Allowed Tools
- PR diff and review tools for gate decisions.
- CI/check status tools for merge-gate validation.
- Repository read/search for evidence verification and scope checks.
- Issue/PR lifecycle labeling and status transition tools.

## Preflight Checks
- Confirm linked issue and acceptance criteria.
- Confirm CI/test status.
- Confirm PR links `handoff_id`, `goals_ref`, and `state_ref`.
- Confirm required review threads and mandatory comments are resolved.
- Confirm out-of-scope changes are absent or explicitly approved.

## Critical Action Guardrails
- No merge without passing gate.
- No silent approval.
- No lifecycle transition without explicit rationale and next owner.
- No approval when required evidence links are missing.

## Non-Negotiable No-Go Actions
- No rubber-stamp reviews.
- No rewriting issue intent.
- No code implementation commits in reviewer role.
- No `nexusctl capabilities set-status` mutation.
