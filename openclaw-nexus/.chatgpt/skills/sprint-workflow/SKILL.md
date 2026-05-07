---
name: sprint-workflow
description: Erstellt, plant, führt und schließt wiederholbare OpenClaw-Nexus-Änderungssprints. Verwenden, wenn der Nutzer einen Sprint zu einem Thema erstellen möchte, „Führe die nächste Phase aus.“ sagt, einen laufenden Sprint über .chatgpt/state/phases.md fortsetzen will oder mit „clear Sprint“ den Sprintabschluss auslösen möchte.
metadata:
  project: openclaw-nexus
  version: "1.3"
---

# Sprint Workflow Skill

Dieser Skill definiert das verbindliche Ausführungsprotokoll für wiederholbare Änderungssprints in OpenClaw Nexus. Er ist bewusst neutral: Er enthält keine fachliche Roadmap und keine Produktprioritäten. Konkrete Sprint-Inhalte entstehen ausschließlich aus dem Nutzerauftrag, dem geprüften Projektzustand und der aktiven Datei `.chatgpt/state/phases.md`.

## 1. Aktivierung

Aktiviere diesen Skill bei Aufträgen wie:

- „Erstelle mir einen Sprint zu Thema X."
- „Plane einen Sprint für X und Y."
- „Führe die nächste Phase aus."
- „Arbeite anhand von .chatgpt/state/phases.md weiter."
- „clear Sprint"
- „Schließe den aktuellen Sprint ab."

Wenn kein Sprint aktiv ist, darf `.chatgpt/state/phases.md` leer sein.

## 2. Kernvertrag

1. `.chatgpt/state/phases.md` ist die einzige aktive Sprint-Arbeitsdatei und das Live-Log.
2. `.chatgpt/skills/sprint-workflow/SKILL.md` enthält nur Protokoll, Formatregeln und Abschlussmechanik.
3. `.chatgpt/state/CURRENT_STATE.md` beschreibt nur den zuletzt abgeschlossenen und geprüften Zustand, nicht den Live-Zwischenstand.
4. Jede normale Übergabe erzeugt genau ein ZIP-Artefakt mit dem Namen `openclaw-nexus.zip`.
5. Für normale Sprintarbeit gilt maximal Fast-Validierung beziehungsweise maximal Fast-Tests.
6. Kein Kompatibilitätszwang: Alte Zwischenstände bleiben nur aktiv, wenn sie ausdrücklich Teil des aktuellen Produktvertrags sind.
7. Der Agent darf aus Beispielen in diesem Skill keine fachlichen Sprintziele ableiten.

## 3. Arbeitsaufwand pro Phase

Jede Phase, die in `.chatgpt/state/phases.md` erstellt wird, muss für einen erfahrenen Entwickler auf ungefähr vier Stunden konzentrierten Arbeitsaufwand zugeschnitten sein.

Verbindliche Schnittregeln:

- Eine Phase soll ungefähr einen halben Arbeitstag umfassen.
- Größere Arbeitspakete müssen in mehrere klar abgegrenzte Phasen zerlegt werden.
- Deutlich kleinere Aufgaben dürfen zusammengefasst werden, wenn sie fachlich zusammengehören.
- Jede Phase muss ohne Rückfrage mit „Führe die nächste Phase aus." ausführbar sein.
- Jede Phase muss ein prüfbares Ergebnis liefern, nicht nur Analyse ohne verwertbaren Projektzustand.
- Der erwartete Aufwand ist eine Planungsgröße, kein Versprechen über die reale Laufzeit eines Agenten oder Tools.

Jede Phase enthält deshalb ein Feld `Aufwand`, zum Beispiel:

```markdown
Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler
```

## 4. Rollen der Dateien

| Datei | Rolle |
| --- | --- |
| `.chatgpt/README.md` | Einstiegspunkt und Index für alle Skills. |
| `.chatgpt/skills/sprint-workflow/SKILL.md` | Dieser Skill: neutrales Sprint-Protokoll. |
| `.chatgpt/state/phases.md` | Aktueller Sprintplan, nächste offene Phase und Live-Ergebnislog. |
| `.chatgpt/state/CURRENT_STATE.md` | Nur der geprüfte Zustand nach abgeschlossenem Sprint. |
| `docs/archiv/sprints/` | Archiv abgeschlossener Sprint-Logs. |

