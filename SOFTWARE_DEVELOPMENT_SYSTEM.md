# OpenClaw - Software Development System
Version: 5.4
Date: 2026-04-27
Status: Verbindlich

---

## 1. Scope

Dieses Dokument regelt ausschliesslich die Software-Lane:
- Triage
- Planung
- Implementierung
- Review/Merge-Gate
- Requirements-Governance
- Capability-Lieferung
- Tooling-Governance fuer `nexusctl` und GitHub-Artefakte

---

## 2. Kanonische SW-Artefakte

Pro Software-Repository sind verpflichtend:

1. Requirements-Katalog (DB)
- Zweck: Feature-/Subfunktions-/Requirement-Definitionen.
- Single Writer: `sw-techlead`.

2. Requirements-State (DB)
- Zweck: aktueller Umsetzungs- und Nachweis-Ist-Zustand.
- Single Writer: `sw-techlead`.

Regel:
- Umsetzung ohne Referenz auf `goals_ref` und `state_ref` gilt als unvollstaendig.

---

## 3. Integrierte Governance (Constitution fuer SW-Lane)

### 3.1 Rollen-Charter

- `nexus`: Eingangstriage, Routing, Lifecycle-Konsistenz.
- `sw-architect`: Zerlegt Anforderungen in testbare Arbeitspakete.
- `sw-builder`: Implementiert auf Branch/PR mit Tests.
- `sw-reviewer`: Fuehrt Qualitaetsgate vor Merge durch.
- `sw-techlead`: Single Writer fuer Goals/State, Architektur-Governance.

### 3.2 Autoritaet in der SW-Lane

| Action | nexus | sw-architect | sw-builder | sw-reviewer | sw-techlead |
|---|---|---|---|---|---|
| SW-Triage/Routing | Execute/Decide | Propose | - | - | Propose |
| SW-Planung | Propose | Execute/Decide | - | - | Propose |
| SW-Implementierung | - | Propose | Execute/Decide | - | - |
| SW-Review/Merge-Gate | - | Propose | Propose | Execute/Decide | Propose |
| Requirements-Katalog pflegen | Propose | Propose | Propose | Propose | Execute/Decide |
| Requirements-State pflegen | Propose | Propose | Propose | Propose | Execute/Decide |

### 3.3 Harte Grenzen

- Keine Trading-Strategieentscheidungen in der SW-Lane.
- Keine Pflege von Trading-Zielen.
- Kein Domain-Uebergang ohne formalen Handoff.

---

## 4. Verbindlicher Workflow

1. Triage:
- `nexus` validiert Mindestdaten und routet in die SW-Lane.

2. Planung:
- `sw-architect` plant gegen Requirements-Katalog + Requirements-State.
- Capability-Preflight vor Planungsstart ist verpflichtend; die normative CLI-Regel liegt in [NEXUSCTL_FUNCTIONS.md](NEXUSCTL_FUNCTIONS.md).

3. Umsetzung:
- `sw-builder` implementiert einen klaren Scope auf Branch/PR.

4. Review:
- `sw-reviewer` prueft Korrektheit, Scope, Tests und Konsistenz zu Goals/State.

5. Governance:
- `sw-techlead` aktualisiert bei Inkonsistenzen Requirements-Katalog oder Requirements-State.
- `sw-techlead` schaltet Feature-Status `planned -> available` ausschliesslich ueber `nexusctl capabilities set-status` frei.

6. Abschluss:
- `nexus` schliesst den Lifecycle und dokumentiert den Status.

Lifecycle-Hinweis:
- Status, Uebergaenge und Eskalationspfade sind im Handoff-Contract normiert.

---

## 5. Eingangsvertrag aus Trading

Trading-Anforderungen muessen als formaler Handoff kommen.
Die SW-Lane akzeptiert nur Handoffs, die dem Vertragsstandard entsprechen.

Wichtig:
- Die SW-Lane braucht keine Kenntnis der Trading-Strategie.
- Die SW-Lane arbeitet nur auf Basis des Handoff-Vertrags und der SW-Requirements-Objekte.

Operative Detailregeln (Gate, Statusmaschine, SLA, Eskalation, Abnahme):
- [HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md](HANDOFF_CONTRACT_TRADING_TO_SOFTWARE.md)

---

## 6. Abschluss in der SW-Lane

Die normative Definition of Done liegt im Handoff-Contract.
Die SW-Lane liefert die Nachweise (Issue/PR/Review/Tests und erforderliche Goals/State-Updates) in den Handoff-Lifecycle.

---

## 7. Verbindlicher Inhaltsstandard fuer Requirements-Katalog und Requirements-State

Dieser Abschnitt definiert, was in den beiden Artefakten mindestens enthalten sein MUSS, damit sie aussagekraeftig sind.

### 7.1 Pflichtinhalt Requirements-Katalog

