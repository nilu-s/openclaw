# Nexus API Contract

## GitHub Adapter Routes

```http
POST /v1/nexus/github/issues/{request_id}
POST /v1/nexus/github/issues/{request_id}/sync

POST /v1/nexus/github/pull-requests/{request_id}/link
POST /v1/nexus/github/pull-requests/{request_id}/sync

POST /v1/nexus/github/sync/{request_id}
GET  /v1/nexus/github/status/{request_id}

GET  /v1/nexus/github/repositories
POST /v1/nexus/github/repositories/sync

POST /v1/github/webhooks
```

## Issue Create Payload

```json
{
  "title": "optional title",
  "labels": ["nexus"],
  "assignees": ["alice"],
  "dry_run": false
}
```

`dry_run=true` returns the rendered sanitized issue body and does not call GitHub or write adapter tables.

## PR Link Payload

```json
{"url": "https://github.com/org/repo/pull/78"}
```

The URL must match the repository mapped by `target_repo_id`.

## Status Response

```json
{
  "request_id": "REQ-123",
  "github": {
    "issue": {"number": 45, "state": "open", "url": "https://github.com/org/repo/issues/45"},
    "pull_request": {
      "number": 78,
      "state": "open",
      "draft": false,
      "merged": false,
      "review_state": "approved",
      "checks_state": "passing",
      "policy_state": "ok",
      "changed_files": ["src/trading_engine/risk/check_order.py"]
    }
  }
}
```

## GitHub Error Codes

- `NX-GH-AUTH`
- `NX-GH-NOT-FOUND`
- `NX-GH-DISABLED`
- `NX-GH-VALIDATION`
- `NX-GH-RATE-LIMIT`
- `NX-GH-UPSTREAM`

Raw GitHub tracebacks are not exposed to agents.

## Webhook Contract

The webhook endpoint expects `X-GitHub-Delivery`, `X-GitHub-Event` and `X-Hub-Signature-256`. Delivery IDs are idempotent in `github_events`.
