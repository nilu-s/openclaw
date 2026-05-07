---
name: legacy
description: Prüft aktive OpenClaw-Nexus-Projektteile auf Altlasten, tote Ansätze, überholte Konzepte, doppelte Implementierungen, unnötigen Code, Platzhalter, veraltete Tests und Archiv-Leaks. Verwenden, wenn der Nutzer Legacy-Code, Altlasten, alte Zielbilder, nicht mehr benötigte Dateien oder unnötige Kompatibilitätsreste finden, bewerten oder für Entfernung vorbereiten möchte.
metadata:
  project: openclaw-nexus
  version: "1.0"
---

# Legacy Skill

Dieser Skill identifiziert Altlasten im aktiven OpenClaw-Nexus-Projekt. Er sucht nicht einfach nach alten Dateien, sondern prüft, ob aktive Projektteile noch zum aktuellen Zielzustand gehören oder nur historische Konzepte weitertragen.

## 1. Aktivierung

Aktiviere diesen Skill bei Aufträgen wie:

- „Prüfe auf Altlasten."
- „Gibt es Legacy-Code?"
- „Welche alten Ansätze können weg?"
- „Finde nicht mehr benötigten Code."
- „Prüfe, ob alte Konzepte noch im Projekt hängen."
- „Können wir diesen alten Ansatz entfernen?"

Nicht aktivieren, wenn der Nutzer primär Zielbild-vs-Ist-Konsistenz prüfen möchte; dafür `drift` verwenden. Nicht aktivieren, wenn der Nutzer den größten Produktionsreife-Hebel sucht; dafür `leverage` verwenden.

## 2. Kernvertrag

1. Der Skill prüft Altlasten und bereitet Entscheidungen vor. Er löscht nichts ohne ausdrücklichen Nutzerauftrag.
2. Der aktuelle Zielzustand zählt. Alte Versionen, historische Pläne und archivierte Sprints haben keinen Kompatibilitätsvorrang.
3. `docs/archiv/` ist historische Quelle und darf nicht als aktive Wahrheit genutzt werden.
4. Nicht jede alte Datei ist eine Altlast. Entscheidend ist, ob sie aktiv gebraucht, dokumentiert, getestet oder bewusst archiviert ist.
5. Jeder Entfernungs-Vorschlag braucht eine Begründung und einen sicheren nächsten Prüfschritt.

## 3. Quellenpriorität

| Priorität | Quelle | Zweck |
| --- | --- | --- |
| 1 | Aktiver Code | Nutzung, Imports, tote Pfade, doppelte Implementierungen. |
| 2 | Tests | Historische Annahmen, tote Testziele, Platzhalter, veraltete Verträge. |
| 3 | `README.md`, Produkt- und Operations-Doku | Aktuelles Zielbild und aktive Bedienung. |
| 4 | `.chatgpt/state/CURRENT_STATE.md` | Geprüfter Status und bekannte Grenzen. |
| 5 | `nexus/*.yml`, `config/*`, Scripts | Aktive Laufzeit- und Validierungsannahmen. |
| 6 | `.chatgpt/state/phases.md` | Laufende Arbeiten, falls vorhanden. |
| 7 | `docs/archiv/` | Nur Herkunft historischer Konzepte. |

## 4. Fundklassen

Klassifiziere jeden Fund in genau eine Hauptklasse:

| Klasse | Bedeutung |
| --- | --- |
| Tote Datei | Datei wird nicht importiert, getestet, dokumentiert oder aktiv genutzt. |
| Toter Code | Funktion, Klasse oder Pfad ist nicht erreichbar oder nicht mehr referenziert. |
| Legacy-Konzept | Alter Begriff oder altes Zielbild lebt im aktiven Projekt weiter. |
| Überholter Test | Test sichert Verhalten ab, das nicht mehr aktueller Zielzustand ist. |
| Platzhalter | Datei oder Test existiert nur strukturell und liefert keinen echten Wert. |
| Doppelter Ansatz | Zwei Implementierungen lösen denselben Zweck ohne klare Abgrenzung. |
| Kompatibilitätsrest | Code hält alte Semantik künstlich am Leben. |
| Archiv-Leak | Historischer Inhalt beeinflusst aktive Doku, Planung oder Implementierung. |
| Unklare Zuständigkeit | Modul oder Datei ist aktiv, aber fachlich nicht mehr sauber verortet. |

