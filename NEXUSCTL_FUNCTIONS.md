# OpenClaw - nexusctl Function Specification
Version: 3.3
Date: 2026-04-26
Status: Draft (MVP reduziert)

---

## 1. Ziel

`nexusctl` hat im MVP genau einen Kernzweck:
- Agent authentifiziert sich einmal und erhaelt sofort die komplette Feature-Liste.

Danach kann der Agent einzelne Features ueber `capabilities show` im Detail abfragen, ohne das Token erneut zu senden.

---

## 2. MVP-Prinzip (klein halten)

- Ein verpflichtender Einstieg: `auth`.
- Eine Listenabfrage: `capabilities list`.
- Eine Detailabfrage: `capabilities show`.
- Eine kontrollierte Statusmutation: `capabilities set-status`.
- Session statt wiederholter Token-Uebergabe.
- Keine Ticket-/PR-Automation im MVP.
- Keine komplexe Workflow-Orchestrierung im MVP.

---

## 3. Identity und Session Model

`nexusctl` nutzt projektgebundene Agent-Tokens:
- Es gibt genau ein Token pro Paar (`agent_id`, `project_id`).
- `agent_token` wird auf `agent_id`, `role` und `project_id` aufgeloest.

Session-Regel:
- Scope ist `agent_id + project_id` (nicht terminalgebunden).
- `auth` erzeugt eine aktive Session fuer den Agenten im Projektkontext.
- Folgeaufrufe nutzen diese Session und brauchen kein Token.
- Mehrere Terminals desselben Agenten koennen dieselbe aktive Session nutzen.
- Ohne aktive Session werden Folgeaufrufe abgelehnt.
- Session-TTL im MVP: 60 Minuten, danach ist Re-Auth erforderlich.

Token-Aufloesung:
1. CLI-Flag: `--agent-token`
2. Env-Fallback: `NEXUS_AGENT_TOKEN`

---

## 4. MVP Command Surface

```text
nexusctl auth --agent-token <token> [--domain <id>] [--output table|json]

nexusctl capabilities list [--domain <id>] [--status all|planned|available] [--output table|json]

nexusctl capabilities show <capability-id> [--output table|json]

nexusctl capabilities set-status <capability-id> --to planned|available --reason <text> [--output table|json]
```

### 4.1 Kommandozwecke

- `auth`
  - validiert Token.
  - setzt Agent-, Rollen- und Projektkontext aus Token-Mapping.
  - liefert als Antwort automatisch die Feature-Liste fuer das gemappte Projekt.
  - erzeugt einen Audit-Eintrag.

- `capabilities list`
  - liefert die aktuelle Capability-Liste im Session-Kontext.
  - dient als expliziter Re-Check nach `auth`.

- `capabilities show`
  - liefert die Detailsicht fuer genau eine Capability-ID.
  - nutzt die aktive Session aus `auth`.
  - sendet im Normalfall kein Token mehr mit.

- `capabilities set-status`
  - aendert den Status einer Capability.
  - im MVP ist nur `planned -> available` als Freischaltung vorgesehen.
  - nur fuer `sw-techlead` erlaubt.
  - prueft vor Freischaltung die Gate-Regeln (siehe Abschnitt 8.1).

---

## 5. Ausgabeformat

`auth --output json`:

```json
{
  "ok": true,
  "auth_id": "AUTH-2026-0001",
  "session_id": "S-2026-0001",
  "agent_id": "trading-strategist-01",
  "role": "trading-strategist",
  "project_id": "trading-system",
  "domain": "Trading",
  "timestamp": "2026-04-26T12:00:00Z",
  "capabilities": [
    {
      "capability_id": "F-001",
      "title": "Paper Trading",
      "status": "available"
    },
    {
      "capability_id": "F-002",
      "title": "Kraken API Integration",
      "status": "planned"
    }
  ]
}
```

`capabilities show --output json`:

```json
{
  "capability_id": "F-001",
  "title": "Paper Trading",
  "status": "available",
  "subfunctions": [
    "SF-001.1",
    "SF-001.2"
  ],
  "requirements": [
    "FR-001.1.1",
    "FR-001.2.1"
  ]
}
```

`capabilities set-status --output json`:

```json
{
  "ok": true,
  "event_id": "CAP-STATUS-2026-0001",
  "capability_id": "F-001",
  "old_status": "planned",
  "new_status": "available",
  "reason": "All requirements verified and evidence linked.",
  "agent_id": "sw-techlead-01",
  "project_id": "trading-system",
  "timestamp": "2026-04-26T13:00:00Z"
}
```

---

## 6. Rollenrechte (MVP)

| Kommando | trading-* | sw-* | nexus | main |
|---|---|---|---|---|
| `auth` | Allow (Token Pflicht) | Allow (Token Pflicht) | Allow (Token Pflicht) | Allow (Token Pflicht) |
| `capabilities list` | Allow (aktive Session Pflicht) | Allow (aktive Session Pflicht) | Allow (aktive Session Pflicht) | Allow (aktive Session Pflicht) |
| `capabilities show` | Allow (aktive Session Pflicht) | Allow (aktive Session Pflicht) | Allow (aktive Session Pflicht) | Allow (aktive Session Pflicht) |
| `capabilities set-status` | Deny | Allow (`sw-techlead` only) | Deny | Deny |

---

## 7. Exit Codes

- `0`: Erfolg
- `2`: Validation Error
- `3`: Not Found
- `4`: Permission Denied
- `6`: Precondition Failed (z. B. keine aktive Session)
- `10`: Infrastructure Error

---

## 8. Audit-Pflicht (MVP)

Nur fuer `auth` verpflichtend:
- `auth_id`
- `session_id`
- `agent_id`
- `role`
- `project_id`
- `domain`
- `timestamp`

Fuer `capabilities set-status` verpflichtend:
- `event_id`
- `capability_id`
- `old_status`
- `new_status`
- `reason`
- `agent_id`
- `project_id`
- `timestamp`

### 8.1 Gate-Regeln fuer `planned -> available`

Eine Freischaltung ist nur gueltig, wenn:
- alle zugeordneten `FR-...` im Requirements-State auf `verified` stehen,
- Nachweise vorhanden sind (`issue_ref`, `pr_ref`, `test_ref` nicht `none`),
- Aufruferrolle `sw-techlead` ist.

---

## 9. Phase 2 (nicht im MVP)

Die folgenden Bereiche sind bewusst aus dem MVP entfernt:
- `whoami`
- `capabilities acknowledge`
- `handoff` Befehlsfamilie
- `workitem` Befehlsfamilie
- `req` Schreibbefehle
- Snapshot-Export
