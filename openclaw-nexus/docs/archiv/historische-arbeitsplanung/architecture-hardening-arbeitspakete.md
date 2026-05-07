# Archiv: Architecture-Hardening VP-00 bis VP-12

Diese Datei enthält die abgeschlossenen Detailabschnitte aus `phasen.md`, archiviert im Rahmen von VP-13.

## VP-00 – Dokumentationsbasis und neue Phasenplanung

Status: abgeschlossen  
Aufwand: erledigt im aktuellen Planungspaket

### Ziel

Die alte Greenfield-Phasenhistorie aus dem aktiven Phasendokument entfernen, archivieren und eine klare, saubere Verbesserungsplanung starten.

### Änderungen

- `README.md` wurde auf eine schlanke Projektübersicht mit Links zu Konzept und Phasensteuerung reduziert.
- `endzustand.md` wurde als stabiler Zielzustand eingeführt.
- `phasen.md` wurde als lebende Fortschrittsdatei eingeführt.
- Der alte Inhalt von `PHASES.md` wurde archiviert nach `docs/archiv/phasen/legacy-greenfield-phases-v1.md`.
- `PHASES.md` bleibt als Kompatibilitätsverweis bestehen, weil der Validator diese Datei erwartet.

### Akzeptanz

- Projekt enthält aktive Konzept- und Phasendateien.
- Alte Phasen verschmutzen die neue Phasensteuerung nicht mehr.
- Der bestehende Projektvalidator bleibt kompatibel.

---

## VP-01 – CLI-Kommandoschnitt vorbereiten und entkoppeln

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Problem

`nexusctl/src/nexusctl/interfaces/cli/main.py` ist zu groß und enthält Parser, Dispatching, Service-Wiring, Output-Formatierung und Command-Logik. Es existieren bereits Command-Module, aber viele sind nur Platzhalter.

### Ziel

Eine stabile Struktur schaffen, damit Folgphasen gefahrlos einzelne Commands aus `main.py` auslagern können, ohne Verhalten zu ändern.

### Arbeitsschritte

1. Neue Datei `nexusctl/src/nexusctl/interfaces/cli/runtime.py` anlegen.
2. Gemeinsame Helfer für DB-Verbindung, Projektwurzel, JSON-Ausgabe, Token/Subject-Auflösung und Commit/Rollback vorbereiten.
3. Neue Datei `nexusctl/src/nexusctl/interfaces/cli/output.py` anlegen.
4. Ausgabe-Helfer zentralisieren, aber zunächst nur dort nutzen, wo Risiko gering ist.
5. Command-Module mit klarer Signatur vorbereiten: `register(subparsers)` und `handle(args)`.
6. `main.py` nur minimal anfassen; keine fachlichen Änderungen.
7. Smoke-Tests für bestehende CLI-Kommandos laufen lassen.

### Akzeptanzkriterien

- Bestehende CLI-Kommandos funktionieren unverändert.
- `main.py` ist auf spätere Command-Auslagerung vorbereitet.
- Neue Runtime-/Output-Helfer sind testbar.
- Keine Business-Logik wird geändert.

### Umsetzung

- `nexusctl/src/nexusctl/interfaces/cli/runtime.py` bündelt Projektwurzel-, DB-, Token-, Auth- und Transaktionshelfer.
- `nexusctl/src/nexusctl/interfaces/cli/output.py` bündelt stabile JSON- und Fehlerausgabe.
- `main.py` delegiert risikoarme Helfer (`_open_ready_database`, `_resolve_token`, `_count`, `_safe_count`, `_print_json`) an die neuen Module.
- Alle bestehenden Command-Module besitzen jetzt vorbereitete `register(subparsers)`- und `handle(args)`-Hooks für VP-02.
- `tests/test_cli_runtime.py` sichert die neuen Runtime-/Output-Helfer ab.

### Validierung

- `PYTHONPATH=nexusctl/src pytest -q tests/test_cli_runtime.py` → 5 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_auth_identity.py` → 6 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_runtime_tools.py` → 5 bestanden.
- Der vollständige Testlauf wurde gestartet, lief in dieser Umgebung jedoch nicht stabil bis zum Prozessende durch.

### Erwartete Dateien

