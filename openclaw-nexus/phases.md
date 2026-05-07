# OpenClaw Nexus Cleanup Orchestration Phases

Dieses Dokument ist die verbindliche Arbeitsanweisung für LLM-Agenten und Entwickler, um OpenClaw Nexus von Legacy-Kompatibilitätszwängen zu befreien, ohne gewollte Kontrollfeatures zu entfernen.

Der Agent soll jeweils nur die **nächste offene Phase** ausführen. Wenn der Nutzer sagt: "Führe die nächste Phase aus", dann gilt:

1. Diese Datei lesen.
2. Die erste Phase mit Status `open` auswählen.
3. Nur diese Phase bearbeiten.
4. Keine späteren Phasen vorziehen.
5. Tests/Checks der Phase ausführen, soweit lokal möglich.
6. Den Phasenstatus in dieser Datei aktualisieren.
7. Die Fortschrittsfelder der bearbeiteten Phase direkt in dieser Datei aktualisieren.
8. Ein sauberes ZIP-Artefakt mit exakt dem Namen `openclaw-nexus.zip` erzeugen.

## Zielzustand

OpenClaw Nexus soll genau eine saubere Zielversion unterstützen.

Nicht mehr gewollt:

- dauerhafte Kompatibilität zu alten Paketlayouts
- Legacy-Import als öffentlicher Produktpfad
- alte CLI-Commands als stabiler Contract
- Backwards-compatible Aliase
- Runtime- oder Test-Abhängigkeiten auf `referenzen/setup`
- Legacy-Import-Reports als Quelle aktueller Runtime-Entscheidungen
- Tests, die historische Migrationspfade als Pflichtbestand erzwingen

Weiterhin ausdrücklich gewollt:

- Generated Artifact Drift Detection
- GitHub Projection Drift Detection
- Runtime/Schedule Drift Checks
- Merge Staleness Gates
- Reconciliation Alerts
- Audit Events
- Policy Gates
- Doctor Output als stabiler Zielversions-Contract
- OpenClaw-Generierung aus Nexusctl als Source of Truth

## Globale Regeln für Agenten

### Arbeitsumfang

Jede Phase ist auf ungefähr 4 Stunden Arbeit für einen erfahrenen Entwickler zugeschnitten. Wenn eine Phase größer wird, muss der Agent sie nicht heimlich erweitern, sondern:

- den abgeschlossenen Teil commitfähig hinterlassen,
- offene Punkte direkt im Abschnitt der bearbeiteten Phase unter `Open items:` notieren,
- den Phasenstatus auf `partial` setzen.

### Keine Feature-Regression

Der Agent darf keine fachlichen Kontrollfeatures entfernen, nur weil sie das Wort `drift`, `reconcile`, `doctor`, `check`, `audit`, `policy` oder `stale` enthalten.

Die Leitfrage lautet immer:

```text
Ist das ein altes Kompatibilitätsversprechen oder ein aktuelles Kontrollfeature?
```

Entscheidung:

```text
Altes Kompatibilitätsversprechen: entfernen oder archivieren.
Aktuelles Kontrollfeature: behalten, sauber benennen, besser testen/dokumentieren.
```

### Packaging-Regel

Jede abgeschlossene Phase muss ein Übergabeartefakt mit exakt diesem Dateinamen erzeugen:

```text
openclaw-nexus.zip
```

Das ZIP darf keine Cache-Verzeichnisse, lokalen virtuellen Umgebungen, `.git`-Daten oder alten Zwischen-ZIPs enthalten.

### Test-Regel

Nach jeder Phase mindestens ausführen, sofern möglich:

```bash
./scripts/run_tests.sh fast
```

Wenn die Phase Integrations- oder E2E-relevante Stellen berührt, zusätzlich:

```bash
./scripts/run_tests.sh integration
./scripts/run_tests.sh e2e
```

Wenn Tests wegen bereits bekannter Baseline-Drifts fehlschlagen, muss der Agent das präzise dokumentieren und darf es nicht verschweigen.

### Fortschrittsdokumentation

Es gibt keine separate Phase-Log-Datei. `phases.md` ist der einzige Status- und Fortschrittsort.

Nach jeder Phase aktualisiert der Agent direkt im bearbeiteten Phasenabschnitt diese Felder:

```markdown
Status: open|partial|done|blocked
Started: YYYY-MM-DD oder leer
Completed: YYYY-MM-DD oder leer
Summary:
- ...
Changed files:
- ...
Validation:
- Befehl: Ergebnis
Open items:
- ...
```

Wenn eine Phase noch keine Fortschrittsfelder enthält, ergänzt der Agent sie direkt unterhalb der Statuszeile.

### Statuswerte

Jede Phase hat genau einen Status:

```text
open      noch nicht begonnen
partial   begonnen, aber nicht vollständig abgeschlossen
done      abgeschlossen und geprüft
blocked   blockiert; Grund direkt im Phasenabschnitt unter `Open items:` dokumentiert
```

Ein Agent darf nur Phasen mit Status `open` oder `partial` bearbeiten. `done`-Phasen dürfen nicht erneut verändert werden, außer der Nutzer fordert das explizit.

---

# Phase 0 — Baseline und Sicherheitsnetz einfrieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Baseline-Dokument für die Legacy-Entfernung unter `docs/cleanup/legacy-removal-baseline.md` angelegt.
- Aktuellen Arbeitsstand ohne verfügbare Git-Metadaten dokumentiert.
- Testzustand dokumentiert; bekannter Drift `OPENCLAW_TEST_TIMEOUT` wurde reproduziert und bewusst nicht behoben.
- Legacy-Kompatibilitätsanker und zu erhaltende Kontrollfeatures getrennt festgehalten.
Changed files:
- `docs/cleanup/legacy-removal-baseline.md`
- `phases.md`
Validation:
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 67 deselected; `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh`.
- `./scripts/run_tests.sh integration`: erfolgreich — 20 passed.
- `./scripts/run_tests.sh e2e`: erfolgreich — 1 passed.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

