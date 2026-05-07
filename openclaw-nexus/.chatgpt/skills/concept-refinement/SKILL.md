---
name: concept-refinement
description: Verfeinert das OpenClaw-Nexus-Konzept kontrolliert von grober Idee zu präzisem Produkt-, Architektur- und Sprint-fähigem Zielbild. Verwenden, wenn der Nutzer das Konzept schärfen, Zielbild, Scope, Begriffe, Systemgrenzen, Risiken, Nicht-Ziele, Akzeptanzkriterien oder eine umsetzbare Konzeptvariante ausarbeiten möchte.
metadata:
  project: openclaw-nexus
  version: "1.0"
---

# Concept Refinement Skill

Dieser Skill verfeinert das OpenClaw-Nexus-Konzept, ohne direkt Implementierung oder Sprintausführung zu starten. Er übersetzt unscharfe Ideen in ein prüfbares Zielbild, klare Systemgrenzen, belastbare Begriffe, Nicht-Ziele, Risiken, Akzeptanzkriterien und eine umsetzbare nächste Konzeptentscheidung.

## 1. Aktivierung

Aktiviere diesen Skill bei Aufträgen wie:

- „Verfeinere das Konzept."
- „Schärfe das Zielbild."
- „Mach aus der Idee ein klares Konzept."
- „Was fehlt dem Konzept noch?"
- „Prüfe, ob das Konzept rund ist."
- „Formuliere Scope und Nicht-Ziele."
- „Arbeite eine bessere Produktlogik aus."
- „Leite daraus einen Sprint-fähigen Plan ab."

Nicht aktivieren, wenn der Nutzer ausdrücklich die nächste Sprint-Phase ausführen oder einen Sprint abschließen will; dafür `sprint-workflow` verwenden. Nicht aktivieren, wenn nur Drift, Legacy oder Production-Leverage gesucht wird; dafür `drift`, `legacy` oder `leverage` verwenden.

## 2. Kernvertrag

1. Der Skill liefert Konzeptschärfung, keine verdeckte Implementierung.
2. Das Ergebnis muss als Produkt- oder Architekturentscheidung nutzbar sein.
3. Jede Empfehlung muss aus dem aktuellen Projektzustand, aktiver Dokumentation und vorhandenen Grenzen abgeleitet werden.
4. Das Konzept darf keine neue Source of Truth einführen, die `nexusctl`, Control Config, Control Store oder generierte Runtime-Artefakte umgeht.
5. Altversionen, archivierte Ansätze und historische Agent-Setups sind nur Inspirations- oder Vergleichsmaterial, nicht automatisch aktiver Produktvertrag.
6. Wenn ein Konzeptpunkt zu groß ist, wird er in eine klare Zielvariante und Folgefragen zerlegt, statt als vager Großumbau stehen zu bleiben.
7. Am Ende muss eine konkrete nächste Entscheidung oder ein konkretes nächstes Arbeitspaket benannt werden.

## 3. Quellenpriorität

Prüfe je nach Auftrag:

| Priorität | Quelle | Zweck |
| --- | --- | --- |
| 1 | `docs/product/overview.md` | Produktumfang, Zielarchitektur, Sprachvertrag und Leitprinzipien. |
| 2 | `.chatgpt/state/CURRENT_STATE.md` | Geprüfter Ist-Zustand, bekannte Grenzen und empfohlene nächste Arbeiten. |
| 3 | `.chatgpt/state/phases.md` | Laufender Sprint-Kontext, falls aktiv. |
| 4 | `README.md` und `.chatgpt/README.md` | Einstieg, Skill-Landschaft und aktive Arbeitsregeln. |
| 5 | `docs/operations/*` | Betriebskonzept, Deployment, Recovery und interne Produktionsannahmen. |
| 6 | `nexus/*.yml` und `generated/*` | Kontrollkonfiguration, Runtime-Ableitung, Policies, Schedules und Agentenmodell. |
| 7 | Code, Tests und Scripts | Tatsächliche Umsetzbarkeit, Validierbarkeit und bestehende Produktverträge. |
| 8 | `docs/archiv/*` | Historie nur zur Einordnung; nicht als aktive Wahrheit übernehmen. |

## 4. Konzeptdimensionen

Bewerte das Konzept entlang dieser Dimensionen:

| Dimension | Leitfrage |
| --- | --- |
| Zielnutzen | Welches Betreiber-, Entwickler- oder Governance-Problem wird konkret gelöst? |
| Scope | Was gehört eindeutig hinein, was bewusst nicht? |
| Authority | Welche Komponente entscheidet, schreibt oder generiert welche Zustände? |
| Datenfluss | Wie bewegen sich Idee, Request, Proposal, Review, Acceptance, Merge und Runtime-Artefakt durch das System? |
| Kontrollgrenzen | Wo dürfen Agents handeln, und wo müssen sie über `nexusctl` gehen? |
| Begriffe | Sind Namen, Rollen und Verantwortlichkeiten eindeutig und produktionsneutral? |
| Nachweisbarkeit | Welche Tests, Reports, Events oder Artefakte beweisen das Konzept? |
| Betriebsreife | Welche Fehler-, Recovery-, Audit- oder Sicherheitsfragen bleiben offen? |
| Anschlussfähigkeit | Kann daraus ein Sprint, eine Dokuänderung, ein Testvertrag oder ein Implementierungsschritt entstehen? |