- `nexusctl/src/nexusctl/interfaces/cli/runtime.py`
- `nexusctl/src/nexusctl/interfaces/cli/output.py`
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `tests/test_cli_runtime.py` oder passende bestehende CLI-Tests
- `phasen.md`

---

## VP-02 – CLI-Domain-Kommandos aus `main.py` auslagern

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Die risikoärmeren CLI-Bereiche aus `main.py` in Command-Module verschieben.

### Umfang

- `me`
- `domains`
- `goals`
- `schedules`
- `generate`
- `doctor`

### Arbeitsschritte

1. Parser-Registrierung in die jeweiligen Command-Dateien verschieben.
2. Handler aus `main.py` extrahieren.
3. Gemeinsame Runtime-Helfer aus VP-01 verwenden.
4. Vorher/Nachher-Verhalten über bestehende Tests absichern.
5. `main.py` als zentralen Bootstrap behalten.

### Umsetzung

- `me`, `goals`, `schedules`, `generate` und `doctor` registrieren ihre Parser jetzt in den jeweiligen Command-Modulen.
- `domains` wurde als risikoarmer Read-only-Command für `list` und `show` ergänzt, weil der Bereich in VP-02 vorgesehen war, aber bisher nur als Platzhalter existierte.
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py` bündelt Parser-Helfer, Ausgabe und den kleinen authentifizierten Service-Lauf für extrahierte Commands.
- `main.py` bleibt Bootstrap und Router, delegiert die genannten Command-Gruppen aber an Module.
- Policy-, Storage- und Service-Verhalten wurden nicht fachlich geändert.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_runtime.py` → bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_command_modules.py` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_goals_evidence.py` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_openclaw_generation.py` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_schedules.py` → 1 bestanden.

### Akzeptanzkriterien

- Genannte Commands laufen weiterhin lokal.
- `main.py` verliert deutlich Umfang.
- Keine Änderung an Policy- oder Storage-Verhalten.

### Erwartete Dateien

- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/me.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/domains.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/goals.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/schedules.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/generate.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/doctor.py`
- `tests/test_cli_command_modules.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-03 – Zentrale CommandRuntime / Unit of Work einführen

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Wiederholtes Muster aus DB öffnen, Auth ableiten, CapabilityMatrix laden, Service bauen, committen oder rollbacken zentralisieren.

### Arbeitsschritte

1. `CommandRuntime` um Context-Manager-Verhalten erweitert.
2. Service-Factories für häufige Services eingeführt.
3. Commit/Rollback über eine zentrale Unit-of-Work-Grenze konsistent gemacht.
4. Extrahierte Commands und die verbleibenden Legacy-Helfer in `main.py` auf die neue Runtime umgestellt.
5. Tests für Rollback-, Commit- und Exception-Pfade ergänzt.

### Umsetzung

- `CommandRuntime` ist jetzt ein Context Manager, öffnet genau eine vorbereitete SQLite-Verbindung und authentifiziert die Session am Eintritt.
- `mark_success(commit=...)` entscheidet zentral, ob beim Verlassen committed oder für read-only Pfade gerollbackt wird. Exceptions erzwingen unabhängig davon Rollback.
- Häufige Service-Factories (`goal_service`, `feature_request_service`, `github_service`, `patch_service`, `schedule_service`, `generation_service` usw.) kapseln Connection-, Policy- und Project-Root-Wiring.
- `commands/common.py` nutzt die Runtime-Unit-of-Work für extrahierte Command-Module.
- `me` läuft über den neuen Runtime-Kontext.
- Die alten `_with_*_service`-Helfer in `main.py` wurden auf einen gemeinsamen `_run_with_runtime` reduziert.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_runtime.py` → 7 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_command_modules.py` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_goals_evidence.py` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_openclaw_generation.py` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_schedules.py` → 1 bestanden.

### Akzeptanzkriterien

- Bei Exceptions wird zuverlässig rollback ausgeführt.
- Mutierende Commands behalten ihr Event-/Persistenzverhalten.
- Verhalten bleibt kompatibel.

### Erwartete Dateien

- `nexusctl/src/nexusctl/interfaces/cli/runtime.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/me.py`
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `tests/test_cli_runtime.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-04 – Repository-Schicht für Goals und Feature Requests konsequent nutzen

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Direktes SQL aus `GoalService` und `FeatureRequestService` reduzieren und in Repositories verschieben.

