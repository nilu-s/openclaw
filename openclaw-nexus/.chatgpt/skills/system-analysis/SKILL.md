---
name: system-analysis
description: Analysiert und bewertet OpenClaw Nexus als Gesamtsystem über Produktzweck, Architektur, Sicherheits-/Authority-Modell, Codequalität, Tests, Betrieb, Dokumentation, Risiken und nächste Verbesserungen. Verwenden, wenn der Nutzer eine Gesamtanalyse, Systembewertung, Architekturreview, Reifegradbewertung, Qualitätsbewertung, Risikoanalyse oder ein Scorecard-/Audit-Ergebnis für das ganze System möchte.
metadata:
  project: openclaw-nexus
  version: "1.0"
---

# System Analysis Skill

Dieser Skill analysiert OpenClaw Nexus als Gesamtsystem und bewertet seine Reife. Er ist breiter als `drift`, `legacy`, `leverage` und `concept-refinement`: Er betrachtet Produktlogik, Architektur, Authority-Modell, Implementierung, Tests, Betrieb, Dokumentation, Risiken und Verbesserungsprioritäten in einem zusammenhängenden Review.

## 1. Aktivierung

Aktiviere diesen Skill bei Aufträgen wie:

- „Analysiere das ganze System."
- „Bewerte das System."
- „Mach einen System-Review."
- „Wie gut ist OpenClaw Nexus insgesamt?"
- „Erstelle eine Reifegradbewertung."
- „Bewerte Architektur, Code, Tests und Betrieb."
- „Finde Schwachstellen im Gesamtsystem."
- „Gib mir eine Scorecard für das Projekt."
- „Was ist gut, was ist riskant, was fehlt?"

Nicht aktivieren, wenn der Nutzer nur ein Konzept schärfen möchte; dafür `concept-refinement` verwenden. Nicht aktivieren, wenn nur Konsistenz zwischen Status und Realität geprüft werden soll; dafür `drift` verwenden. Nicht aktivieren, wenn nur Altlasten gesucht werden; dafür `legacy` verwenden. Nicht aktivieren, wenn genau ein nächster Production-Readiness-Hebel gesucht wird; dafür `leverage` verwenden.

## 2. Kernvertrag

1. Der Skill liefert eine systemweite Analyse und Bewertung, keine verdeckte Implementierung.
2. Bewertungen müssen belegbar aus Repository, aktiver Dokumentation, Tests, Konfiguration und ChatGPT-State abgeleitet werden.
3. Die Analyse muss Stärken, Schwächen, Risiken, Reifegrad und konkrete nächste Schritte trennen.
4. Die Bewertung darf nicht nur generische Best Practices aufzählen; sie muss OpenClaw-Nexus-spezifisch sein.
5. Archivinhalte sind historische Referenz, aber keine aktive Wahrheit.
6. Wenn nicht alles geprüft werden kann, muss der Prüfumfang explizit begrenzt werden.
7. Score-Werte sind begründete Heuristiken, keine objektiven Messwerte.

## 3. Quellenpriorität

Prüfe abhängig vom Auftrag mindestens diese Quellen:

| Priorität | Quelle | Zweck |
| --- | --- | --- |
| 1 | `README.md` | Öffentliches Produktbild, Bedienmodell und Scope. |
| 2 | `.chatgpt/state/CURRENT_STATE.md` | Zuletzt geprüfter Zustand, bekannte Grenzen und nächste Arbeiten. |
| 3 | `nexus/*.yml` | Domänen, Agenten, Capabilities, Policies, Runtime-Tools und Systemverträge. |
| 4 | `nexusctl/src/nexusctl/**` | Tatsächliche Architektur, Services, Interfaces, Storage, Adapter und Authz. |
| 5 | `tests/**` und `pytest.ini` | Abgesicherte Verträge, Teststrategie, Marker und Risikobereiche. |
| 6 | `scripts/*` | Validierung, Packaging, Sprint-/Betriebshilfen und Reproduzierbarkeit. |
| 7 | `config/*` | Docker, ENV, Runtime- und Deployment-Annahmen. |
| 8 | `docs/**` ohne Archiv | Aktive Produkt-, Architektur- und Betriebsdokumentation. |
| 9 | `.chatgpt/skills/*` | Agentenarbeitsweise und wiederholbare Review-/Sprintlogik. |
| 10 | `docs/archiv/**` | Nur historische Referenz bei unklarer Entwicklungslinie. |

