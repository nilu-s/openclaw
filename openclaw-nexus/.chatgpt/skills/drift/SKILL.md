---
name: drift
description: Prüft den allgemeinen OpenClaw-Nexus-Projektstatus auf Drift zwischen Projektabsicht, dokumentiertem Zustand, tatsächlicher Umsetzung, Tests, Konfiguration, Scripts und aktiver Dokumentation. Verwenden, wenn der Nutzer fragt, ob das Projekt noch konsistent ist, ob CURRENT_STATE zur Realität passt, ob Zielbild und Code auseinanderlaufen, oder eine Drift-Prüfung/Kurskontrolle des Projektstatus möchte.
metadata:
  project: openclaw-nexus
  version: "1.0"
---

# Drift Skill

Dieser Skill prüft, ob OpenClaw Nexus als Projekt noch in sich konsistent ist. Er ist kein Sprint-Skill und kein Implementierungs-Skill. Er bewertet den allgemeinen Projektstatus gegen Projektabsicht, aktive Dokumentation, Code, Tests, Konfiguration und Scripts.

## 1. Aktivierung

Aktiviere diesen Skill bei Aufträgen wie:

- „Mach eine Drift-Prüfung."
- „Sind wir noch auf Kurs?"
- „Passt CURRENT_STATE noch zur Realität?"
- „Prüfe den Projektstatus auf Drift."
- „Weichen Zielbild, Doku und Code auseinander?"
- „Ist das, was gerade umgesetzt ist, noch das, was wir vorhaben?"

Nicht aktivieren, wenn der Nutzer nur eine konkrete Änderung implementieren, einen Sprint planen oder alte Dateien entfernen möchte. Für Altlasten den Skill `legacy` verwenden. Für Produktionsreife-Priorisierung den Skill `leverage` verwenden.

## 2. Kernvertrag

1. Der Skill prüft Konsistenz, führt aber keine Codeänderungen aus, außer der Nutzer verlangt ausdrücklich eine Korrektur.
2. Der Skill bewertet nicht primär Sprintziele, sondern den Projektstatus als Ganzes.
3. `.chatgpt/state/CURRENT_STATE.md` ist eine wichtige Statusquelle, aber nicht automatisch Wahrheit. Code, Tests und aktive Konfiguration können ihm widersprechen.
4. `.chatgpt/state/phases.md` darf als Kontext genutzt werden, ist aber nur maßgeblich, wenn ein aktiver Arbeitsstand geprüft werden soll.
5. `docs/archiv/` ist historische Referenz und niemals aktive Wahrheit.
6. Alte Versionen haben keinen Kompatibilitätsvorrang. Die aktuelle Zielversion zählt.

## 3. Quellenpriorität

Prüfe abhängig vom Auftrag mindestens diese Quellen:

| Priorität | Quelle | Zweck |
| --- | --- | --- |
| 1 | Aktiver Code | Tatsächliche Umsetzung und Schnittstellen. |
| 2 | Tests | Abgesichertes Verhalten und implizite Produktverträge. |
| 3 | Scripts | Validierung, Packaging, Betriebshilfen. |
| 4 | `nexus/*.yml` und `config/*` | Aktive Konfiguration und Runtime-Annahmen. |
| 5 | `README.md` und aktive Produkt-/Operations-Doku | Öffentliches Zielbild und Bedienmodell. |
| 6 | `.chatgpt/state/CURRENT_STATE.md` | Zuletzt geprüfter Projektstatus. |
| 7 | `.chatgpt/state/phases.md` | Aktiver Zwischenstand, falls vorhanden. |
| 8 | `docs/archiv/` | Nur historische Vergleichsquelle. |

Wenn die Zeit begrenzt ist, prüfe zuerst die Aussagen aus `CURRENT_STATE.md`, die konkrete technische Fähigkeiten, Grenzen, Tests oder nächste Arbeiten beschreiben.

## 4. Prüfdimensionen

Bewerte Drift in diesen Kategorien:

