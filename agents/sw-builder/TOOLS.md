# TOOLS
Owner: sw-builder
Last Reviewed: 2026-04-27

## Allowed Tools
- Git/GitHub operations for branch/PR lifecycle in implementation scope.
- Build and test tooling required by the target repository.
- Repository search/read for implementation and debugging context.
- Capability verification via `nexusctl auth`, `capabilities list`, and `capabilities show`.

## Preflight Checks
- Confirm issue label is `ready-to-build` or `review-failed`.
- Confirm branch name, base branch, and issue/handoff linkage are correct.
- Confirm `goals_ref` and `state_ref` are present and resolvable before coding.
- Confirm no existing active PR already owns the same issue scope.
- Confirm required checks/tests for merge gate are known.

## Critical Action Guardrails
- No direct main branch commits.
- No skipping tests without explicit rationale.
- No undocumented lifecycle transition; persist state updates in GitHub.
- Keep changes scoped to issue intent and referenced modules.
- Do not introduce unrelated refactors during fix/build runs.

## Non-Negotiable No-Go Actions
- No unrelated refactors.
- No policy-breaking shortcuts.
- No `nexusctl capabilities set-status` mutation.
- No bypass of required review/CI gate semantics.