Wenn die Zeit begrenzt ist, lies zuerst `README.md`, `CURRENT_STATE.md`, `nexus/policies.yml`, `nexus/runtime-tools.yml`, `pytest.ini`, `scripts/validate_project.py` und die Verzeichnisstruktur von `nexusctl/src/nexusctl`.

## 4. Bewertungsdimensionen

Bewerte das System in diesen Dimensionen:

| Dimension | Leitfrage |
| --- | --- |
| Produktklarheit | Ist klar, welches Problem das System löst, für wen, und was bewusst nicht Ziel ist? |
| Systemarchitektur | Sind Domänen, Services, Interfaces, Adapter, Storage und Generated-Artefakte sinnvoll getrennt? |
| Authority & Sicherheit | Sind Agentenrechte, GitHub-Grenzen, Authz, Secrets und gefährliche Operationen kontrolliert? |
| Datenintegrität | Sind Event Store, SQLite, Migrationen, Append-only-Regeln, Backups und Recovery belastbar? |
| Runtime & Betrieb | Sind CLI, HTTP, Docker, Doctor, Deployment, Readiness und Recovery praktisch betreibbar? |
| Testabdeckung | Sichern Tests die zentralen Produkt-, Policy-, Architektur- und Betriebsverträge? |
| Codequalität | Sind Module verständlich, kohäsiv, wartbar und nicht unnötig gekoppelt? |
| Dokumentation | Beschreibt aktive Doku den tatsächlichen Zustand und die Betriebsgrenzen verständlich? |
| Erweiterbarkeit | Können neue Agenten, Tools, Policies, Webhooks oder Flows kontrolliert ergänzt werden? |
| Risiko & Reife | Welche Risiken blockieren internen Produktionsbetrieb oder sichere Weiterentwicklung? |

## 5. Bewertungsheuristik

Nutze eine 0-5-Skala pro Dimension:

| Score | Bedeutung |
| --- | --- |
| 0 | Nicht vorhanden oder nicht bewertbar. |
| 1 | Fragmentarisch; hohes Risiko oder nur Absicht. |
| 2 | Teilweise vorhanden; zentrale Lücken oder unklare Verträge. |
| 3 | Solide Basis; mehrere bekannte Grenzen. |
| 4 | Stark und größtenteils belegt; begrenzte produktionsrelevante Lücken. |
| 5 | Sehr stark, nachweisbar, wartbar und betrieblich belastbar. |

Gesamturteil:

- `rot`: zentrale Produkt-, Authority-, Datenintegritäts- oder Betriebsrisiken sind unkontrolliert.
- `gelb`: solide Basis, aber relevante Lücken verhindern bedenkenlosen Betrieb.
- `grün`: konsistente, gut abgesicherte und betrieblich belastbare Systembasis mit nur begrenzten Restarbeiten.

## 6. Vorgehen

1. Formuliere den Analyseanker: gesamtes System, bestimmter Reifegrad, Architekturreview oder Audit-Frage.
2. Erstelle eine knappe Systemkarte: Zweck, Hauptkomponenten, Daten-/Authority-Fluss, Betreibergrenzen.
3. Prüfe die Quellen nach Priorität und notiere konkrete Belege: Dateien, Module, Tests, Policies, Scripts, Konfigurationswerte.
4. Bewerte jede Dimension mit Score und kurzer Begründung.
5. Trenne Stärken, Schwächen, Risiken und offene Fragen.
6. Unterscheide zwischen:
   - `bestätigt`: direkt in Code, Tests, Konfiguration oder aktiver Doku belegt.
   - `plausibel`: aus Struktur ableitbar, aber nicht vollständig geprüft.
   - `offen`: nicht geprüft oder widersprüchlich.