| Kategorie | Leitfrage |
| --- | --- |
| Intent Drift | Weicht die Umsetzung vom aktuellen Zielbild oder Produktzweck ab? |
| Status Drift | Behauptet `CURRENT_STATE.md` etwas, das Code, Tests oder Doku nicht stützen? |
| Documentation Drift | Beschreiben README oder aktive Doku ein anderes Verhalten als die Implementierung? |
| Test Drift | Sichern Tests noch den gewünschten Zielzustand oder nur historische Annahmen? |
| Config Drift | Passen Defaults, ENV-Variablen und Docker-/Runtime-Konfiguration zur Doku? |
| Architecture Drift | Entwickelt sich die Struktur anders als aktiv beschrieben oder abgesichert? |
| Scope Drift | Gibt es neue Konzepte, die weder dokumentiert noch entschieden sind? |
| Risk Drift | Werden bekannte Grenzen, Risiken oder Produktionsannahmen verharmlost? |

## 5. Vorgehen

1. Formuliere den Prüfanker: Welche Projektabsicht oder Statusaussage wird geprüft?
2. Lies die relevanten aktiven Quellen nach der Quellenpriorität.
3. Extrahiere konkrete Soll-Aussagen, keine vagen Interpretationen.
4. Vergleiche jede Soll-Aussage mit beobachtbaren Ist-Belegen aus Code, Tests, Doku oder Konfiguration.
5. Klassifiziere Befunde als:
   - `kein Drift`
   - `möglicher Drift`
   - `bestätigter Drift`
   - `nicht bewertet`
6. Trenne Befund und Empfehlung sauber.
7. Empfiehl Korrekturen dort, wo die Wahrheitsebene falsch ist:
   - Status/Doku korrigieren, wenn Code und Tests richtig sind.
   - Code/Tests korrigieren, wenn Zielbild und Doku richtig sind.
   - Entscheidung einholen, wenn Zielbild, Code und Doku widersprüchlich sind.

## 6. Bewertungsregeln

- Bevorzuge nachweisbare Befunde gegenüber Vermutungen.
- Nenne Dateipfade und konkrete Symbole, Tests oder Konfigurationswerte.
- Führe keine pauschale Kritik ohne Prüfschritt auf.
- Archivinhalte dürfen Drift erklären, aber nicht rechtfertigen.
- Wenn eine Aussage nur teilweise belegt ist, markiere sie als `möglicher Drift`, nicht als bestätigt.
- Wenn der Nutzer eine vollständige Prüfung erwartet, aber nur Teilbereiche geprüft wurden, kennzeichne den Umfang transparent.

## 7. Ergebnisformat

Verwende dieses Format:

```markdown
## Drift-Prüfung

### Ergebnis
- Status: grün / gelb / rot
- Kurzfazit: ...
- Prüfumfang: ...

### Konsistente Bereiche
- ...

### Möglicher Drift
| Bereich | Beobachtung | Risiko | Nächster Prüfschritt |
| --- | --- | --- | --- |

### Bestätigter Drift
| Bereich | Soll / Behauptung | Ist | Empfehlung |
| --- | --- | --- | --- |

### Empfohlene Korrekturen
- ...

### Offene Entscheidungen
- ...

### Nicht bewertet
- ...
```

Wenn kein Drift gefunden wird, schreibe ausdrücklich, welche Bereiche geprüft wurden und warum der Status grün ist.

## 8. Statusampel

- `grün`: Keine bestätigte Drift in den geprüften Bereichen; höchstens harmlose offene Prüfpunkte.
- `gelb`: Mögliche oder begrenzte Drift mit überschaubarem Risiko.
- `rot`: Bestätigte Drift in Projektstatus, Produktversprechen, Tests, Security-/Betriebsannahmen oder zentraler Architektur.

## 9. Zusammenspiel mit anderen Skills

- Nutze `legacy`, wenn Drift durch alte, tote oder doppelte Ansätze verursacht sein könnte.
- Nutze `leverage`, wenn nach der Drift-Prüfung entschieden werden soll, welcher nächste Produktionsreife-Hebel am wichtigsten ist.
- Nutze `sprint-workflow`, wenn aus den Empfehlungen ein umsetzbarer Änderungssprint geplant oder ausgeführt werden soll.
