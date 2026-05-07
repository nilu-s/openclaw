# OpenClaw - Requirements CLI/DB Plan
Version: 3.0
Date: 2026-04-29
Status: Verbindlich

---

## 1. Zielbild

`nexusctl` liefert einen schlanken, generischen Agenten-Workflow:

1. `context` fuer sofortige Lageeinschaetzung
2. `request create` fuer One-Call-Bedarfsmeldung
3. `request list/show` fuer Nachverfolgung

Mutationen im Lifecycle/Issue-Linkage bleiben exklusiv bei `nexus`.

---

## 2. Scope

Enthalten:
- Token-gebundene Identitaetsaufloesung (`agent_id`, `role`, `domain`, `project_id`)
- `context`
- `request create/list/show`
- `request transition` (`nexus` only)
- `request set-issue` (`nexus` only, nur in `accepted`)
- Kompatibilitaet fuer `handoff *` und bestehende Capability-Commands

Nicht im Scope:
- automatische GitHub-Issue-Erzeugung im Backend
- freie Domain-/Agent-Overrides durch CLI-Parameter

---

## 3. Datenmodell (verbindlich)

- `handoff_requests` (Request-Primarobjekt)
  - enthaelt Pflichtfelder des Trading->Software-Contracts
  - enthaelt Lifecycle-Status
  - enthaelt Issue-Linkage (`github_issue_ref`, `github_issue_number`, `github_issue_url`)
  - enthaelt letzte Transition-Metadaten (`last_reason`, `last_actor_agent_id`, `last_transition_at`)

- `handoff_status_events`
  - append-only Audit fuer Statuswechsel
  - Felder: `from_status`, `to_status`, `reason`, `actor_agent_id`, `actor_role`, `project_id`, `domain`, `timestamp`

- `agent_registry` / `agent_sessions`
  - token-basierte Identitaet + Session-Cache

---

## 4. Akzeptanzkriterien

- AC-001: `context` liefert Identitaet, erlaubte Aktionen, Capabilities und relevante offene Requests.
- AC-002: `request create` setzt Default-Status `submitted` ohne Zusatzschritte.
- AC-003: `request transition` ist fuer Nicht-`nexus` gesperrt.
- AC-004: `request set-issue` ist nur in `accepted` erlaubt.
- AC-005: Jeder Statuswechsel wird auditiert.
- AC-006: Token bestimmt Identitaet je Aufruf; kein Domain/Agent-Override.
- AC-007: Bestehende `handoff *` Kommandos bleiben kompatibel.

