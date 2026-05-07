# Deployment-Strategie

Diese Strategie beschreibt einen pragmatischen Deployment-Pfad für OpenClaw Nexus vom lokalen Betrieb über interne Staging-Umgebungen bis zum internen Produktionsbetrieb. Sie ergänzt die bestehende Betriebsdokumentation und ersetzt nicht die produktiven Sicherheits-, Monitoring- und Backup-Entscheidungen des Betreibers.

## Zielbild

OpenClaw Nexus wird als interne Control Plane betrieben. `nexusctl` bleibt die Lifecycle-Authority für Ziele, Feature Requests, Work Items, Patch Proposals, Reviews, Acceptance, Merge-Gates, GitHub-Projektionen, Runtime-Generierung und Audit-Events. GitHub bleibt Kollaborations- und Projektionsfläche. OpenClaw konsumiert generierte Runtime-Artefakte, aber mutiert keinen autoritativen Nexus-State.

Das Deployment soll diese Eigenschaften sichern:

- reproduzierbare Releases aus Repository-Stand, Control Config und generierten Artefakten;
- getrennte Umgebungen für Entwicklung, Staging und internen Produktionsbetrieb;
- persistente SQLite-Datenbank, Backups, Recovery-Evidence-Manifeste, Workspaces und Repo-Worktrees;
- TLS-/Reverse-Proxy-Boundary für Remote-Zugriffe;
- verpflichtende Doctor-, Restore-Drill- und Smoke-Checks vor produktiver Freigabe;
- klare Rollback- und Recovery-Pfade ohne direkte Mutation des Audit-Event-Stores.

## Umgebungen

### Lokale Entwicklung

Zweck: schnelle Entwicklung, Tests, Feature-Arbeit und lokale Contract-Prüfung.

Profil:

- `NEXUSCTL_DEPLOYMENT_MODE=development`
- Docker Compose darf lokale unsichere Opt-ins verwenden, damit Container untereinander per Plain HTTP sprechen können.
- Keine echten Produktionssecrets verwenden.
- SQLite-DB und Volumes dürfen kurzlebig sein.

Freigabekriterien vor Merge oder Übergabe:

```bash
python scripts/validate_project.py
./scripts/run_tests.sh fast
```

Für breitere Änderungen zusätzlich:

```bash
./scripts/run_tests.sh integration
./scripts/run_tests.sh ci
```

### Interne Staging-Umgebung

Zweck: release-nahe Probe mit produktionsähnlicher Konfiguration, aber isolierten Daten, Test-Secrets und separater GitHub-App beziehungsweise separatem Test-Repository.

Profil:

- `NEXUSCTL_DEPLOYMENT_MODE=internal-production`
- `NEXUSCTL_API_TLS_ENABLED=1`, wenn die API remote erreichbar ist oder hinter Reverse Proxy/TLS liegt.
- `NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND=0`
- `NEXUSCTL_API_ALLOW_INSECURE_REMOTE=0`
- `NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED=1`, falls Webhooks getestet werden.
- `GITHUB_WEBHOOK_SECRET` aus Secret Management, niemals aus Beispieldateien.

Staging muss vor jeder produktiven Freigabe mindestens diese Checks bestehen:

```bash
nexusctl db init --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json
nexusctl doctor --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json
nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --json
```

### Interner Produktionsbetrieb

Zweck: produktive interne Nutzung als autoritative Control Plane.

Profil:

- `NEXUSCTL_DEPLOYMENT_MODE=internal-production`
- API nur loopback oder hinter Reverse Proxy/TLS betreiben.
- Unsichere Remote-Opt-ins bleiben deaktiviert.
- Alle produktiven Secrets kommen aus Secret Management.
- Persistente Volumes für DB, Backups, Workspaces und Repo-Worktrees sind gemountet.
- Backups werden regelmäßig erstellt, durch Restore-Drills nachgewiesen und zusammen mit Recovery-Evidence-Manifesten gemäß Retention- und Offsite-Vertrag archiviert.


## Geführtes Deployment mit Wizard

Für einen leichteren Einstieg gibt es einen lokalen Wizard, der keine Infrastruktur mutiert, sondern ein reviewbares Deployment-Bundle erzeugt:

```bash
python scripts/deployment_wizard.py
```

Für nicht-interaktive Vorbereitung, zum Beispiel in einer Betreiber-Shell oder CI-Probe:

```bash
python scripts/deployment_wizard.py --non-interactive --profile internal-production --volume-mode named
```

