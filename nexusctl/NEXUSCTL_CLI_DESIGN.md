# OpenClaw - nexusctl CLI Design (vollstaendig)
Version: 1.0
Date: 2026-04-27
Status: Design Proposal (implementierungsbereit)

---

## 1. Ziel und Scope

Dieses Dokument entwirft `nexusctl` vollstaendig fuer den aktuellen Stand der OpenClaw-Dokumentation.
Es setzt die normative Spezifikation aus `NEXUSCTL_FUNCTIONS.md` als verbindlichen Kern um und konkretisiert:

- CLI-UX und Kommandoverhalten
- Session-Mechanik im Agent-Kontext
- Rechte- und Gate-Pruefungen
- Fehler- und Exit-Code-Modell
- interne Modulstruktur fuer die Implementierung
- Teststrategie gegen AC-001 bis AC-009

Nicht im Scope:
- Phase-2 Features (`whoami`, `handoff`, `workitem`, Ticket/PR-Automation, `req` Schreibbefehle)
- Aenderung normativer Regeln ausserhalb der Master-Dokumente

---

## 2. Normative Quellen (Single Source of Truth)

1. `NEXUSCTL_FUNCTIONS.md`
- Normativ fuer Kommandos, Session-Regel, Rechte, Exit-Codes, Auditfelder.

2. `REQUIREMENTS_CLI_DB_PLAN.md`
- Normativ fuer MVP-Scope, Datenmodell und Akzeptanzkriterien AC-001..AC-009.

3. `ARCHITECTURE_PLAN.md`
- Normativ fuer Session-State-Lokation im Agent-Kontext und Session-Scope `agent_id + project_id`.

4. `SOFTWARE_DEVELOPMENT_SYSTEM.md`
- Normativ fuer Rolle `sw-techlead` als einzig berechtigte Freischaltung `planned -> available`.

Regel:
- Bei Konflikt gilt die Ownership-Matrix in `DOCUMENTATION_OWNERSHIP_MATRIX.md`.

---

## 3. Design-Alternativen und Empfehlung

### Ansatz A (empfohlen): Stateful CLI + Serverseitige Autoritaet

- CLI persistiert nur Session-Metadaten lokal im Agent-Kontext.
- Alle fachlichen Entscheidungen (Token-Validierung, Rollenpruefung, Gate-Regeln, Audit-ID) sind serverseitig.
- CLI bleibt duenn, robust und gut testbar.

Vorteile:
- klare Sicherheitsgrenze
- wenig Drift-Risiko gegen Master-Doku
- einfacher Rollout

Nachteile:
- API-Verfuegbarkeit notwendig

### Ansatz B: Thick CLI mit lokalen Fachregeln

- CLI prueft Gate-Regeln lokal und schreibt Events direkt.

Vorteile:
- funktioniert teilautonom bei schwacher API

Nachteile:
- hoher Drift gegen Normen
- duplizierte Business-Logik
- hohes Risiko fuer inkonsistente Audit-Ereignisse

### Ansatz C: Hybrid mit Read-Cache

- A wie oben, plus lokale Cache-Layer fuer `capabilities list/show`.

Vorteile:
- bessere Offline-Latenz

Nachteile:
- Konfliktpotenzial mit "DB ist Source of Truth"
- zusaetzliche Invalidation-Komplexitaet

Empfehlung:
- Ansatz A als MVP, ohne semantischen Capability-Cache.

---

## 4. CLI Produktverhalten

### 4.1 Kommandooberflaeche (MVP, verbindlich)

```text
nexusctl auth --agent-token <token> [--domain <id>] [--output table|json]

nexusctl capabilities list [--domain <id>] [--status all|planned|available] [--output table|json]

nexusctl capabilities show <capability-id> [--output table|json]

nexusctl capabilities set-status <capability-id> --to planned|available --reason <text> [--output table|json]
```

### 4.2 Globale UX-Regeln

