---
name: nexusctl_github_adapter
description: Use the Nexus GitHub Adapter for issues, PR links, PR sync, repo sync, status checks, and GitHub evidence.
---

# Nexusctl GitHub Adapter

Use this skill when work touches GitHub issues, PRs, reviews, CI, repo metadata, or GitHub/Nexus synchronization.

## Commands

```bash
nexusctl github issue create <request_id> [--dry-run] [--title TEXT] [--label LABEL]... [--assignee USER]... --output json
nexusctl github issue sync <request_id> --output json
nexusctl github pr link <request_id> --url URL --output json
nexusctl github pr sync <request_id> --output json
nexusctl github status <request_id> --output json
nexusctl github sync <request_id> --output json
nexusctl github repos list --output json
nexusctl github repos sync --output json
```

## Rules

- Do not treat GitHub labels as lifecycle authority.
- Do not create duplicate issues for the same request.
- Run dry-run for issue creation when uncertain.
- Link PRs through Nexus, then sync status.
- If a direct GitHub action is unavoidable, state why the adapter cannot perform it and ask for approval when the action is mutating.

## Gate Evidence

- `in-review` requires approved implementation context and linked PR.
- `approved` requires approved review, passing checks, and policy state ok.
- `done` requires merged PR, merge commit SHA, review evidence, checks evidence, and no do-not-touch violation.
