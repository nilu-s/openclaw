# OpenClaw - Requirements CLI/DB Plan
Version: 2.3
Date: 2026-04-26
Status: Draft (vereinfacht)

---

## 1. Zielbild

DB bleibt Source of Truth fuer Requirements.
`nexusctl` nutzt im MVP einen klaren Einstieg:
- `auth` authentifiziert Agent+Projekt und liefert sofort die komplette Feature-Liste.

Danach kann ein Agent mit `capabilities show` einzelne Features detailliert auslesen.
Bei Bedarf kann der Agent den Stand ueber `capabilities list` erneut abrufen.

---

## 2. MVP Scope

Enthalten:
- `auth`
- `capabilities list`
- `capabilities show`
- `capabilities set-status` (nur `sw-techlead`, nur `planned -> available`)
- statische Agent-Projekt-Token-Aufloesung (`agent_token -> agent_id, role, project_id`)

Nicht enthalten:
- `whoami`
- `capabilities acknowledge`
- Ticket/PR-Steuerung
- Handoff-Automation
- Snapshot-Export

---

## 3. Verbindliche Nutzung

Capability-Preflight vor Strategie-, Planungs- oder Handoff-Arbeit ist verpflichtend.
Die normative CLI-Regel (`auth`, Session-Nutzung, Re-Checks) liegt ausschliesslich in [NEXUSCTL_FUNCTIONS.md](C:/projects/DebugMyself/openclaw/NEXUSCTL_FUNCTIONS.md).

---

## 4. Datenmodell (MVP-minimal)

- `capabilities`
  - `capability_id` (`F-...`)
  - `domain`
  - `title`
  - `status` (`available|planned`)

- `capability_details`
  - `capability_id`
  - `subfunction_ids` (`SF-...`)
  - `requirement_ids` (`FR-...`)
  - `state_summary`

- `capability_status_events`
  - `event_id`
  - `capability_id`
  - `old_status`
  - `new_status`
  - `reason`
  - `agent_id`
  - `project_id`
  - `timestamp`

- `auth_log`
  - `auth_id`
  - `session_id`
  - `agent_id`
  - `role`
  - `project_id`
  - `domain`
  - `timestamp`

- `agent_sessions`
  - `session_id`
  - `agent_id`
  - `project_id`
  - `status` (`active|expired|revoked`)
  - `expires_at`

- `agent_registry`
  - `agent_token`
  - `agent_id`
  - `role`
  - `project_id`
  - `active`

---

## 5. Akzeptanzkriterien

- AC-001: Jeder Agent kann per `auth` die Feature-Liste seines Projekts abrufen.
- AC-002: `auth` wird ohne gueltiges Agent-Projekt-Token abgelehnt.
- AC-003: `auth` erzeugt einen auditierbaren Auth-Eintrag.
- AC-004: `capabilities list` liefert den aktuellen Stand `planned|available` im Session-Kontext.
- AC-005: `capabilities show` liefert eine konsistente Detailsicht je Feature-ID.
- AC-006: Strategist kann auf Basis von `available|planned` Strategien ableiten.
- AC-007: `capabilities show` und `capabilities list` werden ohne aktive Session abgelehnt.
- AC-008: `capabilities set-status` erlaubt `planned -> available` nur fuer `sw-techlead` mit Audit-Event.
- AC-009: `capabilities set-status` wird abgelehnt, wenn Requirements nicht `verified` sind oder Nachweise fehlen.

---

## 6. Phase 2 (optional)

Erst nach stabilem MVP:
- `whoami`
- `capabilities acknowledge`
- `handoff` Kommandos
- `workitem` Kommandos
- erweiterte State-/Req-Mutation