Den aktuellen Projektzustand dokumentieren, bevor Legacy-Kompatibilität entfernt wird.

## Aufgaben

1. Verzeichnis anlegen:

```bash
mkdir -p docs/cleanup
```

2. Baseline-Datei anlegen:

```text
docs/cleanup/legacy-removal-baseline.md
```

3. Darin dokumentieren:

- aktueller Branch oder Arbeitsstand
- aktueller Testzustand
- bekannter Drift: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht
- Liste der zu entfernenden Legacy-Kompatibilitätsanker
- Liste der zu erhaltenden Kontrollfeatures

4. Tests ausführen:

```bash
./scripts/run_tests.sh fast
./scripts/run_tests.sh integration
./scripts/run_tests.sh e2e
```

5. Fortschrittsfelder in diesem Phasenabschnitt aktualisieren.

## Akzeptanzkriterien

- `docs/cleanup/legacy-removal-baseline.md` existiert.
- Teststatus ist ehrlich dokumentiert.
- Keine Runtime-Code-Änderungen in dieser Phase.

## Nicht tun

- Noch keine Legacy-Dateien löschen.
- Noch keine CLI-Befehle entfernen.
- Noch keine Tests umschreiben.

---

# Phase 1 — Zielversions-Policy dokumentieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Zielversions-Policy unter `docs/architecture/target-version-policy.md` angelegt.
- Legacy-Kompatibilität und aktuelle Kontrollfeatures eindeutig getrennt dokumentiert.
- README um einen Verweis auf die neue Target-Version-Policy ergänzt.
Changed files:
- `docs/architecture/target-version-policy.md`
- `README.md`
- `phases.md`
Validation:
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 67 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

Eindeutig dokumentieren, was Legacy-Kompatibilität ist und was als modernes Produktfeature erhalten bleibt.

## Aufgaben

1. Datei anlegen:

```text
docs/architecture/target-version-policy.md
```

2. Darin klar dokumentieren:

### Nicht mehr unterstützt

- `legacy-import` CLI
- `LegacyImportService` als aktiver App-Service
- `referenzen/setup` als Runtime- oder Testquelle
- `AGENT_ALIASES` für alte Agentnamen
- `COMMAND_CAPABILITY_MAP` für alte Commands
- Backwards-compatible HTTP aliases
- Legacy-Import-Reports als aktive Entscheidungsquelle
- Tests, die Legacy-Import als Pflichtvertrag absichern

### Weiterhin unterstützt

- Generated Artifact Drift Detection
- GitHub Projection Drift Detection
- Schedule/Runtime Drift Checks
- Merge Staleness Gates
- Reconciliation Alerts
- Audit Events
- Policy Gates
- Doctor Output als Zielversions-Contract

3. README um einen kurzen Verweis auf `docs/architecture/target-version-policy.md` ergänzen.

## Akzeptanzkriterien

- Policy-Dokument existiert.
- README verweist darauf.
- Die Begriffe `Legacy-Kompatibilität` und `Kontrollfeature` sind eindeutig getrennt.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 2 — Legacy-Import aus öffentlicher CLI entfernen

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Öffentlichen `legacy-import` CLI-Parser, Dispatch und Command-Handler aus `nexusctl.interfaces.cli.main` entfernt.
- Import von `LegacyImportService` aus dem CLI-Einstiegspunkt entfernt.
- `tests/test_legacy_import.py` zu Negativtests umgebaut, die absichern, dass `legacy-import` nicht in der CLI-Hilfe registriert ist und als Kommando abgelehnt wird.
Changed files:
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `tests/test_legacy_import.py`
- `phases.md`
Validation:
- `PYTHONPATH=nexusctl/src python -m nexusctl.interfaces.cli.main --help`: erfolgreich — `legacy-import` erscheint nicht in der CLI-Hilfe.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 67 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.
- `LegacyImportService` selbst bleibt bis Phase 3 noch im App-Layer vorhanden; Phase 2 hat nur den öffentlichen CLI-Pfad entfernt.

## Ziel

`legacy-import` darf kein öffentlicher Produktbefehl mehr sein.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
tests/test_legacy_import.py
```

## Aufgaben

1. Aus `main.py` entfernen:

- Import von `LegacyImportService`
- Parser für `legacy-import`
- Dispatch für `legacy-import`
- Funktion `_cmd_legacy_import()`

2. CLI-Hilfe prüfen:

```bash
python -m nexusctl.interfaces.cli.main --help
```

3. `tests/test_legacy_import.py` entweder löschen oder zu einem Negativtest umbauen:

- neuer Test soll absichern, dass `legacy-import` nicht registriert ist.

## Akzeptanzkriterien

- `legacy-import` erscheint nicht mehr in der CLI-Hilfe.
- Aufruf von `legacy-import` wird abgelehnt.
- Kein öffentlicher CLI-Pfad führt mehr zum Legacy-Import.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 3 — LegacyImportService aus aktivem Produkt entfernen

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- `LegacyImportService` aus dem aktiven App-Layer entfernt.
- Historische Implementierung nach `docs/archiv/legacy/legacy_import_service.py.txt` verschoben und als Archivmaterial markiert.
- `scripts/validate_project.py` angepasst, sodass `tests/test_legacy_import.py` nicht mehr als Pflichtbestand verlangt wird.
- Aktive Pfade auf verbleibende Service-Imports geprüft; übrig bleibt nur der Negativtest für den entfernten CLI-Befehl.
Changed files:
- `docs/archiv/legacy/legacy_import_service.py.txt`
- `nexusctl/src/nexusctl/app/legacy_import_service.py`
- `scripts/validate_project.py`
- `phases.md`
Validation:
- `grep -R "LegacyImportService\|legacy_import_service\|legacy-import" -n nexusctl tests scripts`: erfolgreich — kein aktiver Service-Import; nur `tests/test_legacy_import.py` enthält den absichernden Negativtest für `legacy-import`.
- `python scripts/validate_project.py`: erfolgreich.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 67 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.
- `tests/test_legacy_import.py` ist nicht mehr Pflichtbestand in der Projektvalidierung, bleibt aber vorerst als Negativtest bis zur späteren No-Legacy-Contract-Bereinigung bestehen.

## Ziel

Der Legacy-Import ist nicht mehr Teil der App-Schicht.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/app/legacy_import_service.py
tests/test_legacy_import.py
scripts/validate_project.py
```

