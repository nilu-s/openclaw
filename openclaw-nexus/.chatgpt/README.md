# ChatGPT Workspace

Dieser Ordner enthält wiederverwendbare ChatGPT-/Agent-Skills und aktive Entwicklungszustände für die Weiterentwicklung von OpenClaw Nexus.

## Konvention

Skills liegen unter:

```text
.chatgpt/skills/<skill-name>/SKILL.md
```

Jeder Skill folgt dem Agent-Skills-Format:

- Der Ordnername entspricht dem `name` im YAML-Frontmatter.
- `SKILL.md` enthält mindestens `name` und `description`.
- Ausführungsanweisungen stehen im Markdown-Body.
- Umfangreiche Detaildokumente können optional unter `references/` liegen und werden dann aus `SKILL.md` relativ referenziert.
- Assets oder Hilfsskripte können später unter `assets/` beziehungsweise `scripts/` ergänzt werden.

## Aktive Arbeitsdateien

| Datei | Zweck |
| --- | --- |
| [`state/CURRENT_STATE.md`](state/CURRENT_STATE.md) | Zuletzt abgeschlossener und geprüfter Projektzustand. |
| [`state/phases.md`](state/phases.md) | Aktuelles Sprint-Log; leer, wenn kein Sprint aktiv ist. |

## Verfügbare Skills

| Skill | Zweck | Aktivierung |
| --- | --- | --- |
| [`concept-refinement`](skills/concept-refinement/SKILL.md) | Verfeinert das OpenClaw-Nexus-Konzept von grober Idee zu prüfbarem Zielbild, Scope, Nicht-Zielen, Authority-Grenzen, Akzeptanzkriterien und nächstem Arbeitspaket. | Verwenden bei Anfragen wie „Verfeinere das Konzept“, „Schärfe das Zielbild“ oder „Was fehlt dem Konzept noch?“. |
| [`system-analysis`](skills/system-analysis/SKILL.md) | Analysiert und bewertet OpenClaw Nexus als Gesamtsystem über Produktzweck, Architektur, Authority-Modell, Codequalität, Tests, Betrieb, Dokumentation, Risiken und nächste Verbesserungen. | Verwenden bei Anfragen wie „Analysiere das ganze System“, „Bewerte die Architektur“ oder „Gib mir eine System-Scorecard“. |
| [`sprint-workflow`](skills/sprint-workflow/SKILL.md) | Erstellt, führt und schließt wiederholbare Änderungssprints anhand von `state/phases.md` aus; jede geplante Phase ist auf ca. 4 Stunden Aufwand für einen erfahrenen Entwickler zugeschnitten; bekannte Timeout-Risiko-Tests werden während Sprints nicht blind erneut ausgeführt, sondern quarantänisiert oder gezielt repariert. | Verwenden bei Anfragen wie „erstelle mir einen Sprint zu Thema …“, „Führe die nächste Phase aus.“ oder „clear Sprint“. |
| [`drift`](skills/drift/SKILL.md) | Prüft den allgemeinen Projektstatus auf Drift zwischen Projektabsicht, dokumentiertem Zustand, tatsächlicher Umsetzung, Tests, Konfiguration, Scripts und aktiver Dokumentation. | Verwenden bei Anfragen wie „Mach eine Drift-Prüfung“, „Sind wir noch auf Kurs?“ oder „Passt CURRENT_STATE noch zur Realität?“. |
| [`legacy`](skills/legacy/SKILL.md) | Prüft aktive Projektteile auf Altlasten, tote Ansätze, überholte Konzepte, doppelte Implementierungen, unnötigen Code, Platzhalter, veraltete Tests und Archiv-Leaks. | Verwenden bei Anfragen wie „Prüfe auf Altlasten“, „Gibt es Legacy-Code?“ oder „Welche alten Ansätze können weg?“. |
| [`leverage`](skills/leverage/SKILL.md) | Lokalisiert den wichtigsten konkreten Hebel, der OpenClaw Nexus aktuell am stärksten produktionsreifer macht. | Verwenden bei Anfragen wie „Was macht uns am meisten produktionsreifer?“ oder „Finde den größten Production-Readiness-Hebel“. |


## Kontext-Helfer

Damit ChatGPT nicht bei jeder Anfrage unnötig den gesamten `.chatgpt`-Kontext einlesen muss, gibt es einen kompakten Kontext-Packer:

```bash
python .chatgpt/scripts/context_pack.py --query "Mach eine Drift-Prüfung"
python .chatgpt/scripts/context_pack.py --skill legacy
python .chatgpt/scripts/context_pack.py --list-skills
```

Der Packer wählt anhand von `--query` den wahrscheinlich passenden Skill aus, gibt nur dessen wichtigste Anweisungen, relevante State-Auszüge und High-Signal-Dateien aus und kann bei Bedarf mit `--mode full` ausführlicher werden.

## Pflegehinweise

- Neue Skills immer unter `.chatgpt/skills/<skill-name>/SKILL.md` anlegen.
- Skill-Namen kleinschreiben und nur Buchstaben, Zahlen und Bindestriche verwenden.
- Die `description` so formulieren, dass ChatGPT zuverlässig erkennt, wann der Skill relevant ist.
- Diese README ist der Einstiegspunkt und muss bei jedem neuen Skill aktualisiert werden.
