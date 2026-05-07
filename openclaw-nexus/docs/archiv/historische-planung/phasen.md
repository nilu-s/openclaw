# Verbesserungsphasen: OpenClaw Nexus

Statusdatei: lebend  
Letzte Aktualisierung: 2026-05-05  
Aktuelle Phase: **abgeschlossen – architecture-hardening-v1**  
Historie: Der alte Greenfield-Phasenplan liegt unter `docs/archiv/phasen/legacy-greenfield-phases-v1.md`. Die abgeschlossenen Verbesserungsphasen VP-00 bis VP-12 liegen unter `docs/archiv/phasen/architecture-hardening-vp00-vp12.md`.

## Arbeitsregel

Jede Phase ist auf ungefähr 4 Stunden Arbeit für einen erfahrenen Entwickler ausgelegt. Jede Phase muss klein genug sein, um in einem separaten Chat oder Entwicklungszyklus vollständig umgesetzt, getestet und wieder als ZIP geliefert zu werden.

Die Phasendatei ist die einzige lebende Fortschrittsdatei. `README.md` und `endzustand.md` bleiben stabil. Alte abgeschlossene Detailpläne werden nach Abschluss größerer Meilensteine unter `docs/archiv/phasen/` archiviert.

## Fortschritt

| Phase | Status | Ziel | Ergebnis |
|---|---|---|---|
| VP-00 | abgeschlossen | Dokumentationsbasis, Konzeptanker, neue Phasenplanung | `README.md`, `endzustand.md`, `phasen.md`, Archiv für alten Plan |
| VP-01 | abgeschlossen | CLI-Kommandoschnitt vorbereiten und entkoppeln | Runtime-/Output-Helfer und Command-Modul-Signaturen vorbereitet |
| VP-02 | abgeschlossen | CLI-Domain-Kommandos aus `main.py` auslagern | Command-Module für me, domains, goals, schedules, generate und doctor aktiviert |
| VP-03 | abgeschlossen | Zentrale CommandRuntime / Unit of Work einführen | CommandRuntime arbeitet als Unit of Work mit Service-Factories und Rollback-Schutz |
| VP-04 | abgeschlossen | Repository-Schicht für Goals und Feature Requests konsequent nutzen | GoalService und FeatureRequestService nutzen Repository-Methoden statt direktem SQL |
| VP-05 | abgeschlossen | Repository-Schicht für Work, Patches, Reviews, Acceptance und Merge erweitern | RepositoryContext erweitert; Work/Patch/Review/Acceptance/Merge/Policy-Check-Pfade nutzen dedizierte Repositories |
| VP-06 | abgeschlossen | HTTP/CLI-Parität entwerfen und ersten API-Client einführen | API-Client eingeführt; `me` läuft optional remote gegen `/auth/me`, lokaler Modus bleibt Default |
| VP-07 | abgeschlossen | HTTP-Endpunkte erweitern und CLI optional remote-fähig machen | HTTP-Routen und optionale Remote-CLI-Pfade für Feature Requests, Work, Policy, Review und Acceptance ergänzt |
| VP-08 | abgeschlossen | Operational Hardening aus der Referenz übernehmen | HTTP-Operational-Hardening mit sicheren Defaults, Body-Limit, zentralen Timeouts/Read-Retries und SessionStore umgesetzt |
| VP-09 | abgeschlossen | GitHub-Adapter aus der Referenz härten | GitHub-URL-Parser, externe Review-/Check-State-Derivation, Changed-Files-Policy-Helfer und MockGitHubClient-Abdeckung ergänzt |
| VP-10 | abgeschlossen | Runtime-Tools und importierte Review-Items bereinigen | Legacy-Runtime-Tool-Review-Items entschieden, `runtime.tool.invoke` eingeführt und Guardrail-Tests ergänzt |
| VP-11 | abgeschlossen | Teststrategie beschleunigen und blockierende Tests isolieren | Schnelle Testmarker und isolierte blockierende Tests ergänzt |
| VP-12 | abgeschlossen | Doctor-, Audit- und Drift-Reports verbessern | Doctor-Report liefert Statuscodes, handlungsorientierte Drift-Erklärungen, offene Alerts, GitHub-Projektionsstatus und Audit-Chain-Übersicht |
| VP-13 | abgeschlossen | Abschlussreview und Architektur-Kontrakte stabilisieren | Architektur-Kontrakt-Tests ergänzt, CLI-Storage-Kopplung weiter reduziert, Generated-Artefakt-Regeln geprüft und alte Details archiviert |

---

## Archivierte Detailabschnitte

Die Detailabschnitte der abgeschlossenen Phasen VP-00 bis VP-12 wurden im Rahmen von VP-13 nach `docs/archiv/phasen/architecture-hardening-vp00-vp12.md` verschoben. `phasen.md` bleibt dadurch wieder eine schlanke Fortschritts- und Steuerungsdatei.

---

## VP-13 – Abschlussreview und Architektur-Kontrakte stabilisieren

Status: abgeschlossen  
Aufwand: erledigt im aktuellen Planungspaket

### Ziel

Nach den Refactoring-Phasen die Architektur stabilisieren und Regressionen gegen das Zielbild absichern.

### Umsetzung

- Architektur-Kontrakt-Tests wurden in `tests/test_architecture_contracts.py` ergänzt.
- Der CLI-Einstieg `nexusctl/src/nexusctl/interfaces/cli/main.py` importiert keine konkreten SQLite-Storage-Module mehr und delegiert den Datenbank-Bootstrap an die Runtime-Kompositionsschicht.
- `nexusctl/src/nexusctl/interfaces/cli/runtime.py` kapselt die lokale Datenbankinitialisierung über `initialize_database(args)` inklusive stabiler JSON-Payload-Struktur für `db init`.
- Ein Interface-Kontrakt begrenzt direkte `nexusctl.storage.sqlite`-Imports auf explizite Kompositionswurzeln (`cli/runtime.py`, `http/routes.py`, `http/server.py`).
- Ein Generated-Artefakt-Kontrakt prüft, dass alle erwarteten Runtime-Artefakte durch den Doctor-Check abgedeckt sind und driftfrei bleiben.
- Die abgeschlossenen Detailabschnitte VP-00 bis VP-12 wurden archiviert nach `docs/archiv/phasen/architecture-hardening-vp00-vp12.md`.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_architecture_contracts.py` → 4 bestanden.

### Akzeptanzkriterien

- Architekturgrenzen sind testbar.
- `main.py` bleibt Router/Bootstrap und enthält keine konkrete SQLite-Storage-Kopplung mehr.
- Refactoring ist abgeschlossen, ohne die Phase-20-Invarianten zu schwächen.

### Geänderte Dateien

- `nexusctl/src/nexusctl/interfaces/cli/runtime.py`
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `tests/test_architecture_contracts.py`
- `docs/archiv/phasen/architecture-hardening-vp00-vp12.md`
- `phasen.md`
- `PROJECT_STATE.json`
