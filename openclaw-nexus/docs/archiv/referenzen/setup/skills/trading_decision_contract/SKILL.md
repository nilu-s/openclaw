---
name: trading_decision_contract
description: Make trading strategy, capability-gap, and post-delivery adoption decisions with risk framing and Nexus traceability.
---

# Trading Decision Contract

Before strategy or adoption decisions, inspect:

```bash
nexusctl context --output json
nexusctl goals list --status active --output json
nexusctl request list --status all --output json
nexusctl capabilities list --status all --output json
```

Decision types: `promote`, `hold`, `reject`, `adopt`, `adopt-later`, `reopen-gap`.

Every decision must state objective, evidence, risk framing, constraints, and next owner.

Never place live trades or change live trading mode from this skill.