- Default-Output: `table`
- Maschinenmodus: `--output json`
- Fehlernachrichten sind kurz, deterministisch und enthalten einen Fehlercode (z. B. `NX-PRECONDITION-001`).
- Kein implizites Token in Folgeaufrufen nach erfolgreichem `auth`.
- Ohne aktive Session fuer `capabilities *`: Exit `6`.

### 4.3 Eingaben und Validierung

`capability-id`:
- Pflichtformat: `F-[0-9]{3,}` (MVP)

`--to`:
- zulaessig: `planned|available`
- effektive Mutation im MVP nur `planned -> available`

`--reason`:
- Pflicht bei `set-status`
- Mindestlaenge 10, Max 500 Zeichen

`--status`:
- zulaessig: `all|planned|available`

`--output`:
- zulaessig: `table|json`

---

## 5. Session-Design

### 5.1 Scope und Lebenszyklus

- Scope: `agent_id + project_id`
- TTL: 60 Minuten
- Session ist terminalunabhaengig (mehrere Terminals desselben Agenten nutzbar)
- Ablauf:
1. `auth` validiert Token und legt Session aktiv an
2. `capabilities *` lesen aktive Session
3. bei Ablauf oder Revocation wird Session als ungueltig behandelt (Exit `6`)

### 5.2 Lokale Session-Datei

Basis im Agent-Kontext (aus Runtime-Doku):
- Linux Container: `/home/node/.openclaw/agents/<agent-id>/agent`

Datei:
- `<agentDir>/.nexusctl/sessions/<project-id>.json`

Beispiel:
```json
{
  "session_id": "S-2026-0001",
  "agent_id": "trading-strategist-01",
  "role": "trading-strategist",
  "project_id": "trading-system",
  "domain": "Trading",
  "issued_at": "2026-04-27T10:00:00Z",
  "expires_at": "2026-04-27T11:00:00Z",
  "status": "active"
}
```

### 5.3 Session-Precedence

1. Gueltige Session-Datei fuer aktuelles `project_id`
2. Sonst Fehler `NX-PRECONDITION-001` (keine aktive Session)

Wichtig:
- Token wird nicht lokal gespeichert.
- Nur Session-Metadaten werden gespeichert.

---

## 6. Auth- und Identity-Flow

### 6.1 Token-Aufloesung

Prioritaet:
1. `--agent-token`
2. `NEXUS_AGENT_TOKEN`

Ohne Token:
- Validation Error, Exit `2`

### 6.2 Auth-Ablauf

1. CLI sendet Token (+ optional `domain`) an Backend.
2. Backend mappt `agent_token -> agent_id, role, project_id`.
3. Backend erstellt aktive Session und Audit-Eintrag (`auth_log`).
4. Backend liefert:
- `auth_id`
- `session_id`
- Agent-/Projekt-Kontext
- Capability-Liste
5. CLI speichert Session-Metadaten lokal.
6. CLI rendert Antwort.

### 6.3 Auth-Antwort (json)

Kompatibel zu normativer Vorlage:

```json
{
  "ok": true,
  "auth_id": "AUTH-2026-0001",
  "session_id": "S-2026-0001",
  "agent_id": "trading-strategist-01",
  "role": "trading-strategist",
  "project_id": "trading-system",
  "domain": "Trading",
  "timestamp": "2026-04-27T10:00:00Z",
  "capabilities": [
    {
      "capability_id": "F-001",
      "title": "Paper Trading",
      "status": "available"
    }
  ]
}
```

---

## 7. Capabilities-Kommandos

### 7.1 `capabilities list`

Preconditions:
- aktive Session

Server-Input:
- `project_id` aus Session
- optional `domain`, `status`

Server-Output:
- Liste `capability_id`, `title`, `status`

Fehlerfaelle:
- Session fehlt/abgelaufen -> Exit `6`
- Backend down -> Exit `10`

### 7.2 `capabilities show <capability-id>`