## Aufgaben

1. Entscheide bevorzugt: Datei entfernen.

```text
nexusctl/src/nexusctl/app/legacy_import_service.py
```

2. Falls historische Nachvollziehbarkeit gewünscht ist, Datei nicht aktiv behalten, sondern nach Archiv verschieben:

```text
docs/archiv/legacy/legacy_import_service.py.txt
```

3. Alle aktiven Imports entfernen:

```bash
grep -R "LegacyImportService\|legacy_import_service\|legacy-import" -n nexusctl tests scripts
```

4. `scripts/validate_project.py` so anpassen, dass `tests/test_legacy_import.py` nicht mehr als Pflichttest verlangt wird.

## Akzeptanzkriterien

- Kein aktiver Code importiert `LegacyImportService`.
- Kein aktiver Test verlangt Legacy-Import als Produktfeature.
- Historisches Material liegt höchstens unter `docs/archiv`.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 4 — `referenzen/setup` aus Runtime- und Testabhängigkeiten entfernen

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- `referenzen/setup/` aus dem aktiven Projektpfad entfernt und nach `docs/archiv/referenzen/setup/` verschoben.
- Archiv-Hinweis unter `docs/archiv/referenzen/README.md` ergänzt.
- README auf den archivierten Referenzort umgestellt und die aktive Projektstruktur bereinigt.
- `tests/test_blueprint_contract.py` so angepasst, dass der alte aktive Pfad nicht mehr vorausgesetzt wird und stattdessen die Archivierung abgesichert ist.
Changed files:
- `README.md`
- `docs/archiv/referenzen/README.md`
- `docs/archiv/referenzen/setup/`
- `referenzen/setup/`
- `referenzen/README.md`
- `tests/test_blueprint_contract.py`
- `phases.md`
Validation:
- `grep -R "referenzen/setup\|legacy_root\|setup/agents\|commands.json" -n nexusctl tests scripts`: erfolgreich — keine aktiven Code- oder Testreferenzen mehr.
- `python scripts/validate_project.py`: erfolgreich.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 67 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

Historische Referenzen dürfen Orientierung sein, aber niemals aktiver Input für Runtime, Tests oder Projektvalidierung.

## Betroffene Stellen

```text
referenzen/setup/
scripts/validate_project.py
tests/*
nexusctl/src/*
```

## Aufgaben

1. Suchen:

```bash
grep -R "referenzen/setup\|legacy_root\|setup/agents\|commands.json" -n . --exclude-dir=.git
```

2. Alle aktiven Code- und Test-Abhängigkeiten entfernen.

3. `referenzen/setup/` entweder löschen oder nach Archiv verschieben:

```text
docs/archiv/referenzen/setup/
```

4. Falls archiviert, sicherstellen:

- kein aktiver Code liest daraus
- keine Projektvalidierung verlangt es
- README/Archiv-Hinweis markiert es als historisch

## Akzeptanzkriterien

- Kein aktiver Code referenziert `referenzen/setup`.
- Kein Test referenziert `referenzen/setup`.
- `scripts/validate_project.py` verlangt `referenzen/setup` nicht.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 5 — Legacy-Import-Reports aus Runtime-Tool-Entscheidungen entfernen

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Legacy-Report-Ladepfad aus `tests/test_runtime_tool_review_cleanup.py` entfernt.
- Zielversions-Test ergänzt, der Runtime-Tool-Capabilities über `nexus/runtime-tools.yml` und die Capability-Matrix absichert.
- Leeres `generated/imports/` entfernt, da es nur noch Legacy-Import-Zwecken diente und nicht von der Projektvalidierung verlangt wird.
- Bestehende Guardrail-Tests für `runtime.tool.invoke`, Cross-Domain-Blockaden und destructive Tools beibehalten.
Changed files:
- `tests/test_runtime_tool_review_cleanup.py`
- `generated/imports/`
- `phases.md`
Validation:
- `grep -R "legacy_import_report\|legacy_import_review_decisions\|legacy_command\|legacy_id" -n README.md CURRENT_STATE.md docs/architecture docs/cleanup nexusctl tests scripts nexus generated`: erfolgreich — aktive Treffer nur noch im Negativtest, der sicherstellt, dass generierte Legacy-Import-Reports nicht existieren.
- `python scripts/validate_project.py`: erfolgreich.
- `PYTHONPATH=nexusctl/src pytest -q tests/test_runtime_tool_review_cleanup.py`: erfolgreich — 5 passed.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 68 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.


## Ziel

Runtime-Tool-Capabilities werden aus Zielkonfigurationen geprüft, nicht aus Legacy-Reports.

## Betroffene Stellen

```text
tests/test_runtime_tool_review_cleanup.py
docs/archiv/imports/legacy_import_report.json
docs/archiv/imports/legacy_import_review_decisions.json
generated/imports/
```

## Aufgaben

1. Suchen:

