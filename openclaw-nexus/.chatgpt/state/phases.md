# Sprint-Log

```yaml
sprint:
  schwerpunkt: Internal-Production-Recovery-Evidence und Cutover-Readiness
  ziel: >-
    OpenClaw Nexus besitzt einen wiederholbaren, secretfreien und maschinenlesbaren
    Preflight-/Recovery-Evidence-Nachweis für internal-production, der persistente
    Pfade, Doctor-Gates, Backup, Restore-Drill, Retention-/Offsite-Metadaten und
    operatorische Cutover-Entscheidungen zusammenführt.
  nicht_ziele:
    - Keine produktiven Secrets, Provider-Zugangsdaten oder kundenspezifischen Pfade im Repository ablegen.
    - Keine echte Offsite-/WORM-/Monitoring-Providerintegration als Pflichtbestandteil dieses Sprints.
    - Keine Ablösung von SQLite oder grundlegende Neuarchitektur der Control Plane.
    - Keine GitHub-Live-Sandbox-Ausführung gegen echte Infrastruktur innerhalb des Repositorys.
    - Keine Ausführung von Integration-, E2E- oder Slow-Tests ohne ausdrücklichen Nutzerauftrag.
  validierungsniveau: fast
  ausgabe: openclaw-nexus.zip
  aktuelle_phase: P2
```

## Sprint-Kandidaten und Auswahl

Aus den Analyse- und Leverage-Erkenntnissen ergeben sich mehrere sinnvolle Kandidaten:

| Kandidat | Nutzen | Risikoabbau | Empfehlung |
| --- | --- | --- | --- |
| K1 — Recovery-Evidence-/Preflight-Gate | Macht den wichtigsten Produktionsvertrag ausführbar und prüfbar. | Sehr hoch: schützt die autoritative SQLite-/Audit-Basis vor ungeprüftem Cutover. | Als aktiver Sprint gewählt. |
| K2 — Fast-/Doctor-Reproduzierbarkeit | Stabilisiert Vertrauen in CI-/Agentenläufe und isoliert Sandbox-Timeouts. | Hoch: verhindert falsche grüne oder rote Signale. | Als Phase P4 im Sprint enthalten. |
| K3 — GitHub-Live-Sandbox-Evidence | Belegt reale App-/Webhook-/Projektionsfähigkeit gegen GitHub. | Mittel-hoch: GitHub ist Projektion, aber operativ kritisch. | Als Phase P5 vorbereitet, ohne echte Infrastruktur im Repo. |
| K4 — Service-/Repository-Modularisierung | Senkt Änderungsrisiko in großen Kernmodulen. | Mittel: Wartbarkeit und Reviewbarkeit. | Folge-Sprint, falls Production-Gates grün sind. |
| K5 — Reviewbarer Schedule-Change-Request-Flow | Schließt eine fachliche Governance-Lücke für Schedule-Änderungen. | Mittel: Produktfähigkeit für Agenten-Cron-Änderungen. | Separater Produkt-Sprint. |
| K6 — Externe Audit-/WORM-/Offsite-Anbindung | Erhöht manipulationssichere Nachvollziehbarkeit. | Hoch, aber betreiber-/providerabhängig. | Betreiber-spezifischer Folge-Sprint. |

Aktiv gewählt wird K1, ergänzt durch K2 und vorbereitende Artefakte für K3, weil diese Kombination den größten kurzfristigen Production-Readiness-Hebel liefert, ohne Provider-Secrets oder externe Infrastruktur vorauszusetzen.

## P1 — Internal-Production-Preflight als ausführbaren Contract schneiden

Ziel:
- Es gibt einen klaren, wiederholbaren Preflight-Vertrag für internal-production, der `deployment_wizard`, persistente Pfade, `doctor --json` und Recovery-Evidence in eine operatorische Cutover-Checkliste beziehungsweise ein Script/Runbook zusammenführt.

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- `README.md`
- `docs/operations/internal-production.md`
- `docs/operations/deployment-strategy.md`
- `scripts/deployment_wizard.py`
- `nexusctl/src/nexusctl/app/generation_service.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/doctor.py`
- `tests/test_operational_hardening.py`
- `tests/test_doctor_reports.py`
- `tests/test_deployment_wizard.py`