Preconditions:
- aktive Session
- gueltige `capability-id`

Server-Output:
- `capability_id`, `title`, `status`, `subfunctions[]`, `requirements[]`

Fehlerfaelle:
- ID nicht gefunden -> Exit `3`

### 7.3 `capabilities set-status <capability-id> --to ... --reason ...`

Preconditions:
- aktive Session
- Rolle `sw-techlead`
- gueltige Eingaben

Serverseitige Gate-Pruefungen (verbindlich):
1. Transition ist `planned -> available`
2. alle zugeordneten `FR-*` sind `verified`
3. Nachweise vorhanden (`issue_ref`, `pr_ref`, `test_ref` != `none`)
4. Rolle ist `sw-techlead`

Erfolg:
- Audit Event in `capability_status_events`
- JSON gemaess normativer Vorlage

Fehlerfaelle:
- Rolle unzureichend -> Exit `4`
- Gate verletzt -> Exit `6`

---

## 8. Rechte- und Policy-Matrix (umgesetzt)

| Kommando | trading-* | sw-* | nexus | main |
|---|---|---|---|---|
| `auth` | Allow | Allow | Allow | Allow |
| `capabilities list` | Allow (Session) | Allow (Session) | Allow (Session) | Allow (Session) |
| `capabilities show` | Allow (Session) | Allow (Session) | Allow (Session) | Allow (Session) |
| `capabilities set-status` | Deny | Allow (`sw-techlead` only) | Deny | Deny |

Zusatz:
- `sw-*` heisst nicht automatisch Schreibrecht.
- Schreibrecht ist explizit auf `sw-techlead` eingeschraenkt.

---

## 9. Fehler- und Exit-Code-Konzept

### 9.1 Exit-Codes (verbindlich)

- `0` Erfolg
- `2` Validation Error
- `3` Not Found
- `4` Permission Denied
- `6` Precondition Failed
- `10` Infrastructure Error

### 9.2 Fehlerkatalog

| Fehlercode | Exit | Bedeutung |
|---|---:|---|
| `NX-VAL-001` | 2 | fehlendes/ungueltiges Flag |
| `NX-VAL-002` | 2 | Token fehlt (`--agent-token`/Env) |
| `NX-NOTFOUND-001` | 3 | Capability nicht gefunden |
| `NX-PERM-001` | 4 | Rolle darf Kommando nicht ausfuehren |
| `NX-PRECONDITION-001` | 6 | keine aktive Session |
| `NX-PRECONDITION-002` | 6 | Session abgelaufen |
| `NX-PRECONDITION-003` | 6 | Gate-Regel fuer Statuswechsel verletzt |
| `NX-INFRA-001` | 10 | Backend nicht erreichbar/Timeout |
| `NX-INFRA-002` | 10 | unerwarteter Backend-Fehler |

---

## 10. Backend-Vertrag (adapterfaehig)

Hinweis:
- Die API-Form ist hier als Implementierungsvertrag fuer die CLI definiert.
- Falls bereits ein anderer Transport existiert, wird nur ein kompatibler Adapter benoetigt.

### 10.1 Endpunkte

1. `POST /v1/nexus/auth`
2. `GET /v1/nexus/capabilities`
3. `GET /v1/nexus/capabilities/{capability_id}`
4. `POST /v1/nexus/capabilities/{capability_id}/status`

### 10.2 Header

- `X-Nexus-Session-Id` fuer Folgeaufrufe
- `X-Nexus-Agent-Id` optional fuer Audit-Korrelation

### 10.3 DTOs

Auth Request:
```json
{
  "agent_token": "tok_xxx",
  "domain": "Trading"
}
```

Set-Status Request:
```json
{
  "to": "available",
  "reason": "All requirements verified and evidence linked."
}
```

---

## 11. Interne Implementierungsarchitektur

Empfohlene Sprache:
- Go (ein Binary, stabile CLI-Libs, einfache Distribution)

### 11.1 Modulgrenzen