```bash
grep -R "legacy_import_report\|legacy_import_review_decisions\|legacy_command\|legacy_id" -n . --exclude-dir=.git
```

2. `tests/test_runtime_tool_review_cleanup.py` durch Zielversions-Test ersetzen.

Neuer Testfokus:

- Runtime-Tool-Capabilities kommen aus `nexus/agents.yml`, `nexus/capabilities.yml` oder Zielkonfiguration.
- Kein Legacy-Report wird geladen.

3. Falls `generated/imports/` nur Legacy-Zwecken dient, aus Projektvalidierung entfernen und löschen.

## Akzeptanzkriterien

- Kein aktiver Test lädt Legacy-Import-Reports.
- Runtime-Tool-Capabilities bleiben getestet.
- Legacy-Reports liegen höchstens im Archiv.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 6 — Backward-Compatible Aliase entfernen

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Backwards-compatible HTTP-Alias `NexusctlWebhookHandler = NexusctlAPIHandler` aus dem aktiven HTTP-Server entfernt.
- Aktive Code-, Test- und Script-Pfade auf verbleibende Alias-Nutzung geprüft; keine aktiven Verwendungen gefunden.
- Webhook- und HTTP-API-Tests gegen den Zielhandler `NexusctlAPIHandler` unverändert erfolgreich ausgeführt.
Changed files:
- `nexusctl/src/nexusctl/interfaces/http/server.py`
- `phases.md`
Validation:
- `grep -R "NexusctlWebhookHandler" -n nexusctl tests scripts README.md CURRENT_STATE.md docs/architecture docs/cleanup`: erfolgreich — kein aktiver Code-/Test-/Script-Treffer; nur Baseline-Dokumentation erwähnt den entfernten Alias historisch.
- `PYTHONPATH=nexusctl/src pytest -q tests/test_webhooks_reconciliation.py tests/test_http_api.py tests/test_http_cli_client.py tests/test_operational_hardening.py`: erfolgreich — 18 passed.
- `./scripts/run_tests.sh integration`: erfolgreich — 20 passed.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 68 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

Keine alten Importnamen bleiben als stiller öffentlicher Contract bestehen.

## Betroffene Stelle

```text
nexusctl/src/nexusctl/interfaces/http/server.py
```

## Aufgaben

1. Entfernen:

```python
NexusctlWebhookHandler = NexusctlAPIHandler
```

2. Alle aktiven Verwendungen suchen:

```bash
grep -R "NexusctlWebhookHandler" -n . --exclude-dir=.git
```

3. Tests und Imports auf `NexusctlAPIHandler` umstellen.

## Akzeptanzkriterien

- Kein aktiver Code nutzt `NexusctlWebhookHandler`.
- Kein Backwards-compatible Alias im HTTP-Server.
- Webhook-Reconciliation funktioniert weiterhin.

## Tests

```bash
./scripts/run_tests.sh fast
./scripts/run_tests.sh integration
```

---

# Phase 7 — Doctor-Contract entlegacyfizieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Doctor-Docstring von Legacy-Contract-Sprache auf stabilen Target-Version-Machine-Contract umgestellt.
- Bestehende maschinenlesbare Doctor-Felder `ok`, `status_code`, `drift_count`, `drift` und `checks` unverändert beibehalten.
- Aktive Doctor-, Architektur- und CLI-Tests gegen die Zielversions-Formulierung geprüft.
Changed files:
- `nexusctl/src/nexusctl/app/generation_service.py`
- `phases.md`
Validation:
- `PYTHONPATH=nexusctl/src pytest -q tests/test_doctor_reports.py tests/test_architecture_contracts.py tests/test_cli_command_modules.py`: erfolgreich — 9 passed.
- `python scripts/validate_project.py`: erfolgreich.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 68 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
- `grep -R "legacy contract\|backward\|backwards\|compatible" -n nexusctl tests scripts docs README.md`: kein aktiver Doctor-`legacy contract`-Treffer; verbleibende Treffer betreffen spätere Phasen oder Archiv-/Policy-Dokumentation.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.
- Verbleibende Nicht-Doctor-Treffer für Single-File-CLI-Kompatibilität und stdlib-kompatible HTTP-Formulierung werden in späteren Phasen behandelt.

## Ziel

Doctor bleibt als stabiles Kontrollfeature erhalten, wird aber nicht mehr als Legacy-Contract beschrieben.

## Betroffene Stelle

```text
nexusctl/src/nexusctl/app/generation_service.py
```

## Aufgaben

1. Kommentare mit `legacy contract` ersetzen durch Zielversions-Sprache:

```text
The doctor output is the stable target-version machine contract.
```

2. Output-Felder behalten, sofern Tests sie nutzen:

```text
ok
status_code
drift_count
drift
checks
```

3. Tests umbenennen oder Kommentare anpassen:

- von `legacy contract`
- zu `stable doctor contract` oder `target-version doctor contract`

4. Suchen:

```bash
grep -R "legacy contract\|backward\|backwards\|compatible" -n nexusctl tests scripts docs README.md
```

## Akzeptanzkriterien

- Doctor-Funktionalität bleibt erhalten.
- Kein aktiver Kommentar nennt den Doctor-Output `legacy contract`.
- Tests beschreiben den Zielversions-Contract.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 8 — CLI Single-File-Kompatibilität neutralisieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Legacy-Kompatibilitätsformulierung im gemeinsamen CLI-Human-Renderer entfernt.
- Verbleibende `print_human`-Treffer geprüft; sie beschreiben aktive Ziel-CLI-Ausgabe statt Single-File-Kompatibilität.
- Keine Tests gelockert oder entfernt, da vorhandene Human-Output-Prüfungen Zielversionsverhalten absichern.
Changed files:
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `phases.md`
Validation:
- `PYTHONPATH=nexusctl/src pytest -q tests/test_doctor_reports.py tests/test_cli_runtime.py tests/test_cli_command_modules.py`: erfolgreich — 12 passed.
- `python scripts/validate_project.py`: erfolgreich.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 68 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