## 5. Modus A — Sprint zu einem Thema erstellen

Wenn der Nutzer einen Sprint zu einem Thema anfordert:

1. Den Nutzerauftrag in Schwerpunkt, Zielzustand und Nicht-Ziele übersetzen.
2. Relevante Projektdateien prüfen, bevor Phasen formuliert werden.
3. Bestehendes `.chatgpt/state/phases.md` berücksichtigen:
   - Wenn kein Sprint aktiv ist, einen neuen Sprint anlegen.
   - Wenn ein Sprint aktiv ist, nur überschreiben oder erweitern, wenn der Nutzerauftrag das verlangt.
4. Phasen so schneiden, dass jede Phase ungefähr vier Stunden Arbeitsaufwand für einen erfahrenen Entwickler entspricht.
5. Jede Phase mit Ziel, Aufwand, Kontext, Aufgaben, Akzeptanzkriterien, Validierung, erwarteter Änderung am `Current-State-Delta` und Status versehen.
6. Keine Implementierung ausführen, sofern der Nutzer nur Sprintplanung angefordert hat.
7. Falls die gewünschte Arbeit deutlich größer als ein Sprint ist, zuerst einen realistischen Sprint-Ausschnitt planen und die restliche Arbeit als Nicht-Ziel oder Folgearbeit markieren.

## 6. Modus B — „Führe die nächste Phase aus."

Wenn der Nutzer die nächste Phase ausführen lässt:

1. `.chatgpt/state/phases.md` vollständig lesen.
2. Die nächste offene Phase bestimmen.
3. Nur diese Phase ausführen.
4. Keine zusätzlichen Phasen vorziehen, auch wenn sie naheliegen.
5. Änderungen in `.chatgpt/state/phases.md` protokollieren.
6. `Current-State-Delta` aktualisieren, wenn sich Fähigkeiten, Grenzen, Risiken oder nächste Arbeiten ändern.
7. Maximal die Fast-Validierung ausführen.
8. Tests mit bekannter Timeout-Gefahr nicht erneut blind ausführen; stattdessen die Timeout-Policy aus Abschnitt 12 anwenden.
9. `openclaw-nexus.zip` erzeugen.
9. Im Chat kurz Ergebnis, geänderte Dateien, Validierung, offene Punkte und Download-Link nennen.

Antwortformat:

```markdown
Erledigt:
- ...

Geändert:
- ...

Validierung:
- ...

Offene Punkte:
- ...

Download: openclaw-nexus.zip
```

Wenn keine offenen Punkte bestehen, wird `Offene Punkte: keine` verwendet.

## 7. Modus C — Clear-Up-Funktion: Sprint abschließen

Die Clear-Up-Funktion beendet einen aktiven Sprint kontrolliert.

Auslöser im Chat:

```text
clear Sprint
Schließe den aktuellen Sprint ab.
```

Wenn ein LLM-Agent diese Anweisung erhält, muss der vollständige Abschlussmechanismus ausgeführt werden. Der Agent darf nicht nur `.chatgpt/state/phases.md` leeren oder ein ZIP bauen.

Pflichtschritte:

1. `.chatgpt/state/phases.md` vollständig lesen.
2. Prüfen, ob Ergebnis, Validierung, offene Punkte und `Current-State-Delta` enthalten sind.
3. Einen verpflichtenden LLM-Abschluss-Doublecheck durchführen:
   - aktuellen Ist-Zustand aus Code, Tests, aktiver Dokumentation, Scripts und Konfiguration ableiten,
   - `Current-State-Delta` gegen diesen Ist-Zustand prüfen,
   - falsche, überholte oder fehlende Aussagen korrigieren,
   - prüfen, dass keine Altversions-Kompatibilität als aktive Zielversion fortgeführt wird,
   - prüfen, dass bekannte Grenzen und empfohlene nächste Arbeiten realistisch beschrieben sind.
