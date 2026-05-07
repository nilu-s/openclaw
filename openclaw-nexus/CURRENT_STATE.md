# Aktueller Ist-Zustand: OpenClaw Nexus

Stand: 2026-05-05

## Zusammenfassung

OpenClaw Nexus liegt als funktionsfähiger MVP mit zusätzlicher Architekturhärtung vor. Das Projekt enthält eine Python-basierte Nexusctl-Control-Plane mit CLI, HTTP-API, SQLite-Persistenz, Policy-Gates, GitHub-Projektion, Reconciliation, OpenClaw-Artefaktgenerierung, Runtime-Tool-Guardrails und Audit-Events.

Die Dokumentationsstruktur wurde bereinigt. Es gibt im Root nur noch diese aktiven Dokumentationsdateien:

- `README.md`
- `CURRENT_STATE.md`

Historische Planungsstände liegen unter `docs/archiv/` und sind nicht mehr maßgeblich.

## Umgesetzte Fähigkeiten

- Blueprint-, Domain-, Agent-, Capability-, Policy-, Goal- und Schedule-Konfiguration über `nexus/*.yml`.
- Capability-basierte Autorisierung über `nexusctl.authz`.
- SQLite-Kern mit Schema, Migrationen, Repositories und append-only Event Store.
- Authentifizierung über Token Registry und Session-Modell.
- Goal-, Evidence-, Measurement- und Evaluation-Workflows.
- Cross-Domain Feature Requests mit Routing und Dedupe.
- Work Items und path-/zeitbegrenzte Scope Leases.
- Patch-Proposals mit Scope-Prüfung und PR-Projektion.
- Policy Checks, Review, Business Acceptance, Safety Veto und Merge Gate.
- GitHub-App-Abstraktion mit Mock-Client, Projektionsstatus und Webhook-Reconciliation.
- OpenClaw-Generierung für Agenten, Skills, Allowlists, Tool Policies, Schedules und Runtime-Konfiguration.
- HTTP-API mit Operational-Hardening-Basis, Body-Limit, sicheren Defaults und optionaler Remote-CLI-Nutzung.
- Docker-Konfiguration für Nexusctl und OpenClaw-Runtime.
- Legacy-Import-Review als auditierbarer, nicht automatisch übernommener Prozess.
- Doctor-/Audit-/Drift-Reports für Betriebsdiagnose.
- Architektur-Kontrakt-Tests für Schnittstellengrenzen und Generated-Artefakte.

## Teststruktur

Die Tests sind fachlich benannt und von historischen Umsetzungsabschnitten entkoppelt. Beispiele:

- `tests/test_blueprint_contract.py`
- `tests/test_policy_contract.py`
- `tests/test_storage_sqlite.py`
- `tests/test_auth_identity.py`
- `tests/test_feature_requests.py`
- `tests/test_merge_gate.py`
- `tests/test_webhooks_reconciliation.py`
- `tests/test_openclaw_generation.py`
- `tests/test_e2e_delivery_flow.py`
- `tests/test_architecture_contracts.py`

Die Testauswahl erfolgt über Marker und Runner-Modi:

- `fast`: schnelle Unit-Tests ohne langsame Integrationspfade
- `unit`: alle fachlichen Unit-Tests
- `integration`: HTTP-, CLI-over-HTTP-, Webhook- und Betriebsgrenzen
- `slow`: bewusst langsamere oder breitere Tests
- `e2e`: End-to-End-Produktfluss
- `full`: kompletter Testlauf

## Bekannte Grenzen

- Die HTTP-API ist MVP-tauglich, aber für produktiven Betrieb weiterhin hinter Reverse Proxy, TLS, Secret Management und Monitoring zu betreiben.
- Die SQLite-Schicht ist funktional, aber einige Repository- und Service-Module sind noch groß und sollten weiter aufgeteilt werden.
- Reconciliation ist fachlich kritisch und sollte perspektivisch nach Webhook-/Projektionsarten modularisiert werden.
- Der Event Store ist fachlich append-only; zusätzliche technische Härtung über Hash-Chain, Exportprüfung oder DB-Trigger-Policy kann die Audit-Festigkeit erhöhen.
- Die GitHub-Integration ist stark mock- und projektionsorientiert; für Realbetrieb braucht es zusätzliche Contract-Tests mit echten GitHub-Payload-Fixtures.

## Empfohlene nächste Arbeiten

1. Testlaufzeiten messen und langsame Tests weiter isolieren.
2. CLI-Einstieg weiter als reinen Router halten und verbliebene Command-Logik auslagern.
3. `reconciliation_service.py` nach Verantwortlichkeiten aufteilen.
4. Repository-Schicht weiter nach Aggregaten trennen.
5. Betriebsdokumentation für Backup, Restore, Secrets, TLS, Deployments und Monitoring ergänzen.
6. Event-Store-Integrität technisch stärker absichern.
7. GitHub-App-Produktionspfad mit Payload-Fixtures und Fehlerfalltests erweitern.

## Archivierung

Die früheren Planungs- und Statusdateien wurden archiviert:

- `docs/archiv/historische-planung/`
- `docs/archiv/historische-arbeitsplanung/`
- `docs/archiv/konzept/`
- `docs/archiv/readme/`

Diese Dateien dienen nur als Historie und werden nicht von Validator, Testklassifizierung oder aktiver Dokumentation vorausgesetzt.