### Arbeitsschritte

1. Bestehende Repository-Datei analysieren.
2. `GoalRepository` und `FeatureRequestRepository` ergänzen oder schärfen.
3. Service-Methoden schrittweise umstellen.
4. Event-Erzeugung unverändert lassen.
5. Regressionstests für Phase 5 und 6 laufen lassen.

### Akzeptanzkriterien

- Services enthalten weniger direktes SQL.
- Bestehende Phasen-Tests bleiben grün.
- Repository-Methoden sind klar benannt und fachlich lesbar.

### Umsetzung

- `GoalRepository` kapselt Lese- und Schreibzugriffe für Goals, Metriken, Evidenz, Messungen und Evaluationen.
- `FeatureRequestRepository` kapselt Dedupe-Lookups, Listenabfragen, Routing, Statusübergänge und Domain-Existenzprüfungen.
- `GoalService` und `FeatureRequestService` enthalten keine direkten `connection.execute`-Aufrufe mehr; Policy-Checks und Event-Erzeugung bleiben in der Service-Schicht unverändert sichtbar.
- Die bestehende Event-Semantik wurde beibehalten, insbesondere für `feature_request.created`, `feature_request.deduplicated`, `feature_request.routed`, `feature_request.transitioned`, `goal.measured` und `goal.evaluated`.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_goals_evidence.py` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_feature_requests.py::test_feature_requests_trading_strategist_creates_software_feature_request_from_auth_domain` → 1 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_feature_requests.py::test_feature_requests_source_domain_cannot_be_forged_via_goal_or_cli` → 1 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_feature_requests.py::test_feature_requests_nexus_can_route_and_transition_requests` → Testfall bestanden; der Prozess beendete sich in dieser Umgebung nicht sauber vor dem äußeren Timeout.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_feature_requests.py::test_feature_requests_dedupe_returns_existing_request_and_audits_it` → 1 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_command_modules.py` → 3 bestanden.

### Erwartete Dateien

- `nexusctl/src/nexusctl/storage/sqlite/repositories.py`
- `nexusctl/src/nexusctl/app/goal_service.py`
- `nexusctl/src/nexusctl/app/feature_request_service.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-05 – Repository-Schicht für Work, Patches, Reviews, Acceptance und Merge erweitern

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Die sicherheitskritischen Workflows stärker von SQL-Details trennen.

### Umfang

- Work Items
- Scope Leases
- Patch Proposals
- Reviews
- Acceptances
- Merge Records
- Policy Checks

### Akzeptanzkriterien

- Merge-Gate-Verhalten bleibt identisch.
- Scope- und Patch-Pfadprüfung bleibt unverändert streng.
- Tests für Phasen 8 bis 12 laufen weiterhin.


### Umsetzung

- `RepositoryContext` wurde um dedizierte Repositories für Patch-Proposals, Reviews, Acceptances, Policy-Checks und Merge-Records erweitert.
- `WorkItemRepository` und `ScopeLeaseRepository` kapseln jetzt die in VP-05 benötigten Lese- und Statuspfade.
- `WorkService`, `PatchService`, `ReviewService`, `AcceptanceService`, `PolicyCheckService` und `MergeService` nutzen die neue Repository-Schicht für die kritischen Schreib- und Gate-relevanten Lesepfade.
- Event-Erzeugung bleibt bewusst in der Service-Schicht sichtbar, damit Audit-Semantik und bestehende Event-Typen unverändert bleiben.
- GitHub bleibt Projektion: PR-/Check-/Review-/Label-Daten werden weiterhin aus Nexus-State abgeleitet, nicht als Autorität behandelt.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_work_scopes.py` → 4 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_patch_proposals.py` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_policy_checks.py` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_merge_gate.py` → beide Testfälle einzeln erfolgreich validiert.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_review_acceptance.py` → die ersten zwei Testfälle bestanden im Sammellauf; der Safety-Veto-Test wurde einzeln erfolgreich validiert. In dieser Umgebung beendet sich der kombinierte Sammellauf nicht zuverlässig vor dem äußeren Timeout, analog zu früher dokumentierten Test-Hängepfaden.