7. Leite 3 bis 7 konkrete Verbesserungen ab und sortiere sie nach Wirkung.
8. Empfiehl bei Bedarf, welcher Spezial-Skill als nächstes genutzt werden sollte.

## 7. Analysefokus für OpenClaw Nexus

Achte besonders auf diese systemspezifischen Fragen:

- Ist GitHub nur Projektion und nicht Authority?
- Sind Agentenrechte domain- und capability-basiert kontrolliert?
- Sind direkte gefährliche Writes verhindert oder klar über `nexusctl` geführt?
- Sind Generated-Artefakte aus aktiven YAML-Verträgen ableitbar und testbar?
- Ist der Event Store append-only und manipulationserschwerend?
- Sind Backup, Restore, Restore-Drill und Evidence-Pack praktisch verifizierbar?
- Sind HTTP-API, CLI und Services konsistent?
- Sind Webhooks, Reconciliation und Driftfälle robust genug modelliert?
- Sind Timeout-Risiko-Tests bewusst isoliert statt unbemerkt kaputt?
- Sind Docker-/Deployment-/ENV-Annahmen als Betreiberpflichten sichtbar?
- Gibt es übergroße Module oder Service-Kopplung, die Wartbarkeit gefährden?
- Gibt es Widersprüche zwischen README, CURRENT_STATE, Policies, Tests und Code?

## 8. Ergebnisformat

Verwende dieses Format:

```markdown
## Systemanalyse

### Gesamturteil
- Status: grün / gelb / rot
- Reifegrad: .../5
- Kurzfazit: ...
- Prüfumfang: ...

### Systemkarte
- Zweck: ...
- Zentrale Komponenten: ...
- Authority-Fluss: ...
- Betriebsgrenzen: ...

### Scorecard
| Dimension | Score | Bewertung | Belege |
| --- | ---: | --- | --- |

### Stärken
- ...

### Schwächen und Risiken
| Bereich | Beobachtung | Risiko | Schwere |
| --- | --- | --- | --- |

### Priorisierte Verbesserungen
| Rang | Verbesserung | Wirkung | Validierung |
| ---: | --- | --- | --- |

### Offene Fragen
- ...

### Empfohlener nächster Skill
- `concept-refinement` / `drift` / `legacy` / `leverage` / `sprint-workflow`: ...
```

## 9. Bewertungsregeln

- Nenne konkrete Dateipfade, Modulnamen, Tests oder Konfigurationsdateien, wenn du eine Bewertung begründest.
- Vermische nicht „nicht geprüft" mit „nicht vorhanden".
- Gute Testanzahl ersetzt keine Bewertung der Testrelevanz.
- Eine starke Doku ersetzt keine Implementierung; eine Implementierung ohne Doku ist betrieblich nur teilweise reif.
- Betriebsreife erfordert sichtbare Fehlerzustände, Recovery-Wege und sichere Grenzen, nicht nur funktionierende Happy Paths.
- Kritisiere keine historisch archivierten Ansätze, solange sie nicht in aktive Pfade leaken.
- Wenn du Scores vergibst, erkläre die wichtigsten Abzüge.

## 10. Zusammenspiel mit anderen Skills

- Nutze `concept-refinement`, wenn die Analyse zeigt, dass Produktzweck, Scope oder Nicht-Ziele unscharf sind.
- Nutze `drift`, wenn die Analyse widersprüchliche Wahrheiten zwischen Status, Code, Tests und Doku findet.
- Nutze `legacy`, wenn Schwächen aus alten Ansätzen, totem Code oder doppelten Implementierungen stammen könnten.
- Nutze `leverage`, wenn aus der Analyse genau ein wichtigster Production-Readiness-Hebel priorisiert werden soll.
- Nutze `sprint-workflow`, wenn eine priorisierte Verbesserung geplant, umgesetzt oder abgeschlossen werden soll.
