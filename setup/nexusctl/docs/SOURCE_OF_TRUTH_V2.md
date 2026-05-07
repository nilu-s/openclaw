# Source of Truth v2

Nexus is the source of truth for systems, goals, requests, work, scopes, lifecycle and evidence.

GitHub is the source of truth for code, issues, pull requests, reviews and CI.

The GitHub Adapter is only a synchronization and evidence layer. GitHub metadata is stored in `github_issues`, `github_pull_requests` and `github_events`. Requests contain Nexus routing data only: source/target systems, goal reference, status, priority, risk, objective, task fields, target repository, branch, assignment and implementation context.

## Evidence Mapping

GitHub synchronization emits work evidence kinds:

- `github_issue`
- `github_issue_sync`
- `github_pr_linked`
- `github_pr_sync`
- `github_reviews`
- `github_checks`
- `github_policy_violation`
- `github_sync`
- `github_webhook`
- `manual_override`

## Scope Model

Builders and reviewers receive assigned-only GitHub visibility. Tech leads and Nexus can inspect broader adapter status. Worker agents do not receive global repository synchronization rights.

## Lifecycle Gates

Nexus lifecycle transitions evaluate adapter evidence; GitHub does not become the work item database.