Der Wizard erzeugt standardmäßig unter `deploy/wizard/`:

- eine profilbezogene `.env.*`-Datei mit sicheren Defaults, einem automatisch erzeugten `GITHUB_WEBHOOK_SECRET`, sofern kein bestehendes Secret übergeben wurde, und sichtbaren Recovery-Evidence-/Retention-/Offsite-Kontrollwerten;
- ein `docker-compose.override.yml`, das die Environment-Datei einbindet und die Volume-Strategie festlegt;
- ein `bootstrap-operator-token.sh`, das nach `db init` über `nexusctl auth login --agent operator` einen gültigen DB-gebundenen Operator-Token ausstellt;
- eine kurze lokale README mit den nächsten Befehlen.

Der Wizard unterscheidet bewusst zwei Secret-Arten: Offline sicher generierbare Secrets wie `GITHUB_WEBHOOK_SECRET` werden direkt erzeugt. Nexusctl-Agent-Tokens werden nicht blind in eine Datei gewürfelt, weil sie zur SQLite-Token-Registry passen müssen; sie entstehen erst nach Datenbankinitialisierung über den Bootstrap-Schritt und gehören danach in `NEXUSCTL_TOKEN` oder besser in das Secret Management des Betreibers.

Bei den Volumes kann der Betreiber zwischen Named Volumes und Host-Bind-Mounts wählen:

```bash
python scripts/deployment_wizard.py --non-interactive --volume-mode host --host-volume-root /srv/openclaw-nexus
```

Persistiert werden dabei immer Datenbank, Backups, Recovery-Evidence-Manifeste, Workspaces und Repo-Worktrees. `nexus/` wird read-only in die Nexusctl-Container gemountet; `generated/` wird von OpenClaw read-only konsumiert.

## Deployment-Artefakte

Ein Release besteht aus:

1. Repository-Stand mit `README.md`, `docs/`, `nexus/`, `nexusctl/`, `config/`, `scripts/` und `tests/`.
2. Control Config unter `nexus/*.yml` als designseitigem Soll-Zustand.
3. Generierten OpenClaw-Artefakten unter `generated/*` als abgeleiteter Runtime Config.
4. Docker-Images für `nexusctl` und den OpenClaw-Gateway-Wrapper.
5. Migrationsfähigem SQLite-State in der Zielumgebung, nicht als Teil des Repository-Artefakts.

Empfohlener Build- und Prüfpfad:

```bash
python scripts/validate_project.py
./scripts/run_tests.sh ci
python scripts/package_project.py --output dist/openclaw-nexus.zip
```

Für Container-Deployments:

```bash
docker compose -f config/docker-compose.yml build
```

Die aktuelle `config/docker-compose.yml` ist eine Referenz für lokale Entwicklung und interne Betriebsprofile. Für echte Produktion sollte eine separate Betreiber-Compose-Datei, Helm-Chart oder Plattformdefinition verwendet werden, die Secrets, TLS, Volumes, Netzwerkgrenzen und Ressourcenlimits außerhalb des Repositorys verwaltet.

## Zieltopologie

Die empfohlene interne Topologie besteht aus vier logischen Schichten:

1. **Edge / Reverse Proxy**
   - Terminiert TLS.
   - Erzwingt Authentifizierung, Netzwerkzugriff und Request-Limits.
   - Leitet nur erlaubte Pfade an `nexusctl-api` weiter.

2. **Nexusctl API**
   - Läuft als Container oder interner Dienst.
   - Verwendet persistente `NEXUSCTL_DB`.
   - Ist nur intern beziehungsweise über den Reverse Proxy erreichbar.

3. **Nexusctl Worker / Betriebsjobs**
   - Führt geplante Nexusctl-Aufgaben aus, zum Beispiel Scope-Expiry-Guard oder spätere Reconciliation-Jobs.
   - Nutzt dieselbe persistente DB und denselben Projektzustand wie die API.
   - Darf keine produktiven Cron-Definitionen außerhalb des Nexusctl-Kontrollflusses mutieren.

4. **OpenClaw Runtime / Gateway**
   - Konsumiert `generated/openclaw/openclaw.json` und weitere `generated/*`-Artefakte read-only.
   - Spricht mit der Nexusctl API über den definierten internen Endpoint.
   - Mutiert keine Control Config und keinen autoritativen Control Store direkt.

## Konfigurations- und Secret-Management

`config/.env.example` bleibt ein Beispiel, kein produktives Secret- oder Deployment-Manifest. Für Staging und Produktion gilt:

- eigene Environment-Dateien oder Plattform-Secrets je Umgebung verwenden;
- `GITHUB_WEBHOOK_SECRET` und spätere GitHub-App-Secrets nur aus Secret Management laden;
- keine Secrets in `nexus/*.yml`, `generated/*`, Tests, Fixtures, Dockerfiles oder Dokumentation schreiben;
- TLS-/Proxy-Status über `NEXUSCTL_API_TLS_ENABLED=1` dokumentieren;
- unsichere Remote-Opt-ins nur lokal und bewusst aktivieren;
- Secret-Rotation als Betriebsvorgang mit anschließendem `doctor`-Check dokumentieren;
- `NEXUSCTL_RECOVERY_EVIDENCE_DIR`, `NEXUSCTL_BACKUP_RETENTION_DAYS`, `NEXUSCTL_BACKUP_RETENTION_MIN_COPIES`, `NEXUSCTL_OFFSITE_BACKUP_ENABLED`, `NEXUSCTL_OFFSITE_BACKUP_TARGET` und `NEXUSCTL_OFFSITE_BACKUP_SCHEDULE` je Umgebung reviewen; Offsite-Ziele bleiben Metadaten ohne Credentials.

## Persistenz, Backup und Restore

Produktiv persistent zu halten sind mindestens:

- `NEXUSCTL_DB`, zum Beispiel `/data/nexus.db`;
- `NEXUSCTL_BACKUP_DIR`, zum Beispiel `/backups`;
- `NEXUSCTL_RECOVERY_EVIDENCE_DIR`, zum Beispiel `/recovery-evidence`;
- `NEXUSCTL_WORKSPACES_DIR`, sofern lokale Workflows Workspaces nutzen;
- `NEXUSCTL_REPO_WORKTREES_DIR`, sofern lokale Repo-Worktrees genutzt werden;
- die ausgelieferte Control Config unter `nexus/*.yml`, bevorzugt read-only im Runtime-Container.

Backup und Restore laufen über Nexusctl-Kommandos, nicht über manuelles Kopieren laufender SQLite-Dateien:

```bash
nexusctl db backup --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --path "$NEXUSCTL_BACKUP_DIR/nexus.backup.sqlite3" --json
nexusctl db restore-check "$NEXUSCTL_BACKUP_DIR/nexus.backup.sqlite3" --project-root "$NEXUSCTL_PROJECT_ROOT" --json
nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --evidence-path "$NEXUSCTL_RECOVERY_EVIDENCE_DIR/restore-drill-evidence.json" --json
```

Das daraus entstehende Recovery Evidence Pack besteht mindestens aus geprüftem SQLite-Backup, erfolgreichem Restore-Drill-Report, secretfreiem Evidence-Manifest, Offsite-Kopiernachweis und angewendeter Retention-Policy. `nexusctl` erzeugt lokale Nachweise und Readiness-Signale; externe Verschlüsselung, WORM/Object-Lock, Cloud-Provider, Offsite-Upload und Retention-Automation bleiben Betreiberaufgabe.

Ein Restore in eine produktive Ziel-DB erfolgt nur geplant und mit dokumentiertem Wartungsfenster. Standardmäßig wird nicht überschrieben; ein ersetzender Restore benötigt bewusst `--overwrite` und anschließend einen grünen `doctor`-Lauf.

## Release- und Rollout-Prozess

### 1. Release-Kandidat erstellen

- Branch beziehungsweise Commit einfrieren.
- Projektvalidierung und Tests ausführen.
- Generierte Artefakte gegen Control Config prüfen.
- Release-Notizen mit relevanten Migrations-, Config- und Betriebsänderungen erstellen.

Mindestchecks:

```bash
python scripts/validate_project.py
./scripts/run_tests.sh ci
```

### 2. Staging deployen

- Image oder Paket aus exakt demselben Commit deployen.
- Staging-Secrets und persistente Staging-Volumes verwenden.
- DB initialisieren oder Migration durch Start/Doctor auslösen.
- `doctor` und `restore-drill --evidence-path` ausführen.
- Webhook- und GitHub-Projektionspfad gegen Test-Repository prüfen, wenn der Release daran Änderungen enthält.

### 3. Produktionsfreigabe entscheiden

Freigabe nur bei:

- grünem `validate_project.py`;
- grünem CI- oder äquivalentem Testlauf;
- grünem Staging-`doctor`;
- `doctor --json` mit `internal_production_preflight.status_code=ok` und leerem `cutover_blockers`;
- grünem Staging-`restore-drill` inklusive archiviertem Recovery-Evidence-Manifest;
- dokumentierter Secret-/Config-Differenz zwischen Staging und Produktion;
- geklärtem Rollback-Ziel und aktuellem produktivem Backup.