### Erwartete Dateien

- `nexusctl/src/nexusctl/storage/sqlite/repositories.py`
- `nexusctl/src/nexusctl/app/work_service.py`
- `nexusctl/src/nexusctl/app/patch_service.py`
- `nexusctl/src/nexusctl/app/review_service.py`
- `nexusctl/src/nexusctl/app/acceptance_service.py`
- `nexusctl/src/nexusctl/app/check_service.py`
- `nexusctl/src/nexusctl/app/merge_service.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-06 – HTTP/CLI-Parität entwerfen und ersten API-Client einführen

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Die gute Referenzidee eines API-Clients übernehmen, ohne die Referenzarchitektur mit Storage-God-Object zu kopieren.

### Arbeitsschritte

1. `nexusctl/src/nexusctl/interfaces/http/client.py` oder `interfaces/api_client.py` anlegen.
2. Basisfunktionen für Auth, Timeouts, JSON-Fehler und Healthcheck implementieren.
3. Einen kleinen Command optional über HTTP ausführbar machen, z. B. `me` oder `goals status`.
4. Lokalen Modus als Default behalten.

### Akzeptanzkriterien

- CLI funktioniert weiterhin lokal.
- Ein erster Command kann gegen HTTP laufen.
- HTTP-Fehler werden verständlich gemeldet.

### Umsetzung

- `nexusctl/src/nexusctl/interfaces/http/client.py` führt einen kleinen stdlib-basierten JSON-HTTP-Client ein.
- Der Client kapselt Bearer-Auth, Timeout-Konfiguration, Healthcheck, JSON-Parsing und verständliche HTTP-/Netzwerkfehler.
- `me` und `me capabilities` unterstützen jetzt optional `--api-url`; ohne `--api-url` bleibt der lokale SQLite-/CommandRuntime-Pfad unverändert der Default.
- Die Remote-Antworten werden in die bestehende CLI-Ausgabeform gebracht und mit `transport: http` markiert.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_http_cli_client.py` → 4 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_command_modules.py tests/test_http_api.py tests/test_http_cli_client.py` → 12 bestanden.

### Erwartete Dateien

- `nexusctl/src/nexusctl/interfaces/http/client.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/me.py`
- `tests/test_http_cli_client.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-07 – HTTP-Endpunkte erweitern und CLI optional remote-fähig machen

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

HTTP und CLI sollen dieselben App-Services und Policy-Prüfungen verwenden.

### Umfang

- Feature Request create/list/route
- Work plan/assign/start
- Policy check
- Review queue/submit
- Acceptance submit/status

### Umsetzung

- Der API-Client wurde um schmale Methoden für Feature Requests, Work, Policy Checks, Reviews und Acceptance erweitert.
- Authentifizierte CLI-Kommandos erhalten jetzt ein optionales `--api-url`/`--api-timeout`-Paar; ohne `--api-url` bleibt der lokale Modus unverändert Default.
- `feature-request create/list/show/route`, `work plan/assign/show/start`, `policy check`, `review queue/submit` und `acceptance submit/status` können gegen HTTP laufen.
- Die HTTP-Schicht delegiert weiterhin an dieselben App-Services wie die lokale CLI. Ergänzt wurden insbesondere `/policy/check` und `/work/{id}/start`.
- Remote-CLI-Ausgaben markieren `transport: http`, behalten aber die bestehenden Payload-Schlüssel bei.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_http_cli_parity.py` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_http_cli_client.py tests/test_http_cli_parity.py tests/test_http_api.py tests/test_feature_requests.py tests/test_work_scopes.py` → 19 bestanden.

### Akzeptanzkriterien

- HTTP nutzt keine eigene Business-Logik.
- CLI kann lokal oder remote arbeiten.
- Tests zeigen Parität für mindestens zwei kritische Workflows.

### Erwartete Dateien

- `nexusctl/src/nexusctl/interfaces/http/client.py`
- `nexusctl/src/nexusctl/interfaces/http/routes.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `tests/test_http_cli_parity.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-08 – Operational Hardening aus der Referenz übernehmen

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Die guten Betriebsdetails der Referenz selektiv übernehmen, ohne die bestehende stdlib-HTTP-Grenze durch ein Framework oder ein neues God-Object zu ersetzen.

