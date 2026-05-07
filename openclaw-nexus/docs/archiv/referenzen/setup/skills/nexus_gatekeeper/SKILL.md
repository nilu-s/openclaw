---
name: nexus_gatekeeper
description: Gate submitted capability requests and preserve Nexus lifecycle integrity as the coordination authority.
---

# Nexus Gatekeeper

Gate submitted requests with exactly one decision:

- accept and transition to `accepted`
- reject to `gate-rejected`
- request correction or escalation when evidence is insufficient

Canonical rejection reasons:

- `missing-required-fields`
- `invalid-risk-or-priority`
- `non-testable-acceptance-criteria`
- `not-a-software-capability-gap`
- `reference-not-resolvable`

After acceptance, route through:

```bash
nexusctl request transition <id> --to accepted --reason "..." --output json
nexusctl request transition <id> --to needs-planning --reason "Ready for software planning" --output json
```

Create or sync GitHub parent issue only through `nexusctl github issue ...`.