Aufgaben:
- Den bestehenden internal-production-Betriebsvertrag auf konkrete Preflight-Schritte reduzieren: Env laden, persistente Pfade prüfen, Doctor ausführen, Restore-Drill vorbereiten, Evidence-Pfad festlegen.
- Entscheiden, ob der Preflight zuerst als Runbook-Erweiterung, als kleines Script oder als Wizard-Folgeartefakt umgesetzt wird; die kleinste ausführbare Variante bevorzugen.
- Prüfen, ob `deployment_wizard.py` bereits alle für den Preflight nötigen Werte ausgibt oder ob eine secretfreie Ergänzung nötig ist.
- Eine maschinenlesbare Preflight-Erwartung definieren: erwartete JSON-Felder, Statuscodes und Cutover-Blocker.
- Dokumentieren, dass ein grüner Preflight Voraussetzung für internal-production-Cutover ist.

Akzeptanzkriterien:
- Ein Operator kann aus aktiver Doku oder einem erzeugten Artefakt eindeutig ablesen, welche Befehle vor Cutover auszuführen sind.
- Fehlende persistente Pfade, fehlende Recovery-Evidence-Konfiguration, fehlende Retention- oder Offsite-Metadaten bleiben im internal-production-Profil sichtbar blockierend.
- Keine produktiven Secrets oder echten Offsite-Zugangsdaten werden im Repository festgeschrieben.
- Der Preflight-Vertrag unterscheidet klar zwischen lokaler Entwicklung und internal-production.
- Die relevanten Tests oder Contract-Dokumente spiegeln den neuen Preflight-Vertrag wider.

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh smoke`
- Fokussiert, falls geändert: `python -m pytest tests/test_operational_hardening.py tests/test_doctor_reports.py tests/test_deployment_wizard.py -q`
- Wenn die Umgebung genug Budget hat: `./scripts/run_tests.sh fast`

Erwartete Änderung am Current-State-Delta:
- Neue Fähigkeit: internal-production besitzt einen expliziten, wiederholbaren Preflight-Vertrag vor Cutover.
- Geänderte Grenze: Provider-Liveprüfungen bleiben Betreiberaufgabe, sind aber im Preflight als Nachweispflicht sichtbar.

Ergebnis:
- Status: abgeschlossen
- Umsetzung:
  - `doctor --json` enthält jetzt den maschinenlesbaren Abschnitt `internal_production_preflight` mit `status_code`, `command_sequence`, `expected_json_fields`, `recovery_evidence`, `external_operator_evidence_required` und `cutover_blockers`.
  - Fehlende produktionsrelevante Pfade, Recovery-Evidence-Konfiguration, Retention-/Offsite-Metadaten, Secret-/TLS-Gates oder andere kritische Readiness-Einträge blockieren den Preflight mit `status_code=blocked`.
  - Das Wizard-Bundle beschreibt den Internal-Production-Preflight explizit und verweist auf `nexusctl db init`, `nexusctl doctor --json` und `nexusctl db restore-drill --json --evidence-path ...`.
  - Die aktive Betriebs- und Deployment-Dokumentation beschreibt den Cutover-Preflight als Go/No-Go-Vertrag.
- Geänderte Dateien:
  - `nexusctl/src/nexusctl/app/generation_service.py`
  - `scripts/deployment_wizard.py`
  - `docs/operations/internal-production.md`
  - `docs/operations/deployment-strategy.md`
  - `tests/test_doctor_reports.py`
  - `tests/test_deployment_wizard.py`
  - `tests/test_runtime_tool_review_cleanup.py`
- Validierung:
  - `python scripts/validate_project.py` bestanden.
  - `python -m pytest tests/test_operational_hardening.py tests/test_doctor_reports.py tests/test_deployment_wizard.py -q` bestanden: 17 passed.
  - Smoke-Äquivalent mit Windows-Python bestanden: `python -m pytest tests/test_archive_policy.py tests/test_blueprint_contract.py tests/test_policy_contract.py tests/test_test_strategy.py tests/test_package_contract.py -q --durations=15`: 21 passed.
  - Direkter Fast-Schnitt mit Windows-Python bestanden: `python -m pytest -m "not integration and not slow and not timeout_risk" --durations=25`: 73 passed, 93 deselected.
  - `bash scripts/run_tests.sh smoke` konnte in dieser Windows/WSL-Mischumgebung nicht bis Pytest starten, weil die Bash-Schicht kein pytest-fähiges Python bereitstellt beziehungsweise Windows-Python nicht ausführen kann.
- Offene Punkte: keine produktbezogenen offenen Punkte aus P1; die Bash-Runner-Umgebung bleibt eine lokale Validierungsnotiz.

## P2 — Restore-Drill-Evidence-Pack härten

Ziel:
- Der Restore-Drill erzeugt ein secretfreies Evidence-Pack, das als Cutover- und Regelbetriebsnachweis verwendbar ist und Doctor-, Event-Chain-, Schema-, Count-, Retention- und Offsite-Metadaten nachvollziehbar verbindet.

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- `nexusctl/src/nexusctl/app/backup.py`
- `nexusctl/src/nexusctl/app/restore_drill_service.py`
- `nexusctl/src/nexusctl/app/generation_service.py`
- `nexusctl/src/nexusctl/interfaces/cli/commands/db.py`
- `docs/operations/internal-production.md`
- `tests/test_recovery_evidence.py`
- `tests/test_operational_hardening.py`

Aufgaben:
- Bestehende Restore-Drill-JSON-Ausgabe gegen die Leverage-Akzeptanzkriterien prüfen.
- Fehlende oder uneindeutige Evidence-Felder ergänzen, ohne lokale Pfade oder Secrets unnötig offenzulegen.
- Sicherstellen, dass `doctor_status`, `failed_checks`, `event_chain_status`, Counts, Schema-Version und Recovery-Evidence-Status konsistent berichtet werden.
- Tests ergänzen, die ein grünes und ein bewusst fehlkonfiguriertes internal-production-Evidence-Szenario abdecken.
- Doku so aktualisieren, dass Betreiber die JSON-Felder eindeutig als Go/No-Go-Signal lesen können.

Akzeptanzkriterien:
- `nexusctl db restore-drill --json --evidence-path <manifest.json>` schreibt ein Evidence-Manifest mit klarer `ok`-/`failed_checks`-Semantik.
- Ein grüner Drill enthält keine produktiven Secrets und keine Provider-Zugangsdaten.
- Fehlende Retention-/Offsite-/Recovery-Evidence-Angaben werden im internal-production-Kontext nicht stillschweigend als grün gewertet.
- Tests sichern sowohl den grünen Pfad als auch mindestens einen negativen Evidence-Fall ab.

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh smoke`
- Fokussiert: `python -m pytest tests/test_recovery_evidence.py tests/test_operational_hardening.py -q`
- Wenn die Umgebung genug Budget hat: `./scripts/run_tests.sh fast`