### Umsetzung

- `nexusctl/src/nexusctl/interfaces/http/operational.py` bündelt HTTP-Betriebseinstellungen, sichere Defaults, TLS-/Remote-Binding-Prüfungen, zentrale Timeout-/Read-Retry-Konventionen und einen kleinen `SessionStore`.
- Der API-Server bindet per Default nur noch an `127.0.0.1`; Remote-Bindings ohne TLS werden blockiert, außer der Operator setzt explizit `NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND=1`.
- Request-Bodies werden vor dem Routing über `NEXUSCTL_API_MAX_BODY_BYTES` begrenzt und bei Überschreitung mit HTTP 413 abgelehnt.
- Der HTTP-Client validiert Remote-URLs: Plain HTTP ist nur für Loopback oder per explizitem `NEXUSCTL_API_ALLOW_INSECURE_REMOTE=1` erlaubt.
- Client-Timeouts und sichere GET-Retries sind zentral über `NEXUSCTL_API_TIMEOUT_SECONDS` und `NEXUSCTL_API_READ_RETRIES` konfigurierbar; mutierende Requests werden nicht retryt.
- CLI-API-Timeouts verwenden jetzt denselben zentralen Default und können weiterhin per `--api-timeout` überschrieben werden.
- Docker-Compose setzt die für das interne Container-Netz nötigen Insecure-Opt-ins explizit, statt Remote-Plain-HTTP implizit zu erlauben.

### Bewusst nicht übernommen

- Kein monolithisches `Storage`-God-Object.
- Keine Verlagerung der Lifecycle-Authority nach GitHub.
- Keine manuellen Runtime-Dateien als Wahrheit.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_operational_hardening.py tests/test_http_cli_client.py tests/test_http_cli_parity.py tests/test_http_api.py` → 17 bestanden.

### Akzeptanzkriterien

- Server startet weiterhin lokal sicher.
- Remote-Bindings sind ohne TLS blockiert oder nur per explizitem Operator-Opt-in möglich.
- Client-Timeouts sind zentral konfigurierbar.
- Request-Bodies sind begrenzt.
- Retries gelten nur für sichere Read-Operationen.

### Erwartete Dateien

- `nexusctl/src/nexusctl/interfaces/http/operational.py`
- `nexusctl/src/nexusctl/interfaces/http/server.py`
- `nexusctl/src/nexusctl/interfaces/http/client.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `nexusctl/src/nexusctl/interfaces/cli/main.py`
- `config/.env.example`
- `config/docker-compose.yml`
- `tests/test_operational_hardening.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-09 – GitHub-Adapter aus der Referenz härten

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Pragmatische GitHub-Hilfsfunktionen aus der Referenz übernehmen, aber GitHub weiterhin als Projektion behandeln.

### Kandidaten

- robuste GitHub-URL-Parser
- Review-State-Derivation
- Checks-State-Derivation
- Changed-Files-Policy-Helfer
- bessere MockGitHubClient-Abdeckung

### Akzeptanzkriterien

- GitHub-Parser sind unit-getestet.
- GitHub-State darf Nexus-State nicht autoritativ überschreiben.
- Reconciliation erzeugt Alerts bei unbekannter Drift.

### Umsetzung

- `nexusctl/src/nexusctl/adapters/github/hardening.py` ergänzt robuste Parser für gängige GitHub-URL-Formen.
- Externe GitHub-Review- und Check-Run-Zustände werden nur als nicht-authoritative Projektionszustände abgeleitet.
- Changed-Files-Policy-Helfer normalisieren Pfade und erkennen gesperrte beziehungsweise nicht geleaste Pfade.
- `MockGitHubClient` wurde durch Tests für PR-, Check-, Review- und Merge-Projektionen abgesichert; eine doppelte Review-Speicherung wurde bereinigt.
- Reconciliation bleibt Nexusctl-autoritativ: unbekannte externe Reviews erzeugen Alerts, ohne Nexus-Reviews zu schreiben.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_github_hardening.py` → 5 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_github_projection.py tests/test_webhooks_reconciliation.py tests/test_github_hardening.py` → 14 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_policy_checks.py::test_policy_checks_policy_check_reports_pending_required_gates_and_syncs_github_checks tests/test_policy_checks.py::test_policy_checks_changed_pr_head_sha_after_approval_blocks_policy_gate` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_review_acceptance.py::test_review_acceptance_software_reviewer_can_review_but_builder_cannot tests/test_review_acceptance.py::test_review_acceptance_trading_acceptance_completes_business_gate_not_technical_review tests/test_review_acceptance.py::test_review_acceptance_trading_sentinel_safety_veto_blocks_merge_gate` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_merge_gate.py::test_merge_gate_only_applier_merges_after_green_required_checks tests/test_merge_gate.py::test_merge_gate_merge_requires_synced_green_checks_and_no_critical_alerts` → beide Tests meldeten bestanden; der äußere Prozess lief in dieser Umgebung anschließend in den Timeout.
- `python3 scripts/validate_project.py` → bekannte Altvalidierung blockiert wegen Root-`completed_phase=20`/`next_phase`-Regel aus dem Greenfield-Plan; der Verbesserungsplan wird in `improvement_program` geführt.

