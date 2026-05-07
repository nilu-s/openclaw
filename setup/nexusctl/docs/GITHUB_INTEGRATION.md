# GitHub Integration

## 1. Overview

Nexus GitHub Adapter v2.1 creates sanitized issues, links pull requests, synchronizes review/check/file state and writes evidence. Nexus stays the lifecycle source of truth.

## 2. Setup

Set `NEXUS_GITHUB_TOKEN`, optional `NEXUS_GITHUB_API_BASE`, and `NEXUS_GITHUB_WEBHOOK_SECRET`.

## 3. Auth

Only the GitHub auth provider reads the token. The client sends `Accept: application/vnd.github+json`, `Authorization: Bearer <token>`, `X-GitHub-Api-Version: 2022-11-28` and `User-Agent: nexusctl`.

## 4. Repo Registry

Repositories map `repo_id` to `github_owner` and `github_repo`. Workers may see only assigned repositories.

## 5. Issue Creation

`nexusctl github issue create REQ-123` renders a sanitized body from approved implementation context and creates a GitHub issue. Adapter state is written to `github_issues`; work evidence is written to `work_evidence`.

## 6. PR Link and Sync

`nexusctl github pr link REQ-123 --url ...` validates the URL against the target repo. Sync reads PR state, review state, check state, changed files and commits.

## 7. Review and Checks

Latest review per reviewer determines review state. Check failures dominate pending/passing states.

## 8. Evidence

Each create/sync/link action records evidence. Policy violations also record dedicated evidence.

## 9. Webhooks

`POST /v1/github/webhooks` verifies the HMAC signature, stores idempotent delivery events and resolves linked requests where possible.

## 10. Agent Responsibilities

Architects plan work and can create issues. Builders implement in assigned repos and link assigned PRs. Reviewers inspect assigned review context. Tech leads can sync repos and override gates.

## 11. Failure Modes

GitHub HTTP errors map to `NX-GH-*` codes. Missing repo mappings, invalid URLs and missing lifecycle prerequisites are precondition or validation errors.

## 12. Security Model

The adapter never clones, commits, pushes, merges, resolves conflicts, crawls arbitrary repos or issues global GitHub rights to workers.