## 5. Vorgehen

1. Den Nutzerauftrag in eine Konzeptfrage übersetzen: Produktlogik, Architekturgrenze, Bedienmodell, Betriebsmodell, Agentenmodell oder Validierungsmodell.
2. Aktive Quellen lesen, bevor neue Begriffe oder Zielzustände formuliert werden.
3. Den aktuellen Kern des Konzepts in 3 bis 7 Sätzen zusammenfassen.
4. Unschärfen sammeln: offene Begriffe, widersprüchliche Verantwortlichkeiten, fehlende Nachweise, zu große Scope-Blöcke, implizite Annahmen.
5. Eine verfeinerte Zielvariante formulieren, die zur aktuellen Zielarchitektur passt.
6. Nicht-Ziele und Abgrenzungen ausdrücklich benennen.
7. Akzeptanzkriterien definieren, mit denen das verfeinerte Konzept später überprüft werden kann.
8. Eine konkrete nächste Entscheidung oder ein Sprint-fähiges Arbeitspaket ableiten.
9. Wenn mehrere Varianten möglich sind, maximal drei Varianten vergleichen und eine bevorzugte Variante empfehlen.

## 6. Leitplanken für OpenClaw Nexus

Bei jeder Verfeinerung gelten diese Projektregeln:

- `nexusctl` bleibt autoritative Control-Software für Lifecycle-State.
- GitHub bleibt Projektions- und Kollaborationsfläche, nicht Lifecycle-Authority.
- OpenClaw Runtime konsumiert generierte Konfiguration, ist aber keine eigene Authority für Control-State.
- Agents dürfen Requests, Proposals, erlaubte Runs und delegierte Arbeit erzeugen; direkte Mutationen autoritativer Flächen sind nicht Zielbild.
- Control Config in `nexus/*.yml` ist designseitiger Soll-Zustand; `generated/*` ist abgeleitet.
- Jede fachliche Mutation braucht Nachvollziehbarkeit über Events, Prüfungen oder Reports.
- Neue Konzepte müssen mit Tests, Validatoren, Doctor-/Audit-Reports oder Dokumentationsverträgen prüfbar werden.

## 7. Typische Verfeinerungsfragen

Nutze diese Fragen, wenn das Konzept noch zu grob ist:

- Wer ist der primäre Nutzer: Betreiber, Entwickler, Agent, Reviewer oder Business-Acceptor?
- Welche Entscheidung wird durch das Konzept sicherer, schneller oder nachvollziehbarer?
- Welcher Zustand ist autoritativ, welcher nur Projektion oder Ableitung?
- Welche Fehlbedienung soll unmöglich, sichtbar oder reversibel werden?
- Welche minimalen Artefakte beweisen, dass das Konzept umgesetzt ist?
- Welche alten Annahmen dürfen explizit wegfallen?
- Was ist der kleinste sinnvolle nächste Schritt, der das Konzept realer macht?

## 8. Ergebnisformat

Verwende dieses Format:

```markdown
## Konzeptverfeinerung

### Kurzfazit
- ...

### Geschärftes Zielbild
- ...

### Präzisierter Scope
| Gehört dazu | Gehört nicht dazu |
| --- | --- |
| ... | ... |

### Authority- und Datenfluss
- ...

### Offene Unschärfen
| Punkt | Warum relevant | Vorschlag |
| --- | --- | --- |
| ... | ... | ... |

### Empfohlene Konzeptvariante
- Variante: ...
- Begründung: ...

### Akzeptanzkriterien
- ...

### Nächste Entscheidung oder nächstes Arbeitspaket
- ...

### Empfohlene Validierung
- ...
```

Wenn der Auftrag sehr klein ist, darf das Format gekürzt werden, aber Kurzfazit, geschärftes Zielbild, Nicht-Ziele, Akzeptanzkriterien und nächster Schritt müssen enthalten bleiben.

## 9. Zusammenspiel mit anderen Skills

- Nutze `drift`, wenn unklar ist, ob Dokumentation, State und Code noch zusammenpassen.
- Nutze `legacy`, wenn die Verfeinerung vor allem alte Begriffe, tote Ansätze oder Archiv-Leaks entfernen soll.
- Nutze `leverage`, wenn nach der Konzeptschärfung der wichtigste Produktionsreife-Hebel priorisiert werden soll.
- Nutze `sprint-workflow`, wenn aus dem verfeinerten Konzept ein Sprint geplant, ausgeführt oder abgeschlossen werden soll.