Erwartete Änderung am Current-State-Delta:
- Neue Fähigkeit: Restore-Drill-Evidence ist als secretfreies Cutover-/Recovery-Nachweisdokument nutzbar.
- Neue bekannte Grenze: Externe Provider-Quittungen werden weiterhin nur als Betreiber-Metadaten referenziert, nicht live verifiziert.

Ergebnis:
- Status: offen
- Geänderte Dateien: keine
- Offene Punkte: keine

## P3 — Deployment-Wizard und Doctor-Gates koppeln

Ziel:
- Der Deployment-Wizard erzeugt oder beschreibt die Werte so, dass `nexusctl doctor --json` im internal-production-Profil nach bewusst gesetzten Betreiberwerten reproduzierbar grün werden kann.

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- `scripts/deployment_wizard.py`
- `config/.env.example`
- `config/docker-compose.yml`
- `docs/operations/deployment-strategy.md`
- `docs/operations/internal-production.md`
- `nexusctl/src/nexusctl/app/generation_service.py`
- `tests/test_deployment_wizard.py`
- `tests/test_doctor_reports.py`
- `tests/test_docker_runtime.py`

Aufgaben:
- Wizard-Ausgaben auf Vollständigkeit für internal-production prüfen: Datenpfad, Backup-Pfad, Workspaces, Worktrees, Evidence-Pfad, Retention-Policy, Offsite-Control-Referenz.
- Ergänzen, falls Werte zwar im Doctor erwartet, aber nicht hinreichend im Wizard-Bundle vorbereitet oder erklärt werden.
- Doctor-Meldungen so prüfen oder verbessern, dass sie konkrete Betreiberaktion statt generischer Fehler liefern.
- ENV-Beispiele und Deployment-Doku angleichen, ohne produktive Defaults vorzutäuschen.
- Contract-Tests für Wizard-/Doctor-Kopplung ergänzen oder nachschärfen.

