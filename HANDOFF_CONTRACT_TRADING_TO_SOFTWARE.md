# OpenClaw - Handoff Contract Trading -> Software
Version: 2.2
Date: 2026-04-27
Status: Verbindlich

---

## 1. Zweck und Scope

Dieses Dokument definiert den operativen Standardvertrag fuer den Domain-Uebergang von Trading zur Software-Lane.
Es ist die Detailnorm fuer:
- Feldschema und Validierung
- Rollen, Entscheidungen und Verantwortlichkeiten
- Lifecycle/Statusuebergaenge
- SLA und Eskalation
- Abnahme und Abschluss

Nicht im Scope:
- Trading-Strategieentscheidungen
- technische Implementierungsdetails einzelner Software-Repos

---

## 2. Contract Artefakte

### 2.1 Primarobjekt: `handoff_request`

Ein Handoff ist ein eindeutiges Objekt mit stabiler ID (z. B. `HC-2026-0001`).
- Capability-Preflight vor Handoff-Entscheidungen ist verpflichtend; die normative CLI-Regel liegt in [NEXUSCTL_FUNCTIONS.md](NEXUSCTL_FUNCTIONS.md).
- Die Trading-Lane nutzt fuer diesen Preflight primaer `nexusctl context`; kompatibel bleiben `auth` + `capabilities list/show`.
- Die Trading-Lane darf auf Basis dieser CLI-Informationen Capability-Bedarf vorschlagen; finale Einreichungsentscheidung bleibt bei `trading-strategist`.
Eine vollstaendige Handoff-Steuerung per `nexusctl` ist Phase-2-Zielbild.

Pflichtfelder bei Einreichung durch Trading:
- `objective`
- `missing_capability`
- `business_impact`
- `expected_behavior`
- `acceptance_criteria`
- `risk_class`
- `priority`
- `trading_goals_ref`

Pflichtfelder nach SW-Triage:
- `goals_ref` (optional in nexusctl, kann in Issue abgebildet werden)
- `state_ref` (optional in nexusctl, kann in Issue abgebildet werden)

### 2.2 Referenzen

- `trading_goals_ref` zeigt auf das externe Trading-Goal-System.
- `goals_ref` zeigt auf eine Feature-ID im SW-Requirements-Katalog (z. B. `feature://F-001`).
- `state_ref` zeigt auf die zugehoerige State-ID im SW-Requirements-State (z. B. `state://F-001`).

Regel:
- `goals_ref` und `state_ref` sollten gesetzt oder im Issue verlinkt sein, blockieren aber den Build-Start NICHT hart, falls sie in nexusctl `null` sind.

### 2.3 Aufloesbarkeit von `goals_ref` und `state_ref` (normativ)

- `goals_ref` MUSS auf eine existierende Feature-ID im Requirements-Katalog zeigen.
- `state_ref` MUSS auf eine existierende State-ID im Requirements-State zeigen.
- Nicht aufloesbare oder nicht existente Referenzanker sind `reference-not-resolvable`.

---

## 3. Feldschema und Validierungsregeln

### 3.1 Formatregeln (Gate-Check durch `nexus`)

- `objective`: ein klarer Zielzustand in 1-3 Saetzen.
- `missing_capability`: konkret, keine Loesungsvorgabe, keine Trading-Strategie.
- `business_impact`: messbarer Effekt (z. B. Risiko, Latenz, Kosten, PnL-relevanter Hebel).
- `expected_behavior`: beobachtbares Sollverhalten.
- `acceptance_criteria`: testbar, atomar, eindeutig als Liste.
- `risk_class`: nur `low|medium|high|critical`.
- `priority`: nur `P0|P1|P2|P3`.
- `trading_goals_ref`: muss auf ein existierendes Ziel zeigen.

### 3.2 Semantikregeln (Triage durch `sw-architect`)

- `objective` und `acceptance_criteria` duerfen sich nicht widersprechen.
- `missing_capability` muss als Software-Arbeitspaket formulierbar sein.
- `expected_behavior` muss in verifizierbare Tests oder Checks ueberfuehrbar sein.
- Bei Unklarheit wird der Handoff mit Grund zurueckgegeben, nicht stillschweigend interpretiert.

### 3.3 Rueckweisungsgruende (standardisiert)

- `missing-required-fields`
- `invalid-risk-or-priority`
- `non-testable-acceptance-criteria`
- `not-a-software-capability-gap`
- `reference-not-resolvable`

---

## 4. Rollen und Entscheidungen je Phase

1. Trading-Erstellung
- `trading-analyst`, `trading-strategist`, `trading-sentinel`: Propose
- `trading-strategist`: finale Trading-Entscheidung zur Einreichung

2. Gate
- `nexus`: Execute/Decide (annehmen oder rueckweisen mit Grund)

3. SW-Triage und Planbarkeit
- `sw-architect`: Execute/Decide (Arbeitspakete, `goals_ref`, `state_ref`)
- `sw-techlead`: Propose bei Inkonsistenzen in Requirements-Katalog oder Requirements-State

