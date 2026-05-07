# Aktueller Ist-Zustand: OpenClaw Nexus

Stand: 2026-05-07

## Zusammenfassung

OpenClaw Nexus liegt als produktionsorientierte interne Control Plane mit Betriebs-, Audit-, GitHub-Webhook- und Recovery-Evidence-Härtung vor. Das Projekt enthält eine Python-basierte Nexusctl-Control-Plane mit CLI, HTTP-API, SQLite-Persistenz, Policy-Gates, GitHub-Projektion, Webhook-Reconciliation, OpenClaw-Artefaktgenerierung, Runtime-Tool-Guardrails, manipulationserschwerender Audit-Event-Chain sowie Backup-/Restore- und Recovery-Evidence-Werkzeugen.

Der zuletzt abgeschlossene Sprint hat die größten Production-Readiness-Risiken aus der Systemanalyse bearbeitet: Reconciliation-Wartbarkeit, Timeout-Risk-Teststrategie, GitHub-Live-Sandbox-Verifikation sowie Monitoring-/Recovery-/Operator-Control-Grenzen. Die neue Zielversion behandelt diese Punkte als aktuellen geprüften Zustand; alte Zwischenstände bleiben nur Archivhistorie.

Die aktive Dokumentation ist produktionsneutral aufgebaut und enthält zusätzlich den abgeschlossenen Sprach- und Architekturvertrag für Systemgrenzen, Agentenbenennung und Authority-Flows:

- `README.md`
- `.chatgpt/state/CURRENT_STATE.md`
- `.chatgpt/skills/sprint-workflow/SKILL.md` (reproduzierbarer Sprint-Workflow-Skill mit klarer Modusstruktur, ca. 4-Stunden-Phasenschnitt, Akzeptanzkriterien, Clear-Up-Funktion, verpflichtendem LLM-Doublecheck und ZIP-Übergabe)
- `.chatgpt/state/phases.md` (aktueller Sprint-Log; leer, wenn kein Sprint aktiv ist)

Historische Planungsstände und abgeschlossene Sprint-Logs liegen unter `docs/archiv/` und sind nicht maßgeblich für Runtime, Tests, API, CLI oder Packaging.

Für zukünftige Produktions-Sprints gilt: Die aktuelle Zielversion zählt. Es gibt keinen Kompatibilitätszwang für alte Versionen; lokale DB-Inhalte dürfen bei Schema- oder Strukturkorrekturen verloren gehen, wenn dadurch ein sauberer Zielzustand entsteht.

