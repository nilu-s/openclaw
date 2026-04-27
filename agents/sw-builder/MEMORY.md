# MEMORY
Owner: sw-builder
Last Reviewed: 2026-04-27

## Durable Decisions
- Record only durable role-relevant decisions with date and rationale.
- For each entry, include `handoff_id`, issue/PR refs, decision rationale, and next owner.

## Lessons Learned
- Keep concise notes for recurring execution/review/trading patterns.
- Capture only lessons that changed future implementation quality or cycle time.

## Recurrent Risks and Mitigations
- Track repeated failure modes and the mitigation that worked.
- Include trigger condition and measurable threshold for each mitigation.

## Do Not Store (volatile/noisy data)
- Temporary run logs, ephemeral command output, or unverified assumptions.
- Capability availability claims without verification from official capability source.
- Secrets, tokens, or credential-like values.