1. `cmd`
- Entry-Point, CLI-Bootstrap

2. `internal/cli`
- Command-Definitionen, Flag-Parsing, Renderer (table/json)

3. `internal/session`
- Session-Store (load/save/expire), Locking

4. `internal/auth`
- Auth-Usecase, Token-Resolution

5. `internal/capabilities`
- List/Show/SetStatus-Usecases

6. `internal/api`
- HTTP-Client + Retry/Timeout + Fehler-Mapping

7. `internal/policy`
- Clientseitige Basispruefungen (z. B. lokale Rollenblockade vor Request)

8. `internal/output`
- Tabellarische Ausgabe + JSON marshalling

9. `internal/errors`
- Domainenumeration der `NX-*` Fehlercodes

### 11.2 Verzeichnisstruktur (Zielbild)

```text
nexusctl/
|- cmd/
|  '- nexusctl/
|     '- main.go
|- internal/
|  |- api/
|  |- auth/
|  |- capabilities/
|  |- cli/
|  |- errors/
|  |- output/
|  |- policy/
|  '- session/
|- test/
|  |- e2e/
|  '- fixtures/
|- docs/
|  '- API_CONTRACT.md
|- go.mod
|- go.sum
'- README.md
```

---

## 12. Sicherheits- und Betriebsregeln

- Token niemals loggen.
- Session-Dateien mit restriktiven Rechten schreiben.
- Kein dauerhafter Capability-Cache im MVP.
- Timeouts standardmaessig 5s (auth 8s), max 1 Retry bei GET.
- `set-status` niemals auto-retry (idempotency und Governance-Risiko).

---

## 13. Teststrategie (gegen AC-001..AC-009)

### 13.1 Unit-Tests

- Token-Resolution Prioritaet Flag vor Env
- Session-Expiry
- Flag-Validation pro Kommando
- Exit-Code-Mapping

### 13.2 Integrationstests (API-Mock)

- `auth` Erfolg + Session gespeichert + Capability-Liste gerendert
- `list/show` ohne Session -> Exit 6
- `show` unknown ID -> Exit 3
- `set-status` als Nicht-`sw-techlead` -> Exit 4
- `set-status` Gate fail -> Exit 6
- Infra-Fehler -> Exit 10

### 13.3 E2E-Tests (gegen Test-Backend)

- AC-001 bis AC-009 jeweils als eigener Testfall mit eindeutigem Testnamen
- JSON Snapshots fuer maschinenlesbare Ausgabe

---

## 14. Umsetzungsreihenfolge

1. CLI-Skeleton + Root-Command + globale Flags
2. Session-Store
3. `auth`
4. `capabilities list`
5. `capabilities show`
6. `capabilities set-status`
7. Fehlerkatalog + Exit-Codes finalisieren
8. Test-Suite komplettieren
9. Doku und Betriebsbeispiele

---

## 15. Beispiele (operator-ready)

Auth:
```bash
nexusctl auth --agent-token "$NEXUS_AGENT_TOKEN" --output table
```

Liste:
```bash
nexusctl capabilities list --status available --output table
```

Detail:
```bash
nexusctl capabilities show F-001 --output json
```

Freischaltung:
```bash
nexusctl capabilities set-status F-001 --to available --reason "All FR verified, evidence linked." --output json
```

---

## 16. Annahmen und offene Punkte

Annahmen:
- Backend stellt die benoetigten Endpunkte bereit oder kann adapterbasiert angebunden werden.
- Agent-Kontextpfad ist zur Laufzeit aufloesbar.

Offene Punkte (vor Implementierung final entscheiden):
1. Konkretes Transportprotokoll (REST bestaetigen oder Adapter auf vorhandenen Gateway-Client).
2. Feld `domain`: rein filternd oder serverseitig gegen Projekt validierend.
3. Ob `set-status --to planned` im MVP explizit verboten (empfohlen: verboten, da nur `planned -> available` normativ).