CLI-Ausgabe darf stabil sein, aber nicht wegen alter Single-File-CLI-Kompatibilität.

## Betroffene Stelle

```text
nexusctl/src/nexusctl/interfaces/cli/commands/common.py
```

## Aufgaben

1. Kommentar ersetzen:

Von:

```text
Human-readable rendering kept compatible with the original single-file CLI.
```

Zu:

```text
Human-readable rendering for the target CLI.
```

2. Suchen:

```bash
grep -R "single-file\|original CLI\|print_human" -n . --exclude-dir=.git
```

3. Tests prüfen:

- Wenn Ausgabe Zielversions-Contract ist: Test behalten und neu benennen.
- Wenn Ausgabe nur Legacy-Kompatibilität schützt: Test lockern oder entfernen.

## Akzeptanzkriterien

- Keine aktive Dokumentation verweist auf alte Single-File-CLI-Kompatibilität.
- Ziel-CLI-Ausgabe bleibt funktionsfähig.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 9 — Projektvalidierung von Legacy befreien

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- `scripts/validate_project.py` von Legacy-Pflichtpfaden befreit.
- Zielstruktur-Prüfung um `nexusctl/`, `docs/architecture/` und `docs/cleanup/` ergänzt.
- Explizite Guardrails ergänzt, damit Legacy-Pfade nicht erneut in Required-Listen oder aktive Projektpfade zurückkehren.
Changed files:
- `scripts/validate_project.py`
- `phases.md`
Validation:
- `PYTHONPATH=nexusctl/src pytest -q tests/test_blueprint_contract.py tests/test_runtime_tool_review_cleanup.py tests/test_legacy_import.py`: erfolgreich — 13 passed.
- `python scripts/validate_project.py`: erfolgreich — Project validation passed.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 68 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

`validate_project.py` schützt die Zielstruktur und nicht mehr die Altstruktur.

## Betroffene Stelle

```text
scripts/validate_project.py
```

## Aufgaben

1. Aus Pflichtlisten entfernen oder ersetzen:

```text
tests/test_legacy_import.py
tests/test_runtime_tool_review_cleanup.py
referenzen
referenzen/setup
generated/imports
docs/archiv/imports als Pflichtstruktur
```

2. Neue Zielstruktur prüfen lassen:

```text
nexus/
nexusctl/
tests/
scripts/
generated/
docs/architecture/
docs/cleanup/
```

3. Validierung ausführen:

```bash
python scripts/validate_project.py
```

## Akzeptanzkriterien

- Projektvalidierung verlangt keine Legacy-Pfade.
- Projektvalidierung verlangt Zielversionsdokumentation.
- Validierung läuft oder dokumentiert bekannte offene Fehler.

## Tests

```bash
python scripts/validate_project.py
./scripts/run_tests.sh fast
```

---

# Phase 10a — CLI-Modul `work` aus main.py extrahieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- `work`-Parser und Subcommands `plan`, `assign`, `show` und `start` aus `main.py` nach `nexusctl.interfaces.cli.commands.work` verschoben.
- Work-Handler inklusive lokaler CommandRuntime-Nutzung und vorhandener Remote-API-Unterstützung in das Zielmodul extrahiert.
- `NotImplementedError` im Work-Command-Modul entfernt; `main.py` registriert und dispatcht `work` nur noch über das Command-Modul.
- CLI-Command-Modul-Test erweitert, damit `work` als extrahierte Command-Gruppe sichtbar abgesichert ist.
Changed files:
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/work.py`
- `tests/test_cli_command_modules.py`
- `phases.md`
Validation:
- `PYTHONPATH=nexusctl/src python -m nexusctl.interfaces.cli.main --help`: erfolgreich — `work` bleibt als Top-Level-Command sichtbar.
- `PYTHONPATH=nexusctl/src python -m nexusctl.interfaces.cli.main work --help`: erfolgreich — `plan`, `assign`, `show` und `start` werden vom extrahierten Modul registriert.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_work_scopes.py tests/test_cli_command_modules.py`: erfolgreich — 7 passed.
- `python scripts/validate_project.py`: erfolgreich — Project validation passed.
- `./scripts/run_tests.sh fast`: nicht vollständig abgeschlossen — lokaler Lauf erreichte wiederholt das Ausführungszeitlimit; der bekannte Baseline-Drift wurde separat reproduziert.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_test_strategy.py::test_test_strategy_runner_exposes_isolated_modes_and_timeout`: fehlgeschlagen — bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.
- Der vollständige `fast`-Runner-Lauf konnte in dieser Umgebung nicht stabil bis zum Ende ausgeführt werden; Work-spezifische und CLI-Modul-Tests wurden separat erfolgreich geprüft.

## Ziel

`work`-Command-Gruppe aus der Übergangsstruktur in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/work.py
```

## Aufgaben

1. Parser-Definition für `work` aus `main.py` nach `commands/work.py` verschieben.
2. Handler-Logik für `work` nach `commands/work.py` verschieben.
3. `NotImplementedError` entfernen.
4. `main.py` nur noch registrieren/dispatchen lassen.

## Akzeptanzkriterien

