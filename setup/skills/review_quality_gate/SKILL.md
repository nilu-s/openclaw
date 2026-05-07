---
name: review_quality_gate
description: Review software work against acceptance criteria, implementation context, tests, policy gates, and operational safety.
---

# Review Quality Gate

Review dimensions:

1. Request acceptance criteria are satisfied.
2. Implementation matches approved context.
3. Do-not-touch policy is respected.
4. Tests and CI evidence are credible.
5. Error handling and rollback are acceptable.
6. No secrets or live-trading behavior were changed unexpectedly.

Verdicts:

```bash
nexusctl reviews submit <request_id> --verdict approved --summary "..." --output json
nexusctl reviews submit <request_id> --verdict changes-requested --summary "..." --output json
nexusctl reviews submit <request_id> --verdict rejected --summary "..." --output json
```

A review must include evidence, not just opinion.