Akzeptanzkriterien:
- Ein mit dem Wizard erzeugtes internal-production-Bundle macht alle für Doctor-Readiness relevanten Betreiberwerte sichtbar.
- `doctor --json` liefert bei fehlenden Werten präzise Statuscodes und operatorische Hinweise.
- Nach bewusst gesetzten persistenten Pfaden und Betreiber-Metadaten ist ein grünes Doctor-Ergebnis reproduzierbar.
- Die Doku vermeidet die Fehlinterpretation, dass lokale Entwicklungskonfiguration produktionsgrün sei.

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh smoke`
- Fokussiert: `python -m pytest tests/test_deployment_wizard.py tests/test_doctor_reports.py tests/test_docker_runtime.py -q`
- Wenn die Umgebung genug Budget hat: `./scripts/run_tests.sh fast`

Erwartete Änderung am Current-State-Delta:
- Neue Fähigkeit: Wizard-Bundle und Doctor-Readiness bilden einen zusammenhängenden internal-production-Cutover-Pfad.
- Geänderte Grenze: TLS, Secret-Rotation, Monitoring, Offsite und WORM bleiben weiterhin externe Betreiberkontrollen, sind aber im Bundle/Doctor-Vertrag sichtbarer.

Ergebnis:
- Status: offen
- Geänderte Dateien: keine
- Offene Punkte: keine

## P4 — Fast-/Doctor-Reproduzierbarkeit und Timeout-Signale schärfen

Ziel:
- Die im Analyse-Lauf beobachteten Sandbox-/Harness-Timeouts werden nicht ignoriert, sondern als reproduzierbare Diagnose- und Dokumentationssignale behandelt, ohne bekannte riskante Läufe blind zu wiederholen.

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- `README.md`
- `.chatgpt/state/CURRENT_STATE.md`
- `scripts/run_tests.sh`
- `pytest.ini`
- `conftest.py`
- `tests/test_test_strategy.py`
- `tests/test_auth_identity.py`
- `tests/test_doctor_reports.py`

Aufgaben:
- Den aktuellen Timeout-Hinweis in README, Runner und State gegen die real beobachteten Signale prüfen: Smoke grün, Collect grün, einzelne Tests isoliert grün, aggregierte Läufe potentiell harness-sensitiv.
- Prüfen, ob `run_tests.sh debug` und Collect-only ausreichend dokumentiert sind, um vollständige Fast-Läufe in enger Sandbox sinnvoll einzugrenzen.
- Falls weiterhin nötig, gezielte Durations-/Faulthandler-/Debug-Hinweise ergänzen, ohne pauschal Tests zu quarantänisieren.
- Sicherstellen, dass `doctor --json` für development und internal-production fokussiert testbar bleibt.
- Nur bei konkret reproduziertem Test-Timeout den `timeout_risk`-Mechanismus gemäß Skill-Regel verwenden.

Akzeptanzkriterien:
- Smoke, Fast-Collect und fokussierte Doctor-/Auth-Tests sind als akzeptierte Sandbox-Diagnosepfade dokumentiert oder getestet.
- Kein Test wird ohne konkreten reproduzierten Timeout in `timeout_risk` verschoben.
- Die Dokumentation erklärt klar, wann ein äußerer Harness-Timeout kein Pytest-Fehler ist.
- Ein Entwickler kann aus den Hinweisen ableiten, wie ein lokaler oder CI-Fast-Lauf mit ausreichendem Budget zu prüfen ist.

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh smoke`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=nexusctl/src python -m pytest -m 'not integration and not slow and not timeout_risk' --collect-only -q`
- Fokussiert: `python -m pytest tests/test_test_strategy.py tests/test_auth_identity.py tests/test_doctor_reports.py -q`
- Wenn die Umgebung genug Budget hat: `./scripts/run_tests.sh fast`

Erwartete Änderung am Current-State-Delta:
- Geänderte Grenze: vollständige Fast-Läufe können in engen Harnesses weiterhin durch äußere Limits abbrechen; das Projekt bietet dafür klare Diagnosepfade.
- Neue Fähigkeit: Timeout-/Doctor-Reproduzierbarkeit ist besser operationalisiert.

Ergebnis:
- Status: offen
- Geänderte Dateien: keine
- Offene Punkte: keine

## P5 — GitHub-Live-Sandbox-Evidence als Folge-Gate vorbereiten

Ziel:
- Nach grünem Recovery-Evidence-Gate gibt es ein klares, secretfreies Evidence-Format und Runbook für eine echte GitHub-App-/Webhook-/Repo-Sandbox-Verifikation, ohne diese Infrastruktur im Repository auszuführen.

Aufwand:
- ca. 4 Stunden für einen erfahrenen Entwickler

Kontext:
- `docs/operations/internal-production.md`
- `docs/operations/deployment-strategy.md`
- `nexus/github.yml`
- `nexusctl/src/nexusctl/adapters/github/*`
- `nexusctl/src/nexusctl/app/reconciliation_service.py`
- `tests/test_webhooks_reconciliation.py`
- `tests/test_github_hardening.py`
- `tests/test_github_projection.py`

Aufgaben:
- Das bestehende GitHub-Live-Sandbox-Gate auf konkrete Evidence-Felder zuschneiden: App-Konfiguration, Delivery-ID, HMAC-Verifikation, PR-Projektion, Check-/Review-Signale, Label-/Status-Drift und Unauthorized-Merge-Probe.
- Secretfreie Evidence-Vorlage oder Doku-Tabelle ergänzen.
- Klarstellen, dass GitHub weiterhin Projektion bleibt und keine Lifecycle-Authority wird.
- Prüfen, ob Fixture- und Reconciliation-Tests das Runbook ausreichend stützen oder ob ein zusätzlicher Contract-Test für Evidence-Struktur sinnvoll ist.
- Den Zusammenhang zwischen grünem Recovery-Evidence-Gate und anschließendem GitHub-Live-Gate dokumentieren.

Akzeptanzkriterien:
- Operatoren können die Live-Sandbox außerhalb des Repositorys ausführen und secretfreie Evidence nach einem definierten Schema archivieren.
- Das Runbook nennt klare Go/No-Go-Kriterien für HMAC, Idempotenz, PR-/Check-/Review-Projektion und Drift-Alert-Verhalten.
- GitHub wird ausdrücklich nicht zur Lifecycle-Authority aufgewertet.
- Tests oder Doku sichern, dass GitHub-Live-Evidence erst nach grünem internal-production-Recovery-Gate sinnvoll ist.

Validierung:
- `python scripts/validate_project.py`
- `./scripts/run_tests.sh smoke`
- Fokussiert: `python -m pytest tests/test_webhooks_reconciliation.py tests/test_github_hardening.py tests/test_github_projection.py -q`
- Wenn die Umgebung genug Budget hat: `./scripts/run_tests.sh fast`

Erwartete Änderung am Current-State-Delta:
- Neue Fähigkeit: GitHub-Live-Sandbox-Evidence ist als Folge-Gate nach Recovery-Evidence vorbereitet.
- Bekannte Grenze bleibt: echte GitHub-Infrastruktur wird nicht aus dem Repository heraus verifiziert.

Ergebnis:
- Status: offen
- Geänderte Dateien: keine
- Offene Punkte: keine

## Folge-Sprint-Kandidaten

- Repository-Schicht nach Aggregaten trennen, insbesondere `nexusctl/src/nexusctl/storage/sqlite/repositories.py`.
- `GenerationService` und `ReconciliationService` weiter in kleinere Doctor-/Generation-/Pipeline-Bausteine schneiden.
- Reviewbaren Schedule-Change-Request-Flow als Produktfunktion planen und implementieren.
- Betreiber-spezifische Monitoring-/Pager-, Secret-Rotation-, Offsite-/WORM- und externe Audit-Signatur-Anbindungen ergänzen.
- GitHub-Event-Fixtures bei jeder neuen unterstützten Event-Klasse ausbauen.

## Current-State-Delta

Neue Fähigkeiten:
- Internal-production besitzt einen expliziten, wiederholbaren Preflight-Vertrag vor Cutover.
- `doctor --json` macht den Preflight maschinenlesbar: erwartete JSON-Felder, Befehlsfolge, Recovery-Evidence-Anforderung, externe Betreiber-Evidence und konkrete Cutover-Blocker sind sichtbar.
- Das Deployment-Wizard-Bundle und die aktive Betriebsdokumentation geben Operatoren einen eindeutigen Preflight-Ablauf vor.

Geänderte Grenzen:
- Provider-Liveprüfungen bleiben Betreiberaufgabe, sind aber im Preflight als Nachweispflicht sichtbar.
- Ein grüner lokaler Doctor-/Preflight-Vertrag ersetzt weiterhin keine echte Offsite-, WORM-, Monitoring-, TLS-/Proxy- oder Secret-Management-Providerprüfung.

Entfernte oder bereinigte Bestandteile:
- Stale Fast-Test-Erwartungen auf die alten Agent-IDs `nexus` und `nexus-applier` wurden auf den aktuellen Zielvertrag `control-router` und `merge-applier` korrigiert.

Neue bekannte Risiken:
- Der vollständige `fast`-Lauf kann in engen Agent-/Sandbox-Harnesses weiterhin durch äußere Prozesslimits abbrechen; die Sprintphasen müssen diese Timeout-Policy beachten und dürfen riskante Läufe nicht blind wiederholen.
- Ein grünes Repository-Evidence-Pack ersetzt keine echte Offsite-/WORM-/Monitoring-/Secret-Management-Providerprüfung.

Empfohlene nächste Arbeiten:
- Mit `Führe die nächste Phase aus.` P2 umsetzen: Restore-Drill-Evidence-Pack härten.
- Nach Abschluss von P2 und P3 entscheiden, ob P4 oder P5 zuerst den größeren verbleibenden Risikobeitrag senkt.