4. `.chatgpt/state/CURRENT_STATE.md` erst nach diesem Abschluss-Doublecheck auf den zuletzt geprüften Zustand aktualisieren.
5. In `.chatgpt/state/phases.md` einen Abschlussblock `LLM-Doublecheck` ergänzen mit:
   - Prüfumfang,
   - Ergebnis,
   - Änderungen an `.chatgpt/state/CURRENT_STATE.md`,
   - bewusst akzeptierten Abweichungen oder `keine`.
6. Den Inhalt von `.chatgpt/state/phases.md` unter `docs/archiv/sprints/` archivieren.
7. `.chatgpt/state/phases.md` leeren.
8. Standardvalidierung ausführen, ohne bekannte Timeout-Risiko-Tests blind einzuschließen.
9. `openclaw-nexus.zip` neu erzeugen.

Akzeptanzkriterien:

- Der Sprint ist im Archiv nachvollziehbar abgelegt.
- `.chatgpt/state/phases.md` ist nach Abschluss leer.
- `.chatgpt/state/CURRENT_STATE.md` beschreibt den abgeschlossenen Zielzustand und keine Zwischenarbeit.
- Der archivierte Sprint enthält einen ausgefüllten Abschnitt `LLM-Doublecheck`.
- Offene Punkte aus dem Sprint sind in `.chatgpt/state/CURRENT_STATE.md` oder im Archiv sichtbar.
- Das ZIP heißt exakt `openclaw-nexus.zip`.

Optionale lokale Unterstützung:

```bash
python scripts/close_sprint.py
```

Dieses Script archiviert eine nicht-leere `.chatgpt/state/phases.md` nach `docs/archiv/sprints/`, leert `.chatgpt/state/phases.md` und lässt leere Sprint-Logs unverändert. Bei nicht-leeren Sprint-Logs verweigert es den Abschluss, wenn der Abschnitt `LLM-Doublecheck` fehlt. Die fachliche Aktualisierung von `.chatgpt/state/CURRENT_STATE.md` und der Doublecheck müssen durch den ausführenden Agenten vor dem Scriptlauf erfolgen.

## 8. Struktur von `.chatgpt/state/phases.md`

`.chatgpt/state/phases.md` darf leer sein. Wenn es nicht leer ist, enthält es ein kompaktes, prüfbares Sprint-Log.

Minimaler Steuerblock:

```yaml
sprint:
  schwerpunkt: <vom Nutzerauftrag abgeleiteter Schwerpunkt>
  ziel: <prüfbarer Zielzustand>
  nicht_ziele:
    - <bewusst ausgeschlossene Arbeit>
  validierungsniveau: fast
  ausgabe: openclaw-nexus.zip
  aktuelle_phase: <Phase-ID oder abgeschlossen>
```

Jede Phase enthält mindestens:

- Phase-ID
- Ziel
- Aufwand: ca. vier Stunden für einen erfahrenen Entwickler
- Kontext oder relevante Dateien
- konkrete Aufgaben
- Akzeptanzkriterien
- Validierung
- erwartete Änderung am `Current-State-Delta`, falls zutreffend
- Status

## 9. Neutrale Vorlage für eine Phase

Dieses Beispiel beschreibt nur das Format. Die Inhalte sind Platzhalter und dürfen nicht als fachliche Vorgabe übernommen werden.

```markdown
## P1 — <neutraler Phasentitel>

Ziel:
- <was nach dieser Phase wahr sein soll>

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- <relevante Dateien, Module, Tests oder Dokumente>

Aufgaben:
- <konkrete Aufgabe 1>
- <konkrete Aufgabe 2>
- <konkrete Aufgabe 3>

Akzeptanzkriterien:
- <prüfbares Kriterium 1>
- <prüfbares Kriterium 2>

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh fast`

Ergebnis:
- Status: offen
- Geänderte Dateien: <Liste oder leer>
- Offene Punkte: <Liste oder keine>
```

## 10. Vollständiges neutrales `.chatgpt/state/phases.md`-Beispiel

```markdown
# Sprint-Log

```yaml
sprint:
  schwerpunkt: <Schwerpunkt aus Nutzerauftrag>
  ziel: <prüfbarer Zielzustand>
  nicht_ziele:
    - <Nicht-Ziel>
  validierungsniveau: fast
  ausgabe: openclaw-nexus.zip
  aktuelle_phase: P1
```

## P1 — <neutraler Phasentitel>