`.chatgpt/state/CURRENT_STATE.md` beschreibt nur den zuletzt abgeschlossenen und geprüften Projektzustand. Während eines aktiven Sprints ist `.chatgpt/state/phases.md` die Live-Arbeitsstandsdatei. Vor dem Sprintabschluss führt der ausführende LLM-Agent einen verpflichtenden Abschluss-Doublecheck durch: Er liest den tatsächlichen Ist-Zustand aus Code, Tests, aktiver Dokumentation, Scripts und Konfiguration, gleicht ihn mit dem `Current-State-Delta` aus `.chatgpt/state/phases.md` ab und aktualisiert erst danach `.chatgpt/state/CURRENT_STATE.md`. Anschließend wird `.chatgpt/state/phases.md` nach `docs/archiv/sprints/` archiviert und geleert.

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
- Secretfreie, realitätsnahe GitHub-Payload-Fixtures für `issues`, `pull_request`, `pull_request_review` und `check_run` unter `tests/fixtures/github/`.
- Fixture-basierte GitHub-Normalizer-Contracts für Repository-Full-Name, Issue-/PR-Nummern, Labels, Review-State, Check-State, Head-SHA und Merge-State.
- Negative Webhook-Verträge: fehlende oder ungültige Signaturen, fehlende Delivery-/Event-Header, kaputtes JSON, unbekannte Event-Typen sowie Duplicate-/Conflict-Delivery-Fälle werden kontrolliert und secretfrei behandelt.
- Webhook-Persistenz nutzt den aktiven Statusvertrag `pending`, `processed`, `alerted`, `ignored`, `dead_letter`; Reconciliation verarbeitet nur ausstehende Deliveries und vermeidet Replays bereits verarbeiteter Events.
- Reconciliation erkennt produktionsnähere GitHub-Drift-Szenarien aus Fixtures: PR-Head-SHA-Drift, Unauthorized Merge, Label-Drift, externe Reviews und externe Check-Fehler.
- Externe GitHub-Reviews und Check-Ergebnisse sind Signale oder Alerts, aber keine Nexus-Review-, Acceptance- oder Merge-Authority.
- GitHub-Reconciliation ist modularer prüfbar: Payload-/Header-nahe Normalisierung, Drift-Analyse und Alert-Erzeugung sind aus `reconciliation_service.py` in `reconciliation_payloads.py`, `reconciliation_drift.py` und `reconciliation_alerts.py` ausgelagert und durch eigene Contract-Tests abgesichert.
- OpenClaw-Generierung für Agenten, Skills, Allowlists, Tool Policies, Schedules und Runtime-Konfiguration.
- Sprach- und Architekturvertrag in aktiver Produkt- und Betriebsdokumentation: `OpenClaw Nexus` bleibt Projekt-/Authority-Kontext, `nexusctl` ist die autoritative Control-Software, Control Config und Control Store sind Source-of-Truth-Flächen, und generierte OpenClaw Runtime Config ist abgeleitet.
- Agentenbenennung ist aktiv konsolidiert: alle aktiven Agent Display Names enden mit `Agent`; die früher missverständlichen Control-Agent-IDs `nexus` und `nexus-applier` wurden zu `control-router` und `merge-applier` migriert.
- Authority-Grenzen für Config, Schedules und Runtime-Artefakte sind in Doku, Blueprint, Policies, Capabilities, Schedule-/Runtime-Tool-Guardrails, Generator-Adaptern und Contract-Tests geschärft: Agents dürfen Requests, Proposals und erlaubte Runs erzeugen, aber keinen autoritativen State direkt mutieren.
- HTTP-API mit Operational-Hardening-Basis, Body-Limit, sicheren Defaults und optionaler Remote-CLI-Nutzung.
- Docker-Konfiguration für Nexusctl und OpenClaw-Runtime.
- Doctor-/Audit-/Drift-Reports für Betriebsdiagnose.
- Automatisierter lokaler Restore-Drill über `nexusctl db restore-drill`, der Backup-Erstellung oder externen Backup-Pfad, Restore in eine frisch erzeugte Drill-DB, Doctor-Prüfung und maschinenlesbaren Recovery-Report bündelt.
- Recovery-Evidence-Vertrag für Restore-Drills: JSON-serialisierbarer, secretfrei sanitiserter Evidence-Payload mit Drill-Status, Backup-/Restore-Pfaden, Schema-/Event-Chain-Prüfung, Doctor-Status, fehlgeschlagenen Checks sowie Offsite-/Retention-Status als Betreiberkontrollfelder.
- Recovery Evidence enthält `operator_control_boundaries` als secretfreien Grenzvertrag zwischen lokaler Produkt-Evidence, externen Betreiberkontrollen und Incident-Triggern.
- `nexusctl db restore-drill --json` liefert einen `recovery_evidence`-Abschnitt; `--evidence-path <datei>` schreibt ein archivierbares Manifest atomar und lehnt bestehende Manifestdateien ohne `--overwrite-evidence` kontrolliert ab.
- Fehlerfälle bei defekten, leeren oder manipulationsverdächtigen Backup-Dateien liefern nicht-grüne Recovery-Evidence ohne Secret-Leaks.
- Doctor-Report mit maschinenlesbarer `operational_readiness`-Liste, Event-Chain-Integrität, geprüfter Event-Anzahl, DB-Schema-/Migrationsstand und Betriebswarnungen ohne Secret-Leaks.
- Im internen Produktionsprofil enthält `operational_readiness` stabile Readiness-IDs für Recovery-Evidence-Verzeichnis, Backup-Retention-Policy, Offsite-Backup-Control, Monitoring-/Alert-Runbook und operatorverwaltete Kontrollen; fehlende Konfiguration wird kritisch sichtbar, bleibt in `development` aber nicht blockierend.
- `nexusctl doctor --json` enthält den maschinenlesbaren Abschnitt `github_webhook_contract` mit unterstützten Event-Klassen, fixture-abgedeckten Events, negativen Webhook-Verträgen, Processing-Statusmodell, Authority-Regel und `live_sandbox_verification`-Evidence-Vertrag.
- Die GitHub-Live-Sandbox-Verifikation ist als secretfreies Operator-Runbook vorbereitet: echte GitHub-App-/Repository-Prüfung mit Webhook-Delivery, PR-Projektion, Review-Signal, Check-Run-Signal, Label-Drift, Unauthorized Merge und negativer Signaturprobe.
- Im internen Produktionsprofil macht `operational_readiness` fehlende Webhook-Secrets, unsichere Remote-Bindings, fehlende persistente Pfade, fehlende oder unsichere GitHub-Webhook-Fixture-Abdeckung, fehlende Monitoring-/Alert-Verträge und nicht belegte Betreibergrenzen sichtbar.
- Technisch manipulationserschwerender Event Store: Events enthalten `prev_hash` und `event_hash`, werden deterministisch verkettet und können über `EventStore.verify_integrity()` geprüft werden.
- SQLite-Migrationen ergänzen bestehende lokale Events um Hash-Chain-Felder; Append-only-Trigger verhindern direkte Updates und Deletes auf Events.
- CLI-gestützte Integritätsprüfung über `nexusctl doctor`, inklusive Erkennung manipulierter Events mit konkretem Fehlerhinweis.
- CLI-gestützte SQLite-Betriebswerkzeuge: `nexusctl db backup`, `nexusctl db restore-check`, `nexusctl db restore` und `nexusctl db restore-drill`.
- Backup-Erstellung nutzt die SQLite-Backup-API, prüft die gesicherte Datenbank und protokolliert Metadaten sowie Audit-Event.
- Restore-Check prüft SQLite-Integrität, Schema-/Migrationsstand, Checksumme, Kernobjekt-Counts und Event-Chain.
- Restore schreibt in eine neue lokale DB oder überschreibt nur mit explizitem `--overwrite`.
- Restore-Drill schreibt ausschließlich in frisch erzeugte Drill-Datenbanken, bietet keinen nutzerdefinierten Restore-Zielpfad und keinen Overwrite-Schalter und berichtet `ok`, `backup_path`, `restored_db`, `checked_events`, `schema_version`, `counts`, `doctor_status` und `failed_checks`.
- README und Konfiguration unterscheiden lokale Entwicklung von internem Produktionsbetrieb; unsichere Entwicklungs-Opt-ins bleiben möglich, gelten aber nicht als produktionsgrün.
- Aktive Betriebsdokumentation beschreibt den GitHub-Webhooks-/Reconciliation-Betriebsvertrag als aktuellen Produktzustand: Secrets, HMAC-Prüfung, Delivery-Idempotenz, unterstützte Event-Klassen, Statusmodell, Alert-Reaktion, GitHub-Live-Sandbox-Gate und Nicht-Authority von GitHub.
- Aktive Deployment-Strategie unter `docs/operations/deployment-strategy.md` beschreibt Umgebungen, Artefakte, Zieltopologie, Secret-/Persistenzregeln, Rollout, Smoke-Checks, Rollback, Monitoring, GitHub-Live-Sandbox-Gate und nächste Deployment-Arbeiten.
- `scripts/deployment_wizard.py` erzeugt ein reviewbares Deployment-Bundle mit profilbezogener Environment-Datei, Docker-Compose-Override, sicher generiertem Webhook-Secret, wählbarer Named-Volume- oder Host-Mount-Strategie und Bootstrap-Helfer für DB-gebundene Operator-Tokens.
- Aktive Betriebsdokumentation schreibt den Restore-Drill als Vor-Inbetriebnahme- und Nach-Restore-Nachweis vor und definiert, welche JSON-Felder Betreiber für einen grünen Drill prüfen müssen.
- Betriebs- und Deployment-Dokumentation beschreiben den Recovery-Evidence-Pack-Vertrag inklusive Backup-Frequenz, Restore-Drill-Frequenz, Evidence-Manifest-Archivierung, Offsite-Kopie, Retention, Operator-Control-Boundaries und Incident-Schwellen.
- Monitoring-/Alert-Reaktion ist als Betriebsvertrag dokumentiert: Doctor-/Readiness-Alarme, GitHub-Reconciliation-Alerts, Restore-Drill-/Recovery-Evidence-Alarme, Offsite-/Retention-Alarme sowie TLS-/Secret-Alarme haben Trigger, Sofortreaktion und Abschlusskriterium.
- Der Deployment-Wizard erzeugt Recovery-Evidence-, Retention- und Offsite-Metadaten in reviewbaren Artefakten, ohne produktive Provider-Secrets im Repository festzuschreiben.
- Architektur-Kontrakt-Tests für Schnittstellengrenzen und Generated-Artefakte.
- Die ehemals pauschal quarantänisierten Tests `tests/test_auth_identity.py`, `tests/test_cli_command_modules.py` und `tests/test_goals_evidence.py` laufen wieder im Standard-Fast-/Unit-Schnitt. `scripts/run_tests.sh timeout-risk` ist bei leerer Timeout-Risk-Liste ein erfolgreicher No-op.
- Neutraler Sprint-Workflow als ChatGPT-/Agent-Skill für wiederholbare Änderungssprints. `.chatgpt/skills/sprint-workflow/SKILL.md` enthält keine fachliche Roadmap, ist in Aktivierung, Modi, Phasenvorlage, Validierung und Abschluss strukturiert und schreibt ca. 4 Stunden Arbeitsaufwand je Phase für einen erfahrenen Entwickler vor. Konkrete Sprint-Inhalte und Logs gehören ausschließlich in `.chatgpt/state/phases.md`.

