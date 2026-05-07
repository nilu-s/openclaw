# Legacy-Removal Baseline

Stand: 2026-05-05

## Arbeitsstand

- Paketquelle: hochgeladenes Übergabeartefakt `openclaw-nexus.zip`.
- Git-Status: keine `.git`-Metadaten im Paket vorhanden; Branch und Commit sind lokal nicht ermittelbar.
- Aktiver Projektstand: Root-Dokumentation über `README.md`, `CURRENT_STATE.md` und Phasensteuerung über `phases.md`.
- Phase: Phase 0 — Baseline und Sicherheitsnetz einfrieren.

## Aktueller Testzustand

| Befehl | Ergebnis | Hinweis |
| --- | --- | --- |
| `./scripts/run_tests.sh fast` | fehlgeschlagen | 44 passed, 1 failed, 67 deselected; bekannter Baseline-Drift in `tests/test_test_strategy.py`: Test erwartet `OPENCLAW_TEST_TIMEOUT`, `scripts/run_tests.sh` enthält diesen Contract aktuell nicht. |
| `./scripts/run_tests.sh integration` | erfolgreich | 20 passed. |
| `./scripts/run_tests.sh e2e` | erfolgreich | 1 passed. |

## Bekannter Drift

`tests/test_test_strategy.py` erwartet aktuell den Contract `OPENCLAW_TEST_TIMEOUT`. `scripts/run_tests.sh` enthält diesen Contract nicht. Dieser Drift ist in `phases.md` für Phase 0 ausdrücklich als bekannter Ausgangszustand genannt und wurde in dieser Phase nicht behoben, weil Phase 0 keine Runtime-Code- oder Teständerungen vorsieht.

## Zu entfernende Legacy-Kompatibilitätsanker

Die folgenden Anker gelten als alte Kompatibilitätsversprechen und sollen in späteren Phasen entfernt, archiviert oder in Zielversionssprache überführt werden:

- öffentlicher CLI-Befehl `legacy-import`
- aktiver App-Service `LegacyImportService`
- aktive Runtime-, Test- oder Validierungsabhängigkeiten auf `referenzen/setup`
- Legacy-Import-Reports als aktive Entscheidungsquelle
- `generated/imports/`, sofern nur für Legacy-Import-Zwecke verwendet
- alte Agent-Aliase wie `AGENT_ALIASES`
- alte Command-Capability-Abbildungen wie `COMMAND_CAPABILITY_MAP`, sofern sie nur Legacy-Commands absichern
- backwards-compatible HTTP-Aliase wie `NexusctlWebhookHandler = NexusctlAPIHandler`
- Tests, die Legacy-Import als Pflichtvertrag oder Produktfeature absichern
- Kommentare oder Testnamen, die Zielcontracts als `legacy contract`, `backward compatible` oder alte Single-File-CLI-Kompatibilität beschreiben

## Zu erhaltende Kontrollfeatures

Die folgenden Mechanismen sind moderne Zielversionsfeatures und dürfen nicht als Legacy entfernt werden:

- Generated Artifact Drift Detection
- GitHub Projection Drift Detection
- Schedule-/Runtime-Drift-Checks
- Merge Staleness Gates
- Reconciliation Alerts
- Audit Events und append-only Event Store
- Policy Gates
- Doctor Output als stabiler Zielversions-Contract
- OpenClaw-Generierung aus Nexusctl als Source of Truth
- Scope Leases, Patch-Proposals, Reviews und Business-Acceptance als getrennte Kontrollpfade
- GitHub-Projektion als Kollaborationsfläche, nicht als Lifecycle-Authority

## Phase-0-Abgrenzung

In Phase 0 wurden ausschließlich Dokumentations- und Phasenstatusänderungen vorgenommen. Es wurden keine Legacy-Dateien gelöscht, keine CLI-Befehle entfernt, keine Tests umgeschrieben und keine Runtime-Code-Dateien verändert.