Ziel:
- <was nach dieser Phase wahr sein soll>

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- <relevante Dateien, Module, Tests oder Dokumente>

Aufgaben:
- <konkrete Aufgabe 1>
- <konkrete Aufgabe 2>

Akzeptanzkriterien:
- <prüfbares Kriterium 1>
- <prüfbares Kriterium 2>

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh fast`

Ergebnis:
- Status: offen
- Geänderte Dateien: <Liste oder leer>
- Offene Punkte: <Liste oder keine>

## Current-State-Delta

Neue Fähigkeiten:
- <falls zutreffend>

Geänderte Grenzen:
- <falls zutreffend>

Entfernte oder bereinigte Bestandteile:
- <falls zutreffend>

Neue bekannte Risiken:
- <falls zutreffend>

Empfohlene nächste Arbeiten:
- <falls zutreffend>
```

## 11. Validierung

Standardvalidierung:

```bash
python scripts/validate_project.py
./scripts/run_tests.sh fast
```

`fast` ist der Sprint-Begriff für die schnelle Standardauswahl des Runners. Im aktuellen Script ist `fast` ein expliziter Alias für denselben Marker-Schnitt wie `unit`: `not integration and not slow and not timeout_risk`.

Nicht als Standardvalidierung ausführen:

```bash
./scripts/run_tests.sh integration
./scripts/run_tests.sh e2e
./scripts/run_tests.sh full
```

Ausnahmen sind nur erlaubt, wenn der Nutzer sie ausdrücklich anfordert oder wenn der konkrete Sprint-Schwerpunkt genau diese Testebene betrifft. Sandbox-Timeouts aus optionalen längeren Tests gelten nicht als Produktfehler, solange die Fast-Validierung bestanden ist und der Timeout plausibel umgebungsbedingt ist.

## 12. Test-Timeout-Policy während eines Sprints

Während eines Sprints gilt: Timeouts sind Arbeitsinput, aber kein Grund, dieselben riskanten Tests immer wieder blind auszuführen.

Verbindliche Regeln:

- Die Standardvalidierung bleibt `python scripts/validate_project.py` plus `./scripts/run_tests.sh fast`.
- Tests, die bereits konkret als Timeout-Risiko bekannt sind, werden mit dem Marker `timeout_risk` isoliert und von `scripts/run_tests.sh` standardmäßig ausgeschlossen.
- Ein Test darf nur dann als `timeout_risk` markiert werden, wenn ein echter Timeout beobachtet wurde oder der Nutzer ihn ausdrücklich als Timeout-Kandidat benennt.
- Timeout-Risiko-Tests werden erst wieder bewusst ausgeführt, wenn die aktuelle Phase explizit ihre Reparatur oder Verifikation zum Ziel hat. Dann wird `OPENCLAW_INCLUDE_TIMEOUT_RISK=1` gesetzt.
- Wenn während einer Phase ein neuer Timeout auftritt, wird nicht mehrfach derselbe Lauf wiederholt. Stattdessen muss der Agent:
  1. den Timeout im Ergebnis der Phase dokumentieren,
  2. die vermutete Ursache und den betroffenen Test notieren,
  3. nach Möglichkeit einen fokussierten Fix umsetzen, wenn er in den ca. 4-Stunden-Phasenschnitt passt,
  4. den Test nur für einen gezielten Reparaturlauf erneut einschließen,
  5. andernfalls den Test als `timeout_risk` quarantänisieren und eine Folgephase oder offenen Punkt anlegen.
- Timeout-Risiko-Tests dürfen nicht stillschweigend ignoriert werden. Sie müssen in `.chatgpt/state/phases.md` unter `Ergebnis`, `Offene Punkte` oder `Current-State-Delta` sichtbar sein.
- Ein Sprint darf als sauberer Zwischenstand übergeben werden, wenn die Fast-Validierung ohne `timeout_risk`-Tests grün ist und alle ausgeklammerten Timeout-Risiken dokumentiert sind.

Projektmechanik:

- Der Marker `timeout_risk` ist in `pytest.ini` deklariert.
- Bekannte Timeout-Dateien werden in `conftest.py` in `TIMEOUT_RISK_TESTS` eingetragen.
- `scripts/run_tests.sh` schließt `timeout_risk` standardmäßig aus.
- Bewusster Reparatur- oder Verifikationslauf:

```bash
OPENCLAW_INCLUDE_TIMEOUT_RISK=1 ./scripts/run_tests.sh fast
```

Wenn der Sprint eine Timeout-Reparaturphase enthält, muss die Phase ein separates Validierungsfeld enthalten:

```markdown
Validierung:
- `./scripts/run_tests.sh fast`
- gezielt nach Fix: `OPENCLAW_INCLUDE_TIMEOUT_RISK=1 ./scripts/run_tests.sh fast <betroffener Test oder pytest args>`
```

## 13. ZIP-Übergabe

Jede Übergabe erzeugt genau ein ZIP-Artefakt mit exakt diesem Namen:

```text
openclaw-nexus.zip
```

Das ZIP enthält das Projektverzeichnis und keine lokalen Arbeitsreste, insbesondere keine:

- `.git/`
- `.pytest_cache/`
- `__pycache__/`
- `.venv/` oder `venv/`
- lokale `.db`, `.sqlite`, `.sqlite3`
- alte oder verschachtelte `.zip`-Dateien
- `.pyc` oder `.pyo`

## 14. Anti-Framing-Regel

Beispiele in diesem Skill sind Platzhalter. Sie dürfen nicht als inhaltliche Vorgabe interpretiert werden.

Der Agent muss bei der Erstellung oder Ausführung von Phasen:

- den Nutzerauftrag priorisieren,
- den vorhandenen Projektzustand prüfen,
- keine Beispielthemen aus diesem Skill übernehmen,
- keine Standardphase mit fachlichem Inhalt füllen, nur weil sie im Beispiel erwähnt wird,
- keine Roadmap aus diesem Skill ableiten,
- keine Arbeit ausführen, die nicht durch `.chatgpt/state/phases.md`, den Nutzerauftrag oder den geprüften Projektzustand begründet ist.

## 15. Zielversion statt Kompatibilitätszwang

Für Änderungssprints gilt: kein Kompatibilitätszwang für alte Versionen.

Eine saubere aktuelle Zielversion ist wichtiger als das Mitschleppen alter Zwischenstände. Alte Befehle, alte Datenmodelle, alte Tabelleninhalte, alte Aliasnamen, alte Importpfade oder alte Zwischenartefakte müssen nur erhalten bleiben, wenn sie ausdrücklich Teil des aktuellen Produktvertrags sind.

Erlaubt ist insbesondere:

- aktive Altlasten zu entfernen,
- Datenmodelle und Tabellenstrukturen an die Zielversion anzupassen,
- lokale Datenbankinhalte zu verlieren,
- Tests, Dokumentation und Scripts auf den aktuellen Zielzustand umzubenennen,
- historische Inhalte zu archivieren oder aus der aktiven Steuerung zu entfernen.

Nicht erlaubt ist:

- stille Fallbacks oder Alias-Pfade nur für alte Versionen einzubauen,
- historische Dateien als aktive Runtime-, CLI-, API-, Test- oder Packaging-Quelle zu verwenden,
- aktuelle Dokumentation mit Umsetzungshistorie statt Produktzustand zu füllen.

## 16. Zustandsregel für `.chatgpt/state/CURRENT_STATE.md`

`.chatgpt/state/CURRENT_STATE.md` beschreibt nur den zuletzt abgeschlossenen und geprüften Zustand. Während ein Sprint läuft, darf `.chatgpt/state/CURRENT_STATE.md` bewusst veraltet sein und wird nicht als Live-Log verwendet.

Live-Änderungen stehen während des Sprints ausschließlich in `.chatgpt/state/phases.md`, insbesondere im Abschnitt `Current-State-Delta`.

Beim Sprintabschluss wird `.chatgpt/state/CURRENT_STATE.md` nicht automatisch aus dem Delta übernommen. Zuerst muss ein LLM-Agent einen unabhängigen Abschluss-Doublecheck durchführen. Der Agent liest den aktuellen Ist-Zustand aus Code, Tests, aktiver Dokumentation, Scripts und Konfiguration, prüft das Delta dagegen, korrigiert Widersprüche und aktualisiert erst danach `.chatgpt/state/CURRENT_STATE.md`.