4. Build und Review
- `sw-builder`: Execute/Decide fuer Implementierung im Scope
- `sw-reviewer`: Execute/Decide fuer Merge-Gate

5. Lifecycle-Abschluss
- `nexus`: Execute/Decide fuer formalen Abschluss
- `trading-strategist`: Execute/Decide fuer Adoption in der Trading-Lane

---

## 5. Lifecycle und Statusmaschine

### 5.1 Kanonische Handoff-Status

1. `draft` (nur Trading-intern)
2. `submitted` (an `nexus` uebergeben)
3. `gate-rejected` (zurueck an Trading mit Grund)
4. `accepted` (Gate bestanden)
5. `needs-planning` (SW-Triage offen)
6. `ready-to-build` (Planung abgeschlossen)
7. `in-build` (Umsetzung aktiv)
8. `in-review` (Review-Gate aktiv)
9. `review-failed` (zurueck an Build)
10. `state-update-needed` (Techlead-Update noetig)
11. `done` (Capability geliefert)
12. `adoption-pending` (Trading bewertet Nutzung)
13. `closed` (formal abgeschlossen)
14. `cancelled` (abgebrochen mit Grund)

### 5.2 Erlaubte Uebergaenge

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

Regel:
- Jeder Statuswechsel muss Zeitstempel, Verantwortlichen und Begruendung enthalten.

---

## 6. SLA und Reaktionszeiten

Zeiten gelten als Zielwerte in Business Hours.

- `P0` oder `critical`: Gate-Reaktion <= 30 min, SW-Triage-Start <= 4 h
- `P1` oder `high`: Gate-Reaktion <= 4 h, SW-Triage-Start <= 1 Business Day
- `P2` oder `medium`: Gate-Reaktion <= 1 Business Day, SW-Triage-Start <= 2 Business Days
- `P3` oder `low`: Gate-Reaktion <= 2 Business Days, SW-Triage-Start <= 5 Business Days

Regel:
- Wenn `priority` und `risk_class` unterschiedlich sind, gilt immer das strengere SLA.

---

## 7. Eskalation

1. Gate- oder Triage-SLA verpasst:
- Eskalation an `nexus` und `sw-techlead`.

2. Konflikt ueber Scope oder Verantwortlichkeit:
- gemeinsame Klaerung `nexus + sw-architect + trading-strategist`.

3. Kritischer Blocker ohne Einigung:
- Eskalation an `main` fuer finalen Entscheid.

4. Jede Eskalation muss enthalten:
- Blocker
- betroffene Ziele/Referenzen
- vorgeschlagene Optionen
- benoetigte Entscheidung bis Zeitpunkt X

---

## 8. Definition of Ready / Done / Adoption

### 8.1 Definition of Ready (vor Build)

Ein Handoff ist `ready-to-build`, wenn:
- Pflichtfelder gueltig sind
- Acceptance Criteria testbar heruntergebrochen sind
- Verantwortlicher Builder und Scope definiert sind

### 8.2 Definition of Done (SW-Lane)

Eine Capability ist `done`, wenn:
- Issue, PR, Review und Tests eindeutig verlinkt sind
- Review ein explizites Ergebnis hat
- der verbindliche Git-Workflow gemaess [SOFTWARE_DEVELOPMENT_SYSTEM.md](SOFTWARE_DEVELOPMENT_SYSTEM.md) (Abschnitt 8) eingehalten ist
- erforderliche Goals/State-Updates erfolgt sind
- Abweichungen zum Handoff dokumentiert sind

### 8.3 Adoption in Trading-Lane

Nach `done` entscheidet `trading-strategist`:
- `adopt` -> `closed`
- `adopt-later` -> `adoption-pending`
- `reopen-gap` -> neuer/aktualisierter Handoff mit Referenz auf Vorgaenger

---

## 9. Audit und Nachvollziehbarkeit

Mindest-Trace je Handoff:
- Handoff-ID
- Trading-Referenz (`trading_goals_ref`)
- SW-Referenzen (`goals_ref`, `state_ref`)
- Issue/PR/Review-Links
- Statushistorie mit Entscheider und Zeitpunkt
- Eskalationen und Entscheidungen

Regel:
- Ohne vollstaendige Traceability gilt der Lifecycle als nicht revisionssicher.

---

## 10. Normatives Beispiel

```yaml
handoff_id: HC-2026-0001
objective: "Reduce reaction latency for risk-limit breaches."
missing_capability: "Automatic hard-stop trigger when risk threshold is exceeded."
business_impact: "Prevents prolonged exposure during volatility spikes."
expected_behavior: "System halts new position entries within threshold breach window."
acceptance_criteria:
  - "Given threshold breach, new entries are blocked within 500ms."
  - "Event is logged with timestamp and breach metadata."
  - "Rollback path exists and is documented."
risk_class: high
priority: P1
trading_goals_ref: "trading-goal://risk/limit-hard-stop"
goals_ref: "feature://F-001"
state_ref: "state://F-001"
status: submitted
```
