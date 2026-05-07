---
name: handoff_contract
description: Validate and create capability-gap handoffs between trading, Nexus, and software agents.
---

# Capability Handoff Contract

Required fields:

- `objective`
- `missing_capability`
- `business_impact`
- `expected_behavior`
- `acceptance_criteria` as one or more testable criteria
- `risk_class`: `low`, `medium`, `high`, or `critical`
- `priority`: `P0`, `P1`, `P2`, or `P3`
- `goal_ref`

Deterministic identity key: `objective + missing_capability + goal_ref`. Mutable details such as business impact, priority and acceptance criteria update the existing request instead of changing identity.

## Validation

Reject or return to draft when any required field is missing, risk/priority is invalid, acceptance criteria are not testable, the request is not a software capability gap, or the referenced `goal_ref` cannot be resolved through Nexus goal aliases.

## Create or Submit

```bash
nexusctl request create --objective "..." --missing-capability "..." --business-impact "..."   --expected-behavior "..." --acceptance-criteria "..." --risk-class high --priority P1 --goal-ref TG-001 --output json
```

Strategist submits or cancels drafts via `nexusctl request transition <id> --to submitted|cancelled --reason "..." --output json`.
