# Lokale Entwicklung

## Projektvalidierung

```bash
python scripts/validate_project.py
```

## Testläufe

Der empfohlene Standardlauf ist ein schneller Unit-Lauf. Er schließt Integrationstests, Slow-Tests und timeout-anfällige Tests aus und zeigt die 25 langsamsten Tests an:

```bash
./scripts/run_tests.sh
./scripts/run_tests.sh smoke
./scripts/run_tests.sh unit
./scripts/run_tests.sh unit -k doctor
```

Weitere bewusst gewählte Modi:

```bash
./scripts/run_tests.sh integration
./scripts/run_tests.sh slow
./scripts/run_tests.sh timeout-risk
./scripts/run_tests.sh all
./scripts/run_tests.sh ci
```

Einzelne Tests oder zusätzliche Pytest-Argumente werden nach dem Modus weitergereicht:

```bash
./scripts/run_tests.sh integration tests/test_doctor_reports.py
./scripts/run_tests.sh debug tests/test_doctor_reports.py::test_name
```

Der Debug-Modus aktiviert `PYTHONFAULTHANDLER=1`, `python -X faulthandler`, `-vv`, `-s`, `--full-trace` und `--durations=50`. Er ist der bevorzugte Einstieg, wenn ein einzelner Test hängt oder nur schwer zu diagnostizieren ist.

```bash
./scripts/run_tests.sh debug --collect-only
./scripts/run_tests.sh debug tests/test_doctor_reports.py::test_name
```

Für Agent-/Sandbox-Prüfungen ist `./scripts/run_tests.sh smoke` der kleinste reproduzierbare Contract-Lauf. Der Runner setzt keinen äußeren Shell-Timeout mehr um den Pytest-Prozess. Wenn ein Lauf mit einer Meldung wie `command failed because it timed out` endet, kommt diese Meldung von einer äußeren Ausführungsumgebung wie CI, Sandbox, Editor-Agent oder Terminal-Harness, nicht von `scripts/run_tests.sh`.

Timeouts sollen lokal und aussagekräftig sein. Tests oder Produktionscode, die Subprozesse, Locks, Watcher, Sleeps oder andere hängergefährdete Operationen nutzen, sollen eigene Timeouts verwenden, zum Beispiel `subprocess.run(..., timeout=30, capture_output=True, text=True, check=False)` oder `proc.communicate(timeout=30)` mit sauberem `proc.kill()` im Timeout-Fall. So ist im Fehlerfall sichtbar, welche Operation und welcher Test betroffen waren.

Vollständige Repository-Kopien sind langsam und werden nur für Integrationstests verwendet, die tatsächlich die reale Projektstruktur benötigen. Bevorzugt werden zentrale Fixtures in `tests/conftest.py`:

- `minimal_project` für kleine, isolierte Projektstrukturen in Unit-Tests.
- `repo_project_copy` für explizite Integrationstests mit echter Repository-Struktur.

Tests mit echten Projektlayouts, Dateisystem-Flows, CLI-Flows oder längeren Abläufen sollen mit `integration`, `slow` oder `timeout_risk` markiert werden. Der Standardlauf bleibt dadurch schnell und deterministisch, während vollständige Diagnose mit `debug` oder vollständige Ausführung mit `all` bewusst gewählt werden kann.

## Lokale Recovery-Evidence-Probe

Für lokale Betriebsproben kann ein Restore-Drill inklusive Evidence-Manifest in temporäre oder lokale Verzeichnisse geschrieben werden. Das ist ein Entwicklungsnachweis, keine echte Offsite-Absicherung:

```bash
nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --evidence-path "$NEXUSCTL_RECOVERY_EVIDENCE_DIR/restore-drill-evidence.json" --json
```

In `development` darf `NEXUSCTL_OFFSITE_BACKUP_ENABLED=0` bleiben. Für `internal-production` meldet `doctor --json` fehlende Recovery-Evidence-, Retention- oder Offsite-Konfiguration als Operational-Readiness-Problem.

OpenClaw-Artefakte werden aus der Control Config in `nexus/*.yml` über `nexusctl` erzeugt und liegen unter `generated/*`. Sie beschreiben den Runtime-Zustand, der von OpenClaw konsumiert werden kann, sind aber nicht die Source of Truth. Schedule-Artefakte unter `generated/openclaw/schedules/*` sind ebenfalls generierte Runtime Config; Cron-Änderungen erfolgen über `nexus/schedules.yml` und Nexusctl-Generation beziehungsweise Schedule-Flows, nicht durch manuelle Runtime-Edits.