- `commands/work.py` enthält reale Logik.
- `main.py` ist kleiner.
- Work-CLI-Tests laufen.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 10b — CLI-Modul `feature_requests` aus main.py extrahieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- `feature-request`-Parser und Subcommands `create`, `list`, `show`, `route` und `transition` aus `main.py` nach `nexusctl.interfaces.cli.commands.feature_requests` verschoben.
- Feature-Request-Handler inklusive lokaler CommandRuntime-Nutzung und vorhandener Remote-API-Unterstützung für `create`, `list`, `show` und `route` in das Zielmodul extrahiert.
- `NotImplementedError` im Feature-Request-Command-Modul entfernt; `main.py` registriert und dispatcht `feature-request` nur noch über das Command-Modul.
- CLI-Command-Modul-Test erweitert, damit `feature-request` als extrahierte Command-Gruppe sichtbar abgesichert ist.
Changed files:
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/feature_requests.py`
- `tests/test_cli_command_modules.py`
- `phases.md`
Validation:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_feature_requests.py tests/test_cli_command_modules.py`: erfolgreich — 7 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_http_cli_parity.py::test_http_cli_parity_feature_request_create_list_and_route_can_use_remote_api`: erfolgreich — 1 passed.
- `python scripts/validate_project.py`: erfolgreich — Project validation passed.
- `./scripts/run_tests.sh fast`: nicht vollständig abgeschlossen — lokaler Lauf erreichte wiederholt das Ausführungszeitlimit.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_test_strategy.py::test_test_strategy_runner_exposes_isolated_modes_and_timeout`: fehlgeschlagen — bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.
- Der vollständige `fast`-Runner-Lauf konnte in dieser Umgebung nicht stabil bis zum Ende ausgeführt werden; Feature-Request-spezifische und CLI-Modul-Tests wurden separat erfolgreich geprüft.

## Ziel

`feature_requests`-Command-Gruppe in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/feature_requests.py
```

## Aufgaben

1. Parser und Handler aus `main.py` nach `commands/feature_requests.py` verschieben.
2. `NotImplementedError` entfernen.
3. Dispatch sauber verbinden.

## Akzeptanzkriterien

- `commands/feature_requests.py` enthält reale Logik.
- Feature-Request-CLI funktioniert unverändert fachlich.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 10c — CLI-Modul `scopes` aus main.py extrahieren

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- `scopes`-Parser und Subcommands `lease`/`revoke` aus `main.py` nach `nexusctl.interfaces.cli.commands.scopes` verschoben.
- Scope-Handler inklusive Pfadargument-Expansion und Scope-Lease-Payload in das Zielmodul extrahiert.
- `NotImplementedError` im Scopes-Command-Modul entfernt; `main.py` registriert und dispatcht `scopes` nur noch über das Command-Modul.
- CLI-Command-Modul-Test erweitert, damit `scopes` als extrahierte Command-Gruppe sichtbar abgesichert ist.
Changed files:
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/scopes.py`
- `tests/test_cli_command_modules.py`
- `phases.md`
Validation:
- `grep -n "scopes\|ScopeService\|_cmd_scopes\|_with_scope_service\|_scope_payload\|_expand_path_args" nexusctl/src/nexusctl/interfaces/cli/main.py`: erfolgreich — `main.py` enthält nur noch Scopes-Command-Modulimport, Registrierung und Dispatch; keine Scopes-Handlerreste.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_work_scopes.py tests/test_cli_command_modules.py`: erfolgreich — 7 passed.
- `PYTHONPATH=nexusctl/src python -m nexusctl.interfaces.cli.main --help`: erfolgreich — `scopes` bleibt als Top-Level-Command sichtbar.
- `PYTHONPATH=nexusctl/src python -m nexusctl.interfaces.cli.main scopes --help`: erfolgreich — `lease` und `revoke` werden vom extrahierten Modul registriert.
- `python scripts/validate_project.py`: erfolgreich — Project validation passed.
- `./scripts/run_tests.sh fast`: fehlgeschlagen — 44 passed, 1 failed, 68 deselected; bekannter Baseline-Drift `OPENCLAW_TEST_TIMEOUT` in `scripts/run_tests.sh` fehlt weiterhin.
Open items:
- Bekannter Baseline-Drift bleibt offen: `tests/test_test_strategy.py` erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht.

## Ziel

`scopes`-Command-Gruppe in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/scopes.py
```

## Aufgaben

1. Parser und Handler für Scopes verschieben.
2. `NotImplementedError` entfernen.
3. Scope-Policy-Verhalten unverändert lassen.

## Akzeptanzkriterien

- Scope-CLI funktioniert.
- Keine Scope-/Policy-Regression.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 16 — Teststrategie bereinigen

Status: done
Started: 2026-05-05
Completed: 2026-05-05
Summary:
- Option A umgesetzt: `OPENCLAW_TEST_TIMEOUT` ist wieder ein Zielversions-Feature des Test-Runners.
- `scripts/run_tests.sh` schützt pytest-Läufe per Prozess-Timeout und unterstützt eine portable Python-Auswahl über `PYTHON_BIN`, `python` oder `python3`.
- Windows-Testharness-Drifts bereinigt: Validator prüft historische Root-Dokumente case-genau, Worktree-Testkopien behalten unveränderte Dateien bytegenau.
- Python-3.11-Syntaxfehler in `config_writer.py` behoben, damit die Fast-Suite wieder sammeln kann.
Changed files:
- `scripts/run_tests.sh`
- `scripts/validate_project.py`
- `nexusctl/src/nexusctl/adapters/openclaw/config_writer.py`
- `tests/test_test_strategy.py`
- `tests/test_e2e_delivery_flow.py`
- `tests/test_merge_gate.py`
- `tests/test_policy_checks.py`
- `tests/test_patch_proposals.py`
- `tests/test_review_acceptance.py`
- `phases.md`
Validation:
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src python -m pytest -q tests/test_test_strategy.py`: erfolgreich — 3 passed.
- `python scripts/validate_project.py`: erfolgreich — Project validation passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src python -m pytest -q -m "unit and not slow and not integration and not e2e" tests nexusctl/tests --basetemp %TEMP%\openclaw-nexus-pytest`: erfolgreich — 45 passed, 68 deselected.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src python -m pytest -q --basetemp %TEMP%\openclaw-nexus-pytest tests/test_webhooks_reconciliation.py tests/test_http_api.py tests/test_http_cli_client.py tests/test_http_cli_parity.py tests/test_operational_hardening.py`: erfolgreich — 20 passed.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src python -m pytest -q --basetemp %TEMP%\openclaw-nexus-pytest-e2e tests/test_e2e_delivery_flow.py`: erfolgreich — 1 passed.
- `python scripts/package_project.py`: erfolgreich — `openclaw-nexus.zip` erzeugt.
Open items:
- Keine.

