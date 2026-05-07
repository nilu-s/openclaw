---
name: software_delivery_workflow
description: Plan, build, review, and complete software delivery through Nexus work commands.
---

# Software Delivery Workflow

## Planning

```bash
nexusctl work plan <request_id> --repo <repo_id> --branch <branch> --assign <builder_agent_id> --reviewer <reviewer_agent_id> --sanitized-summary "..." --output json
nexusctl work set-implementation-context <request_id> --component "..." --likely-file "..." --do-not-touch "..." --test-command "..." --acceptance-criteria "..." --output json
nexusctl work approve-plan <request_id> --output json
# Use work assign only to change the builder after planning; reviewer remains explicit in work plan.
nexusctl work assign <request_id> --agent sw-builder-01 --output json
```

## Build

Builders work only from approved implementation context. Submit evidence:

```bash
nexusctl work submit-evidence <request_id> --kind test --summary "..." --ref "..." --output json
nexusctl github pr link <request_id> --url <pr_url> --output json
nexusctl github pr sync <request_id> --output json
nexusctl work transition <request_id> --to in-review --reason "PR ready with evidence" --output json
```

## Review and Close

Reviewers use `nexusctl reviews submit` only for work assigned to their `reviewer_agent_id`. Techlead or Nexus advances lifecycle only when gates are satisfied.
