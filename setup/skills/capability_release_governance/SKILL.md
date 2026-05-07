---
name: capability_release_governance
description: Promote capabilities and handle release governance only when Nexus and GitHub evidence gates are satisfied.
---

# Capability Release Governance

Use for capability status changes, release gates, and state-update-needed loops.

Before promotion:

- Request is `done` or has equivalent complete evidence.
- PR is merged and synced through Nexus GitHub adapter.
- Review state approved, checks passing, policy ok.
- Acceptance criteria and tests are attached as evidence.
- No unresolved reviewer or do-not-touch blocker exists.

Promotion command:

```bash
nexusctl capabilities set-status <capability_id> --to available --reason "Evidence: request ..., PR ..., tests ..." --output json
```

Do not promote from open PR evidence alone.