- MUSS einen Feature-Katalog mit stabilen IDs enthalten (`F-...`).
- MUSS je Feature Unterfunktionen mit stabilen IDs enthalten (`SF-...`).
- MUSS je Feature funktionale Anforderungen mit stabilen IDs enthalten (`FR-...`).
- Funktionale Anforderungen MUESSEN im beobachtbaren Verhalten formuliert sein (kein abstraktes Zielbild, kein Architektur-Blabla).
- Funktionale Anforderungen MUESSEN testbar und eindeutig sein.

### 7.2 Pflichtinhalt Requirements-State

- MUSS den aktuellen Umsetzungsstatus pro Feature-ID (`F-...`) enthalten.
- MUSS den Status je Unterfunktion (`SF-...`) und je Requirement (`FR-...`) enthalten.
- MUSS zulaessige Statuswerte explizit festlegen und verwenden (z. B. `not-started | in-progress | implemented | verified`).
- MUSS Nachweisfelder pro Feature enthalten (mindestens Issue/PR/Test-Referenz oder explizit `none`).

### 7.3 Konsistenzregeln zwischen Goals und State

- Jede `F-...`, `SF-...` und `FR-...` ID aus dem Requirements-Katalog MUSS im Requirements-State vorkommen.
- Der Requirements-State darf keine ID fuehren, die im Requirements-Katalog nicht existiert.
- Aenderungen am Feature-/Requirement-Katalog erfordern im selben Aenderungslauf ein konsistentes Update des Requirements-State.

### 7.4 Unzulaessige Inhalte

- Unstrukturierte Wunschlisten ohne IDs.
- Reine Strategie- oder Governance-Texte ohne konkrete funktionale Anforderungen.
- Statustexte ohne Bezug auf Feature-/Requirement-IDs.

---

## 8. Verbindlicher Git-Workflow

### 8.1 Branch-Modell

1. Der Default-Branch pro Repo ist `main` und ist als Protected Branch zu fuehren.
2. Direkte Pushes auf `main` sind unzulaessig.
3. Jede Umsetzung erfolgt auf einem dedizierten Arbeitsbranch mit genau einem klaren Scope (ein Handoff/eine Capability).
4. Branch-Namensschema:
- `feature/<handoff-id>-<kurzname>`
- `fix/<handoff-id>-<kurzname>`
- `hotfix/<incident-id>-<kurzname>`

### 8.2 Commit- und PR-Konvention

1. Jeder PR MUSS Issue-Referenz, Handoff-ID und Capability-ID enthalten.
2. Der PR-Titel MUSS im Format `<handoff-id> <capability-id> <kurztitel>` vorliegen.
3. Die PR-Beschreibung MUSS enthalten:
- Scope und Out-of-Scope
- `goals_ref` und `state_ref`
- Mapping von Acceptance Criteria auf Tests/Checks
- Links auf Issue, CI-Lauf und Review
4. Commits MUESSEN nachvollziehbar und klein genug fuer gezielte Reviews sein.

### 8.3 Merge-Gate (verbindlich)

Merge in `main` ist nur erlaubt, wenn alle folgenden Punkte erfuellt sind:
- alle als verpflichtend markierten CI-Checks des Repos sind erfolgreich,
- ein explizites `Approve` durch `sw-reviewer` liegt vor,
- alle als required markierten Review-Punkte sind aufgeloest,
- `goals_ref` und `state_ref` sind aufloesbar und konsistent,
- Testnachweise sind im PR verlinkt.

### 8.4 Merge-Strategie

1. Standard ist `squash merge` nach bestandenem Merge-Gate.
2. Abweichungen (z. B. `merge commit`) sind nur zulaessig, wenn der Repo-Standard dies explizit fordert.
3. Nach Merge aktualisiert `sw-techlead` bei Bedarf Requirements-Katalog/State und fuehrt die Freischaltung `planned -> available` ausschliesslich ueber `nexusctl capabilities set-status` aus.

### 8.5 Hotfix-Pfad

1. Hotfixes laufen ausschliesslich ueber `hotfix/*` Branch + PR.
2. Fast-Track ist nur bei aktivem Incident zulaessig; Mindestgate bleibt:
- explizites Review durch `sw-reviewer`,
- erfolgreiche kritische CI-Checks (mindestens Build und Tests).
3. Innerhalb von 1 Business Day nach Merge ist ein Nachtrag mit Ursachenhinweis, Risikoabschaetzung und Folgeaufgaben verpflichtend.

## 9. Ticket-/PR-Automation ueber `nexusctl` (Phase 2 Zielbild)

1. GitHub bleibt System of Record fuer Umsetzungsevidenz (Issue/PR/Review/CI).
2. Die Handoff->Issue-Koordination liegt in der `nexus`-Agent-Lane.
3. `nexusctl` bleibt fuer Capability-/Handoff-State und Linkage-Persistenz zustaendig, ohne automatische Issue-Erstellung.
4. Eine vollstaendige Ticket-/PR-Steuerung als direkter `nexusctl`-Automatismus bleibt optionales Phase-2-Zielbild.