## 5. Vorgehen

1. Bestimme den Prüfbereich: gesamtes Projekt, bestimmtes Modul, Tests, Doku oder ein konkreter Verdacht.
2. Ermittle den aktuellen Zielzustand aus aktiver Doku, `CURRENT_STATE.md`, Code und Tests.
3. Suche nach Altlasten-Indikatoren:
   - historische Begriffe oder alte Versionsnamen,
   - ungenutzte Imports, Klassen, Funktionen oder CLI-Pfade,
   - leere oder rein strukturelle Platzhalter,
   - doppelte Services oder Repository-Pfade,
   - Tests, die nur alte Semantik schützen,
   - aktive Referenzen auf `docs/archiv/` als Wahrheit,
   - Kompatibilitätslogik ohne aktuellen Nutzerwert.
4. Prüfe jeden Verdacht gegen Nutzung, Tests, Dokumentation und Konfiguration.
5. Teile Funde in diese Entscheidungsgruppen:
   - `sicher entfernen empfohlen`
   - `verdächtig, weiter prüfen`
   - `bewusst behalten`
   - `nicht entfernen ohne Entscheidung`
6. Schlage für Entfernen immer eine Validierung vor.

## 6. Entfernen-Entscheidung

Empfiehl Entfernung nur, wenn mindestens zwei dieser Punkte erfüllt sind:

- Keine aktive Referenz aus Code, Tests, Scripts oder Konfiguration.
- Kein aktueller Produkt- oder Betriebszweck in aktiver Doku.
- Tests prüfen nur historische Semantik oder sind Platzhalter.
- Eine neuere aktive Implementierung ersetzt denselben Zweck.
- `CURRENT_STATE.md` oder README beschreibt den Ansatz nicht mehr als aktiv.

Empfiehl keine Entfernung, wenn:

- Der Code sicherheits-, audit-, migrations- oder backuprelevant sein könnte.
- Der einzige Beleg fehlende Dokumentation ist.
- Ein Test den aktuellen Zielzustand plausibel schützt.
- Die Datei Teil der bewusst archivierten Historie ist.

## 7. Ergebnisformat

Verwende dieses Format:

```markdown
## Legacy-Review

### Ergebnis
- Status: grün / gelb / rot
- Kurzfazit: ...
- Prüfumfang: ...

### Sichere Altlasten
| Fund | Datei / Symbol | Klasse | Begründung | Empfehlung |
| --- | --- | --- | --- | --- |

### Verdächtige Altlasten
| Fund | Datei / Symbol | Warum verdächtig | Nächster Prüfschritt |
| --- | --- | --- | --- |

### Bewusst behalten
| Fund | Grund |
| --- | --- |

### Entfernen empfohlen
- ...

### Nicht entfernen ohne Entscheidung
- ...

### Validierung nach Entfernung
- ...
```

Wenn keine Altlasten gefunden werden, nenne die geprüften Bereiche und warum die Funde als bewusst aktiv gelten.

## 8. Statusampel

- `grün`: Keine relevanten Altlasten im geprüften Bereich.
- `gelb`: Verdächtige oder kleine Altlasten, aber kein unmittelbares Risiko.
- `rot`: Aktive Altlasten gefährden Zielbild, Tests, Betrieb, Sicherheit, Auditierbarkeit oder Wartbarkeit.

## 9. Zusammenspiel mit anderen Skills

- Nutze `drift`, wenn unklar ist, ob ein Fund wirklich Legacy ist oder ob der dokumentierte Projektstatus selbst falsch ist.
- Nutze `leverage`, wenn mehrere Aufräumarbeiten möglich sind und entschieden werden soll, welche Produktionsreife am stärksten erhöht.
- Nutze `sprint-workflow`, wenn aus bestätigten Legacy-Funden ein strukturierter Änderungssprint entstehen soll.
