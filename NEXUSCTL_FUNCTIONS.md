# OpenClaw - nexusctl Function Specification
Version: 4.0
Date: 2026-04-29
Status: Verbindlich

---

## 1. Ziel

`nexusctl` stellt einen schlanken, token-gebundenen Agentenzugang bereit.
Normatives Bedienziel:

1. `context` fuer den Gesamtueberblick
2. `request create` fuer One-Call-Bedarfsmeldung
3. `request list/show` fuer laufende Nachverfolgung

Lifecycle-Mutationen bleiben bei `nexus`.

---

## 2. Identity und Sicherheitsmodell

- Jeder Aufruf ist token-gebunden (`NEXUS_AGENT_TOKEN` oder Seed-Token-Aufloesung).
- Identitaet wird serverseitig auf `agent_id`, `role`, `domain`, `project_id` aufgeloest.
- Client-seitige Overrides fuer Domain/Agent sind unzulaessig.
- Lokaler Session-State ist nur Transport-Cache, nicht Autoritaetsquelle.

---

## 3. Command Surface (normativ)

Primarflaeche:

```text
nexusctl context [--output table|json]

nexusctl request create --objective <text> --missing-capability <text> --business-impact <text> --expected-behavior <text> --acceptance-criteria <text> --risk-class <low|medium|high|critical> --priority <P0|P1|P2|P3> --trading-goals-ref <ref> [--output table|json]

nexusctl request list [--status all|draft|submitted|gate-rejected|accepted|needs-planning|ready-to-build|in-build|in-review|review-failed|state-update-needed|done|adoption-pending|closed|cancelled] [--limit 100] [--output table|json]

nexusctl request show <request-id> [--output table|json]

nexusctl request transition <request-id> --to <status> --reason <text> [--output table|json]

nexusctl request set-issue <request-id> --issue-ref <ref> [--issue-number <n>] [--issue-url <url>] [--output table|json]
```

Kompatibilitaets-Aliases:

- `handoff submit/list/set-issue` bleiben kompatibel und mappen intern auf denselben Request-Store.
- `auth`, `capabilities list/show/set-status` bleiben erhalten.

---

## 4. Rollenrechte

| Kommando | trading-strategist | trading-analyst / trading-sentinel | sw-* | nexus |
|---|---|---|---|---|
| `context` | Allow | Allow | Allow | Allow |
| `request create` | Allow | Deny | Deny | Deny |
| `request list/show` | scoped Allow | scoped Allow | scoped Allow | full Allow |
| `request transition` | Deny | Deny | Deny | Allow |
| `request set-issue` | Deny | Deny | Deny | Allow |
| `capabilities set-status` | Deny | Deny | `sw-techlead` only | Deny |

Hinweis:
- `request set-issue` ist nur im Status `accepted` zulaessig.
- Issue-Linkage vor `accepted` ist unzulaessig.

---

## 5. Lifecycle-Regeln fuer Requests

Kanonische Status:

1. `draft`
2. `submitted`
3. `gate-rejected`
4. `accepted`
5. `needs-planning`
6. `ready-to-build`
7. `in-build`
8. `in-review`
9. `review-failed`
10. `state-update-needed`
11. `done`
12. `adoption-pending`
13. `closed`
14. `cancelled`

Uebergaenge:
- `draft -> submitted|cancelled`
- `submitted -> accepted|gate-rejected`
- `gate-rejected -> draft|cancelled`
- `accepted -> needs-planning`
- `needs-planning -> ready-to-build|cancelled`
- `ready-to-build -> in-build`
- `in-build -> in-review|cancelled`
- `in-review -> done|review-failed|state-update-needed`
- `review-failed -> in-build`
- `state-update-needed -> in-review`
- `done -> adoption-pending|closed`
- `adoption-pending -> closed|needs-planning`

Jeder Wechsel wird mit Grund, Actor und Zeitstempel auditiert.

---

## 6. Kontextvertrag (`context`)

`context` liefert in einem Aufruf:

- aufgeloeste Agent-Identitaet (`agent_id`, `role`, `domain`, `project_id`)
- erlaubte Aktionen (`allowed_actions`)
- Capability-Snapshot
- relevante offene Requests (rollenbasiert gescoped)

Ziel:
- Minimaler operativer Einstieg ohne mehrstufiges Kommando-Set.

---

## 7. Exit Codes

- `0`: Erfolg
- `2`: Validation Error
- `3`: Not Found
- `4`: Permission Denied
- `6`: Precondition Failed
- `10`: Infrastructure Error

---

## 8. Abwaertskompatibilitaet

- Bestehende Flows mit `auth` + `handoff *` bleiben lauffaehig.
- Neues Lean-Verhalten priorisiert `context` + `request *`.