## Teststruktur

Die Tests sind fachlich benannt und von historischen Umsetzungsabschnitten entkoppelt. Beispiele:

- `tests/test_blueprint_contract.py`
- `tests/test_policy_contract.py`
- `tests/test_storage_sqlite.py`
- `tests/test_auth_identity.py`
- `tests/test_feature_requests.py`
- `tests/test_merge_gate.py`
- `tests/test_webhooks_reconciliation.py`
- `tests/test_github_hardening.py`
- `tests/test_reconciliation_modularization.py`
- `tests/test_doctor_reports.py`
- `tests/test_recovery_evidence.py`
- `tests/test_http_api.py`
- `tests/test_operational_hardening.py`
- `tests/test_openclaw_generation.py`
- `tests/test_e2e_delivery_flow.py`
- `tests/test_architecture_contracts.py`
- `tests/test_target_version_contracts.py`
- `tests/test_runtime_tool_contract.py`
- `tests/test_docker_runtime.py`
- `tests/test_deployment_wizard.py`

Die Testauswahl erfolgt über Marker und Runner-Modi:

- `unit`: Standardauswahl ohne `integration`, `slow` und `timeout_risk`.
- `smoke`: kleinster reproduzierbarer Contract-Lauf für Agent-/Sandbox-Prüfungen.
- `fast`: Alias für dieselbe schnelle Auswahl wie `unit`.
- `integration`: HTTP-, CLI-over-HTTP-, Webhook- und Betriebsgrenzen.
- `slow`: bewusst langsamere oder breitere Tests.
- `timeout-risk`: bekannte Timeout-Kandidaten mit `timeout_risk`-Marker; aktuell sind keine Timeout-Risk-Dateien registriert, daher ist der Modus ein erfolgreicher No-op.
- `all`: kompletter Pytest-Lauf ohne Marker-Einschränkung.
- `debug`: ausführlicher Debug-Lauf mit Faulthandler und Full Trace.
- `ci`: CI-orientierter Lauf mit Strict-Marker-Prüfung.