### 4. Produktion ausrollen

Empfohlener Ablauf:

1. Wartungsfenster oder kontrollierten Änderungszeitraum öffnen.
2. Aktuelles Backup erstellen, `restore-check` ausführen und Recovery-Evidence-Ziel prüfen.
3. Neue Images oder neues Paket bereitstellen.
4. API und Worker geordnet neu starten.
5. `nexusctl doctor --json` gegen die produktive DB ausführen und `internal_production_preflight.cutover_blockers` prüfen.
6. Anschließend einen Restore-Drill mit `--evidence-path` ausführen und das Evidence-Manifest archivieren.
7. Smoke-Checks gegen API, Worker, OpenClaw-Konfigurationsmount und GitHub-Webhook-Empfang ausführen.
8. Ergebnis inklusive Operator-Evidence für Offsite, Retention, TLS-/Proxy-Boundary, Secret Management und Monitoring im Betriebslog dokumentieren.

## Smoke-Checks nach Deployment

Minimaler Smoke-Check:

```bash
nexusctl doctor --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json
```

Bei Containerbetrieb zusätzlich:

```bash
docker compose -f config/docker-compose.yml ps
docker compose -f config/docker-compose.yml run --rm nexusctl-cli doctor --json
```

Fachliche Smoke-Checks:

- API-Healthcheck antwortet erfolgreich.
- `operational_readiness` enthält keine produktionsblockierenden Einträge.
- Event-Chain-Integrität ist grün.
- Migrationsstatus ist aktuell.
- `generated/openclaw/openclaw.json` ist lesbar und passt zur erwarteten Control Config.
- GitHub-Webhook-Signaturprüfung lehnt ungültige Signaturen ab und akzeptiert gültige Test-Deliveries in Staging.
- Worker kann geplante Jobs mindestens im Dry-Run ausführen.

## Rollback-Strategie

Rollback ist zweistufig zu betrachten: Code-/Image-Rollback und Daten-/State-Recovery.

### Code-/Image-Rollback

Geeignet, wenn:

- neue API, Worker oder OpenClaw Runtime fehlerhaft sind;
- keine inkompatible DB-Migration produktiv angewendet wurde;
- `doctor` mit vorherigem Image wieder grün werden kann.

Ablauf:

1. Dienste stoppen oder Traffic am Reverse Proxy zurücknehmen.
2. Vorheriges Image oder Paket deployen.
3. Dienste starten.
4. `nexusctl doctor --json` ausführen.
5. Smoke-Checks wiederholen.

### Daten-/State-Recovery

Geeignet, wenn:

- DB-State beschädigt ist;
- Audit-Event-Chain inkonsistent ist;
- eine Migration oder Mutation nicht durch Code-Rollback behebbar ist.

Ablauf:

1. Produktive Dienste stoppen und DB schreibgeschützt sichern.
2. Ziel-Backup mit `restore-check` prüfen.
3. Restore in neue DB durchführen.
4. `doctor` gegen neue DB ausführen.
5. Erst nach grünem Ergebnis Traffic auf die wiederhergestellte DB legen.
6. Ursache dokumentieren und beschädigte DB für Analyse isolieren.

Direkte Updates oder Deletes auf dem Event Store sind kein zulässiger Rollback-Pfad.

## GitHub-Live-Sandbox-Gate

Ein Deployment gilt trotz grünem `nexusctl doctor --json` erst dann als GitHub-live-verifiziert, wenn der separate Sandboxlauf gegen eine echte GitHub-App und ein Test-Repository abgeschlossen wurde. Das Gate ist bewusst kein Repository-Secret und kein Fixture-Test: Der Operator archiviert nur die im internen Betriebsrunbook definierten secretfreien Evidence-Felder. Fehlende Live-Evidence blockiert die produktionsnahe Aktivierung von GitHub-Webhook-Reconciliation, auch wenn die lokalen Fixture-Contracts grün sind.

## Monitoring und Betriebsalarme

Für den internen Produktionsbetrieb müssen mindestens diese Signale überwacht werden:

- API-Healthcheck, Fehlerrate und Latenz hinter dem Reverse Proxy/TLS-Boundary;
- Worker-Liveness und letzter erfolgreicher Joblauf;
- `nexusctl doctor --json` als periodischer Readiness-Report mit `operational_readiness`, `operational_warnings`, Event-Chain-Integrität und Migrationsstatus;
- offene GitHub-Reconciliation-Alerts aus `doctor.alerts` beziehungsweise `github_alerts`;
- Backup-Erfolg, Alter des letzten erfolgreichen Restore-Drills und Vorhandensein des letzten Recovery-Evidence-Manifests;
- Offsite-Kopierstatus, Retention-Fenster, Verschlüsselungsnachweis und WORM/Object-Lock-Quittung gemäß Betreiberpolicy;
- freier Speicherplatz für DB, Backups, Workspaces und Repo-Worktrees;
- unerwartete Änderungen an `nexus/*.yml` und `generated/*`;
- Secret-Rotation-Fristen und Redaktionsverstöße in Logs oder Evidence.

Die konkrete Alert-Reaktion ist im Betriebsrunbook unter `docs/operations/internal-production.md#monitoring--und-alert-reaktion` definiert. Für Deployment-Freigaben gelten diese Gate-Regeln:

| Gate | Blockierender Zustand | Erwartete Aktion |
| --- | --- | --- |
| Doctor-/Readiness-Gate | `status_code != ok`, `status_codes.operations != ok` oder kritische `operational_readiness`-ID. | Betroffene Konfiguration oder Betreiberkontrolle korrigieren und Doctor wiederholen. |
| GitHub-Reconciliation-Gate | Offener kritischer Alert, insbesondere Unauthorized Merge oder Head-SHA-Drift. | Merge-Gate blockiert lassen, Drift reconciliieren oder Abweichung dokumentiert schließen. |
| Recovery-Gate | `restore-drill` nicht grün, Evidence-Manifest fehlt, `failed_checks` nicht leer oder Event-Chain nicht grün. | Backup prüfen, Drill wiederholen, Manifest archivieren und Ursache dokumentieren. |
| Offsite-/WORM-Gate | Offsite-Kopie, Retention, Verschlüsselung oder WORM/Object-Lock extern nicht nachgewiesen. | Provider-Nachweis nachziehen; lokale Evidence allein reicht nicht für Produktionsfreigabe. |
| TLS-/Secret-Gate | Remote-Binding ohne TLS-Boundary, Platzhaltersecret oder überfällige Rotation. | Traffic begrenzen, Reverse Proxy/TLS und Secret Management korrigieren, anschließend Smoke-Checks wiederholen. |

`nexusctl` stellt dafür Readiness-IDs, lokale Evidence und secretfreie Grenzen bereit. Das produktive Monitoring-System, Alert-Routing, Pager, Offsite-Replikation, WORM/Object-Lock, externe Audit-Signaturen und Secret Management bleiben Betreiberpflicht.

## Sicherheitsgrenzen

- Produktive API nicht direkt ohne TLS oder Netzwerkgrenze exponieren.
- GitHub ist nicht autoritativ; externe Labels, Reviews, Checks und Merges sind Signale, keine Lifecycle-Entscheidungen.
- Agents dürfen Requests, Proposals und erlaubte Runs erzeugen, aber keinen autoritativen Control Store und keine Control Config direkt mutieren.
- `generated/*` ist abgeleitete Runtime Config und darf produktiv nicht manuell editiert werden.
- Fixtures, Docs und Konfiguration bleiben secretfrei.
- Audit-Events sind append-only; Integritätsverletzungen werden als Incident behandelt.

## Empfohlene nächste Deployment-Arbeiten

1. Betreiber-spezifisches Produktionsmanifest oder Plattformtemplate auf Basis des Wizard-Bundles ergänzen, zum Beispiel ein Helm-Chart außerhalb sensibler Secrets.
2. Reverse-Proxy-Beispiel mit TLS-Boundary, Body-Limits und Authentifizierung dokumentieren.
3. Secret-Rotation-Runbook für GitHub-Webhooks und spätere GitHub-App-Secrets schreiben.
4. Betreiber-spezifische Prometheus-, Cron- oder Plattformchecks aus dem Monitoring-Runbook implementieren und mit Alert-Routing verbinden.
5. Offsite-Backup-, Retention-, Verschlüsselungs- und WORM/Object-Lock-Strategie technisch beim Betreiber umsetzen und mit den Recovery-Evidence-Manifesten verknüpfen.
6. Das GitHub-Live-Sandbox-Runbook aus `docs/operations/internal-production.md#github-live-sandbox-verifikation` vor produktionsnaher Webhook-Freigabe ausführen und das secretfreie Evidence-Artefakt archivieren.