### Erwartete Dateien

- `nexusctl/src/nexusctl/adapters/github/hardening.py`
- `nexusctl/src/nexusctl/adapters/github/client.py`
- `tests/test_github_hardening.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-10 – Runtime-Tools und importierte Review-Items bereinigen

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Die aus dem Legacy-Import offenen Review-Items bewusst entscheiden und sauber in Capabilities oder Runtime-Tool-Regeln überführen.

### Arbeitsschritte

1. `generated/imports/legacy_import_report.*` prüfen.
2. Offene Runtime-Tool-Kommandos klassifizieren.
3. `nexus/runtime-tools.yml` und `nexus/capabilities.yml` angleichen.
4. Tests für erlaubte und verbotene Tool-Aufrufe ergänzen.

### Umsetzung

- Die importierten Legacy-Kommandos `runtime_tools_list`, `runtime_tools_show` und `runtime_tools_check` wurden in `generated/imports/legacy_import_review_decisions.*` explizit entschieden.
- `runtime.tool.invoke` wurde als eigene Runtime-Grenzfähigkeit eingeführt und den Agenten zugewiesen, die Runtime-Tool-Guardrails nutzen dürfen.
- `nexus/runtime-tools.yml` referenziert die neue Guardrail-Fähigkeit über `runtime_tool_access_capability`.
- `RuntimeToolService` prüft zuerst die Runtime-Tool-Grenzfähigkeit und danach weiterhin konkrete Tool-Capability, Domain, Trading-MVP-Regeln, Live-Trade-Approval und destruktive Defaults.
- Die bestehenden Sperren für Trading-Agenten gegen Software-Tools und für destruktive Tools bleiben unverändert wirksam.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_runtime_tools.py tests/test_runtime_tool_review_cleanup.py` → 9 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_openclaw_generation.py tests/test_runtime_tools.py tests/test_runtime_tool_review_cleanup.py` → 11 bestanden.
- `timeout 30 python3 scripts/validate_project.py` → bestanden.

### Akzeptanzkriterien

- Keine unentschiedenen kritischen Runtime-Tool-Review-Items.
- Trading-Agenten können keine Software-Tools ausführen.
- Destruktive Tools bleiben standardmäßig blockiert.

### Erwartete Dateien

- `generated/imports/legacy_import_review_decisions.json`
- `generated/imports/legacy_import_review_decisions.md`
- `nexus/capabilities.yml`
- `nexus/agents.yml`
- `nexus/runtime-tools.yml`
- `nexusctl/src/nexusctl/app/runtime_tool_service.py`
- `tests/test_runtime_tool_review_cleanup.py`
- `phasen.md`
- `PROJECT_STATE.json`

---

## VP-11 – Teststrategie beschleunigen und blockierende Tests isolieren

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Die vollständige Test-Suite darf nicht unklar hängen. Es soll schnelle Feedback-Suites geben.

### Arbeitsschritte

1. Langsame oder blockierende Tests identifizieren.
2. Pytest-Marker einführen: `unit`, `integration`, `e2e`, `slow`.
3. `scripts/run_tests.sh` erweitern: fast, full, e2e.
4. Timeouts für riskante Tests ergänzen.
5. README nur bei bewusster Konzeptrevision ändern; laufende Testanweisungen bevorzugt in `phasen.md` oder dedizierte Testdocs.

### Akzeptanzkriterien

- Fast-Suite läuft zuverlässig.
- Full-Suite ist dokumentiert.
- Hängende Integrationspfade sind isoliert oder mit Timeout versehen.

### Umsetzung

- Pytest-Marker `unit`, `integration`, `e2e` und `slow` sind in `pytest.ini` registriert.
- `conftest.py` klassifiziert bekannte schnelle, Integrations-, E2E- und Slow/Legacy-Testpfade zentral während der Collection.
- `scripts/run_tests.sh` unterstützt `fast`, `unit`, `integration`, `slow`, `e2e` und `full`.
- Prozessweite Shell-Timeouts wurden später aus `scripts/run_tests.sh` entfernt; riskante Testpfade sollen lokal begrenzte Operationen und aussagekräftige Pytest-Diagnose verwenden.
- Die Integrations- und E2E-Modi verwenden konkrete Zielpfade, damit sie nicht durch die Sammlung langsamer Legacy-Tests blockieren.

### Validierung

- `./scripts/run_tests.sh fast` → 41 bestanden, 65 abgewählt.
- `./scripts/run_tests.sh integration -vv` → 20 bestanden.
- `./scripts/run_tests.sh e2e` → 1 bestanden.

---

## VP-12 – Doctor-, Audit- und Drift-Reports verbessern

Status: abgeschlossen  
Geschätzter Aufwand: ca. 4 Stunden

### Ziel

Architekturdrift, generierte Artefaktdrift, GitHub-Projektionsdrift und offene Alerts klar sichtbar machen.

### Arbeitsschritte

1. `doctor`-Ausgabe strukturieren.
2. JSON-Report erweitern.
3. Human-readable Summary ergänzen.
4. Audit-Kette von Goal bis Merge visualisieren oder tabellarisch ausgeben.
5. Tests für Drift-Fälle ergänzen.

### Akzeptanzkriterien

- `doctor --json` zeigt klare Statuscodes.
- Drift wird nicht nur erkannt, sondern handlungsorientiert erklärt.
- Kritische Alerts blockieren weiterhin Merge-Gates.

### Umsetzung

- `doctor` öffnet jetzt die migrierte lokale Datenbank read-only-artig über Rollback und reicht die Verbindung an den Report weiter.
- Der Doctor-JSON-Report behält die alten Felder (`ok`, `drift_count`, `drift`, `checks`) und ergänzt `status_code`, `status_codes`, `summary`, `alerts`, `github_projection` und `audit_chains`.
- Generierte Artefaktdrift erhält pro Eintrag einen stabilen Statuscode und eine konkrete Aktion zum Regenerieren und Prüfen.
- Offene GitHub-Alerts werden nach Schwere sortiert; kritische Alerts sind als `blocks_merge=true` sichtbar und machen den Doctor-Status kritisch.
- GitHub-Projektionsdrift prüft required Nexus-Policy-Checks gegen GitHub-Check-Run-Projektionen inklusive fehlender Projektionen und Head-SHA-Abweichungen.
- Die Human-Ausgabe fasst Doctor-Status, Artefaktdrift, GitHub-Projektion, Alerts und Audit-Chains kompakt zusammen.

### Validierung

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_doctor_reports.py` → 2 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_cli_command_modules.py` → 3 bestanden.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src pytest -q tests/test_openclaw_generation.py` → 2 bestanden.
- Ein größerer Sammellauf mit `tests/test_merge_gate.py` wurde in dieser Umgebung wegen Timeout abgebrochen; die VP-12- und betroffenen Doctor-/Generation-Tests liefen einzeln erfolgreich.

### Geänderte Dateien

- `nexusctl/src/nexusctl/app/generation_service.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/doctor.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/common.py`
- `tests/test_doctor_reports.py`
- `phasen.md`
- `PROJECT_STATE.json`

---