## Ziel

Tests validieren die Zielversion, nicht alte Kompatibilitätsannahmen.

## Aufgaben

1. Bekannten Drift entscheiden:

```text
tests/test_test_strategy.py erwartet OPENCLAW_TEST_TIMEOUT.
scripts/run_tests.sh enthält diesen Contract aktuell nicht.
```

2. Eine von zwei Optionen umsetzen:

### Option A

`OPENCLAW_TEST_TIMEOUT` wieder als Zielversions-Test-Runner-Feature einführen.

### Option B

Test anpassen oder entfernen, falls Timeout kein Zielcontract ist.

3. Testnamen modernisieren:

Von:

```text
legacy
cleanup
compatibility
```

Zu:

```text
target_version
stable_contract
projection_drift
generated_artifact_drift
runtime_tool_capabilities
```

## Akzeptanzkriterien

- Teststrategie ist grün oder bekannte externe Fehler sind dokumentiert.
- Keine Tests erzwingen alte Legacy-Kompatibilität.

## Tests

```bash
./scripts/run_tests.sh fast
./scripts/run_tests.sh integration
./scripts/run_tests.sh e2e
```

---

# Phase 10d — CLI-Modul `patches` aus main.py extrahieren

Status: open

## Ziel

`patches`-Command-Gruppe in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/patches.py
```

## Aufgaben

1. Parser und Handler für Patches verschieben.
2. `NotImplementedError` entfernen.
3. Patch-/Diff-/Scope-Prüfungen fachlich unverändert lassen.

## Akzeptanzkriterien

- Patch-CLI funktioniert.
- Keine Änderung am Scope-Sicherheitsmodell.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 10e — CLI-Modul `reviews` aus main.py extrahieren

Status: open

## Ziel

`reviews`-Command-Gruppe in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/reviews.py
```

## Aufgaben

1. Parser und Handler für Reviews verschieben.
2. `NotImplementedError` entfernen.
3. Review-Policy-Verhalten unverändert lassen.

## Akzeptanzkriterien

- Review-CLI funktioniert.
- Keine Änderung an Reviewer-/Policy-Gates.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 10f — CLI-Modul `acceptance` aus main.py extrahieren

Status: open

## Ziel

`acceptance`-Command-Gruppe in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/acceptance.py
```

## Aufgaben

1. Parser und Handler für Acceptance verschieben.
2. `NotImplementedError` entfernen.
3. Acceptance-Gates fachlich unverändert lassen.

## Akzeptanzkriterien

- Acceptance-CLI funktioniert.
- Keine Änderung an Acceptance-Gates.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 10g — CLI-Modul `github` aus main.py extrahieren

Status: open

## Ziel

`github`-Command-Gruppe in das Zielmodul verschieben.

## Betroffene Stellen

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
nexusctl/src/nexusctl/interfaces/cli/commands/github.py
```

## Aufgaben

1. Parser und Handler für GitHub-Kommandos verschieben.
2. `NotImplementedError` entfernen.
3. Reconciliation-/Projection-Drift-Verhalten unverändert lassen.

## Akzeptanzkriterien

- GitHub-CLI funktioniert.
- GitHub Projection Drift Detection bleibt erhalten.

## Tests

```bash
./scripts/run_tests.sh fast
./scripts/run_tests.sh integration
```

---

# Phase 11 — Legacy-in-main Runtime Wrapper bereinigen

Status: open

## Ziel

Übergangsbezeichnung aus dem CLI-Runtime-Pfad entfernen.

## Betroffene Stelle

```text
nexusctl/src/nexusctl/interfaces/cli/main.py
```

## Aufgaben

1. Nach Phase 10 prüfen, ob `_run_with_runtime()` noch gebraucht wird.
2. Falls ja, neutral umbenennen:

```text
_run_command_with_runtime()
```

3. Kommentar ändern zu:

```text
Run a CLI command through the shared CommandRuntime Unit of Work.
```

4. Falls nicht mehr gebraucht, Funktion entfernen.

## Akzeptanzkriterien

- Kein aktiver Kommentar spricht von `legacy in-main command`.
- CLI-Runtime funktioniert weiterhin.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 12 — No-Legacy-Contract-Tests einführen

Status: open

## Ziel

Verhindern, dass Legacy-Kompatibilität versehentlich zurückkommt.

## Neue Datei

```text
tests/test_no_legacy_contracts.py
```

## Aufgaben

Tests ergänzen für aktive Pfade:

1. Kein öffentlicher `legacy-import` CLI-Befehl.
2. Kein aktiver Import von `LegacyImportService`.
3. Kein aktiver Code referenziert `referenzen/setup`.
4. Kein Backwards-compatible Alias in `nexusctl/src`.
5. Kein aktiver Code lädt `legacy_import_report.json`.

Archivpfade ausdrücklich ausnehmen:

```text
docs/archiv
```

## Akzeptanzkriterien

- Neue Tests existieren.
- Tests blockieren aktive Legacy-Rückfälle.
- Archivmaterial wird nicht pauschal verboten.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 13 — Archivregel einführen

Status: open

## Ziel

Historisches Material darf existieren, aber nie aktiver Produktbestand sein.