Der zuletzt geprüfte Abschlusszustand wurde nach der Production-Readiness-Härtung validiert mit:

- `python scripts/validate_project.py` — bestanden.
- `./scripts/run_tests.sh smoke` — bestanden, 21 Tests.
- Direkter Fast-Collect-Lauf mit `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=... python -m pytest -m 'not integration and not slow and not timeout_risk' --collect-only` — bestanden, 65 Tests selektiert und 93 abgewählt.
- Fokussierte Reconciliation-, Recovery-Evidence- und Test-Strategy-Contracts — bestanden, 10 Tests.

Hinweis zur Reproduzierbarkeit: In begrenzten Agent-/Sandbox-Harnesses kann der vollständige `fast`-Lauf und können einzelne subprocess-/Doctor-nahe Testläufe durch den äußeren Prozess-Timeout beendet werden, obwohl `scripts/run_tests.sh` selbst keinen Shell-Timeout setzt. Für solche Umgebungen ist `smoke` der dokumentierte Mindest-Contract; der vollständige `fast`-Lauf bleibt lokal oder in CI mit ausreichendem Zeitbudget auszuführen.

## Bekannte Grenzen

- Die HTTP-API ist für den internen Produktionsbetrieb vorbereitet und bleibt verpflichtend hinter Reverse Proxy, TLS, Secret Management und Monitoring zu betreiben.
- Interner Produktionsmodus prüft Betriebsbedingungen und macht Verstöße sichtbar, erzwingt aber kein vollständiges Deployment-, TLS- oder Secret-Management.
- `github_webhook_contract` ist lokale Contract-/Ops-Sichtbarkeit und ersetzt keine echte GitHub-App-/Repository-Liveverifikation; die Live-Sandbox-Verifikation ist als Operator-Runbook und Evidence-Vertrag vorbereitet, aber nicht im Repository gegen echte GitHub-Infrastruktur ausgeführt.
- Event-Typen außerhalb der ausgewählten Fixture-Abdeckung können weiterhin ungetestete GitHub-Sonderformen enthalten.
- Fixture-Payloads müssen secretfrei und wartbar bleiben; echte Produktionsdaten dürfen nicht ungeprüft übernommen werden.
- Backup-Dateien sind lokale SQLite-Snapshots. Der lokale Restore-Drill und das Recovery-Evidence-Manifest sind aktive Produktbestandteile; Verschlüsselung, Offsite-Replikation, Aufbewahrungsrichtlinien und externe Recovery-Infrastruktur sind verpflichtende Betreiberaufgaben für produktionsreife Umgebungen.
- Offsite- und Retention-Felder in Recovery-Evidence und Doctor-Readiness sind Betreiberkontrollen beziehungsweise Metadaten; sie ersetzen keine Provider-Liveprüfung, keine Upload-Quittung und kein externes Secret Management.
- Monitoring-/Alert-Runbook und Operator-Control-Boundaries sind lokal dokumentiert und maschinenlesbar sichtbar, aber nicht an ein echtes Monitoring-System, Pager, Offsite-Provider, WORM/Object-Lock oder Secret-Management-System angebunden.
- Event-Hashing macht Manipulationen an der SQLite-Audit-Historie erkennbar, ersetzt aber keine extern signierten Audit-Exporte, WORM-Speicher oder Offsite-Backups.
- Backup/Restore muss sorgfältig zwischen laufender SQLite-Nutzung und Offline-Restore unterschieden werden.
- Die SQLite-Schicht ist funktional, aber einige Repository- und Service-Module sind noch groß und sollten weiter aufgeteilt werden.
- Reconciliation ist fachlich kritisch und muss trotz modularisierter Normalisierung, Drift-Analyse und Alert-Erzeugung weiterhin durch Webhook-/Authority-Contracts abgesichert werden.
- Der vollständige `fast`-Lauf kann in engen Agent-/Sandbox-Harnesses weiterhin durch äußere Prozesslimits abbrechen; `smoke`, `fast --collect-only` und fokussierte Contract-Läufe sind dort die dokumentierten Mindest-/Zusatzsignale.
- Externe lokale Datenbanken, Tokens oder Skripte außerhalb dieses Repositorys können noch alte Agent-IDs wie `nexus` oder `nexus-applier` referenzieren; das Repository selbst behandelt die neue Zielversion als maßgeblich und erzwingt keine Altversions-Kompatibilität.
- Es gibt weiterhin kein vollständiges Produkt für reviewbare Schedule-Change-Requests; Agents können Änderungsbedarf formulieren oder erlaubte Runs auslösen, produktive Cron-/Schedule-Mutationen bleiben aber `nexusctl`-kontrolliert.

## Empfohlene nächste Arbeiten

1. Vollständigen `fast`-Lauf lokal oder in CI mit ausreichendem Zeitbudget regelmäßig messen und langsame Tests weiter isolieren.
2. GitHub-Live-Sandbox-Runbook extern gegen echte Sandbox-App und Test-Repository durchführen und secretfreie Evidence archivieren.
3. Betreiber-spezifische Monitoring-/Alert-Checks, Secret-Rotation, Offsite-/WORM-Provider-Evidence und externe Audit-Signaturen implementieren.
4. Optional einen separaten Produkt-Sprint für reviewbare Schedule-Change-Request-Flows planen, wenn Agents Cronjob- oder Schedule-Änderungen aktiv beantragen sollen.
5. CLI-Einstieg weiter als reinen Router halten und verbliebene Command-Logik auslagern.
6. Repository-Schicht weiter nach Aggregaten trennen.
7. Betreiber-spezifische Produktionsmanifeste aus dem Wizard-Bundle ableiten sowie Reverse-Proxy-/TLS-Beispiele, Monitoring-Runbooks, Secret-Rotation, Offsite-Backups und Retention-Policies vertiefen.
8. Event-Store-Integrität durch externe Signatur, Exportprüfung oder Offsite-Audit-Snapshots weiter absichern.
9. Bei neuen GitHub-Event-Klassen Fixture-, Normalizer- und Reconciliation-Contracts ergänzen.
10. Für den nächsten Sprint `.chatgpt/state/phases.md` direkt aus dem Nutzerauftrag und dem geprüften Projektzustand befüllen. Den Skill `.chatgpt/skills/sprint-workflow/SKILL.md` nur als neutrales Protokoll verwenden, nicht als Quelle für fachliche Sprint-Inhalte.

## Archivierung

Archivierte Dateien dienen nur als Historie. Sie werden nicht von Validator, Testklassifizierung oder aktiver Dokumentation vorausgesetzt.