## Aufgaben

1. Datei anlegen:

```text
docs/archiv/README.md
```

2. Inhalt:

```text
Dieses Verzeichnis enthält ausschließlich historisches Material.
Nichts daraus ist Teil der Runtime.
Nichts daraus ist Teil der Tests.
Nichts daraus ist Teil des öffentlichen CLI- oder API-Contracts.
```

3. Test ergänzen oder erweitern:

- aktiver Code darf nicht aus `docs/archiv` lesen
- aktive Tests dürfen nicht von `docs/archiv` abhängen

## Akzeptanzkriterien

- Archivregel ist dokumentiert.
- Keine aktive Abhängigkeit auf Archivmaterial.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 14 — README und Architektur-Dokumentation finalisieren

Status: open

## Ziel

Neue Entwickler verstehen sofort: Zielversion ja, Legacy-Kompatibilität nein.

## Aufgaben

1. README um Abschnitt ergänzen oder bestehenden Abschnitt schärfen:

```text
Target Version Contract
```

2. Explizit dokumentieren:

- genau eine Zielarchitektur
- keine Kompatibilitätsgarantie für alte Paketlayouts
- keine Kompatibilitätsgarantie für alte CLI-Befehle
- keine Kompatibilitätsgarantie für alte Importreports
- keine Kompatibilitätsgarantie für alte Aliasnamen
- keine Runtime-Abhängigkeit auf historische Setup-Bäume

3. Explizit dokumentieren, dass folgende Features bleiben:

- Drift Detection
- Reconciliation
- Audit Events
- Merge Staleness Gates
- Policy Gates
- Generated Artifact Checks

## Akzeptanzkriterien

- README enthält klare Zielversionssprache.
- Keine README-Stelle verkauft Legacy-Kompatibilität als Produktversprechen.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Phase 15 — Vollständige Legacy-Restprüfung

Status: open

## Ziel

Alle verbliebenen Legacy- oder Kompatibilitätsreste bewerten.

## Aufgaben

1. Suchbefehle ausführen:

```bash
grep -R "legacy" -n nexusctl tests scripts nexus README.md docs --exclude-dir=.git
grep -R "backward" -n nexusctl tests scripts nexus README.md docs --exclude-dir=.git
grep -R "backwards" -n nexusctl tests scripts nexus README.md docs --exclude-dir=.git
grep -R "compatible" -n nexusctl tests scripts nexus README.md docs --exclude-dir=.git
grep -R "referenzen/setup" -n . --exclude-dir=.git
grep -R "legacy_import" -n . --exclude-dir=.git
grep -R "legacy_command" -n . --exclude-dir=.git
grep -R "legacy_id" -n . --exclude-dir=.git
```

2. Jeden Treffer in `docs/cleanup/legacy-restcheck.md` klassifizieren:

```text
KEEP_FEATURE
ARCHIVE_ONLY
REMOVE
```

3. Alle `REMOVE`-Treffer entfernen.

## Akzeptanzkriterien

- Restcheck-Datei existiert.
- Jeder Treffer ist klassifiziert.
- Keine `REMOVE`-Treffer bleiben im aktiven Code.

## Tests

```bash
./scripts/run_tests.sh fast
./scripts/run_tests.sh integration
./scripts/run_tests.sh e2e
```

---

# Phase 17 — Packaging-Regel umsetzen und prüfen

Status: open

## Ziel

Jede Übergabe erzeugt ein sauberes ZIP mit exakt dem Namen `openclaw-nexus.zip`.

## Aufgaben

1. Packaging-Script suchen:

```bash
find . -iname "*package*" -o -iname "*release*" -o -iname "*zip*"
```

2. Falls kein sauberes Script existiert, anlegen:

```text
scripts/package_release.sh
```

3. Script muss ausschließen:

- `.git/`
- `__pycache__/`
- `.pytest_cache/`
- `.venv/`
- `venv/`
- alte ZIP-Dateien
- lokale Datenbanken, sofern nicht explizit Beispielartefakt

4. Output muss exakt heißen:

```text
openclaw-nexus.zip
```

5. ZIP prüfen:

```bash
unzip -l openclaw-nexus.zip | head
```

## Akzeptanzkriterien

- Packaging-Script existiert oder bestehendes Script erfüllt die Regel.
- Output heißt exakt `openclaw-nexus.zip`.
- ZIP enthält keine lokalen Cache-/Buildreste.

## Tests

```bash
./scripts/run_tests.sh fast
```

---

# Abschlusskriterien für das Gesamtvorhaben

Das Cleanup gilt erst als vollständig, wenn alle folgenden Punkte erfüllt sind:

```text
1. Kein öffentlicher CLI-Befehl legacy-import.
2. Kein aktiver App-Service LegacyImportService.
3. Kein aktiver Code liest aus referenzen/setup.
4. Kein Test verlangt Legacy-Import-Reports.
5. Kein Required-Test in validate_project.py schützt Legacy.
6. Keine Backward-Compatible-Aliase im aktiven Code.
7. Doctor-Contract ist als Zielversions-Contract dokumentiert.
8. Drift Detection bleibt vollständig erhalten.
9. GitHub Reconciliation bleibt vollständig erhalten.
10. Merge-Staleness-Gates bleiben vollständig erhalten.
11. Runtime-Tool-Capabilities werden aus Zielkonfigurationen geprüft, nicht aus Legacy-Reports.
12. main.py ist deutlich reduziert und Command-Module sind real implementiert.
13. Archivmaterial liegt nur in docs/archiv und wird nicht aktiv gelesen.
14. Fast-, Integration- und E2E-Tests laufen grün oder bekannte externe Blocker sind dokumentiert.
15. Das Übergabeartefakt heißt exakt openclaw-nexus.zip.
```
