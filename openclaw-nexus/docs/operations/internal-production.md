# Interner Betrieb

## Produktionsprofil

Der Docker- und Environment-Stand unterscheidet bewusst zwischen lokaler Entwicklung und internem Produktionsbetrieb. Die mitgelieferte `config/.env.example` startet im Profil `NEXUSCTL_DEPLOYMENT_MODE=development`; unsichere Remote-Bindings oder Plain-HTTP-Containerkommunikation müssen über `NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND=1` beziehungsweise `NEXUSCTL_API_ALLOW_INSECURE_REMOTE=1` sichtbar aktiviert werden. Diese Opt-ins sind für lokale Containerentwicklung gedacht und gelten nicht als produktionsgrün.

Für internen Produktionsbetrieb gilt mindestens dieser Vertrag:

- `NEXUSCTL_DEPLOYMENT_MODE=internal-production` setzen.
- Nexusctl-API nur loopback oder hinter Reverse Proxy/TLS betreiben; bei Remote-Binding muss `NEXUSCTL_API_TLS_ENABLED=1` den TLS-/Proxy-Boundary dokumentieren.
- `NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND=0` und `NEXUSCTL_API_ALLOW_INSECURE_REMOTE=0` verwenden, außer ein Betreiber entscheidet explizit für einen nicht produktionsreifen Entwicklungsmodus.
- Wenn GitHub-Webhook-Reconciliation aktiv ist (`NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED=1` oder GitHub-App-Modus), muss `GITHUB_WEBHOOK_SECRET` aus Secret Management gesetzt sein; Platzhalterwerte wie `change-me` sind nicht zulässig.
- Persistente Pfade für `NEXUSCTL_DB`, `NEXUSCTL_BACKUP_DIR`, `NEXUSCTL_RECOVERY_EVIDENCE_DIR`, `NEXUSCTL_WORKSPACES_DIR` und `NEXUSCTL_REPO_WORKTREES_DIR` müssen vorhanden beziehungsweise gemountet sein.
- `NEXUSCTL_BACKUP_RETENTION_DAYS`, `NEXUSCTL_BACKUP_RETENTION_MIN_COPIES`, `NEXUSCTL_OFFSITE_BACKUP_ENABLED`, `NEXUSCTL_OFFSITE_BACKUP_TARGET` und `NEXUSCTL_OFFSITE_BACKUP_SCHEDULE` müssen als Betreibervertrag gesetzt sein; Ziel- und Schedule-Werte sind Metadaten, keine Provider-Secrets.
- Vor Inbetriebnahme und nach jedem Restore den automatisierten Restore-Drill ausführen. Der Drill bündelt Backup, Restore in eine neue Drill-DB, `doctor` und optional ein Recovery-Evidence-Manifest; ergänzende direkte `nexusctl doctor --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json`-Läufe bleiben für die aktive DB zulässig und nicht-grüne `operational_readiness`-Einträge müssen behoben werden.

Der Doctor-Report enthält dafür eine maschinenlesbare `operational_readiness`-Liste und macht verletzte Produktionsbedingungen zusätzlich unter `operational_warnings` sichtbar. Secret-Werte werden dabei nicht ausgegeben.

## Internal-Production-Preflight

Vor einem Cutover muss ein Operator einen wiederholbaren Preflight ausführen. Der Preflight ist secretfrei dokumentiert, liest aber Betreiberwerte aus der Zielumgebung oder aus dem durch `scripts/deployment_wizard.py` erzeugten Bundle:

1. Internal-Production-Environment laden und prüfen, dass produktive Secrets aus Secret Management kommen.
2. Datenbank initialisieren oder migrieren:

   ```bash
   nexusctl db init --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json
   ```

3. Doctor gegen die Ziel-DB ausführen und den JSON-Report archivieren:

   ```bash
   nexusctl doctor --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --json
   ```

4. Restore-Drill mit Evidence-Manifest ausführen:

   ```bash
   nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --evidence-path "$NEXUSCTL_RECOVERY_EVIDENCE_DIR/restore-drill-evidence.json" --json
   ```

5. Cutover nur freigeben, wenn `doctor --json` unter `internal_production_preflight.status_code` nicht `blocked` meldet, `cutover_blockers` leer ist, das Restore-Drill-Manifest grün ist und die Betreiber-Nachweise für Offsite-Kopie, Retention, TLS-/Proxy-Boundary, Secret Management, Monitoring und gegebenenfalls WORM/externe Audit-Evidence im Betriebslog vorliegen.

Der Doctor-Report enthält dafür den maschinenlesbaren Abschnitt `internal_production_preflight` mit `expected_json_fields`, `command_sequence`, `recovery_evidence`, `external_operator_evidence_required` und `cutover_blockers`. Lokale Repository-Checks ersetzen keine Provider-Liveprüfung; sie machen fehlende Betreiber-Evidence nur sichtbar und blockierend.

## GitHub-Webhooks und Reconciliation

GitHub bleibt im Produktionspfad Projektion und Kollaborationsfläche. `nexusctl` bleibt die Lifecycle-Authority für Feature Requests, Work Items, Patch Proposals, Reviews, Business-Acceptance, Policy-Gates und Merge-Entscheidungen. Externe GitHub-Reviews, Check-Runs, Labels oder Merge-Zustände werden als Signale, Repairs oder Alerts verarbeitet, übernehmen aber keine OpenClaw-Nexus-Authority. Agents dürfen solche Signale erzeugen, bewerten oder erlaubte Ausführungsschritte starten, mutieren aber keinen autoritativen Control Store und keine Control Config direkt.

Unterstützte Webhook-Event-Klassen sind aktuell `issues`, `issue_comment`, `pull_request`, `pull_request_review`, `check_run`, `workflow_run` und `push`. Fixture-abgedeckt sind die produktionsrelevanten Kernformen `issues`, `pull_request`, `pull_request_review` und `check_run` unter `tests/fixtures/github/`. Diese Fixtures müssen secretfrei bleiben und dienen als Contract-Beispiele für Repository-Felder, Issue-/PR-Nummern, Labels, Review-State, Check-State, Head-SHA und Merge-State.

Der Webhook-Empfang prüft Delivery-ID, Event-Header und HMAC-SHA256-Signatur vor der Verarbeitung. Ungültige oder fehlende Signaturen, fehlende Pflichtheader, ungültiges JSON und konflikthafte Wiederholungen derselben Delivery werden kontrolliert abgewiesen, ohne Secret-Werte in Antworten oder Doctor-Ausgaben zu rendern. Unbekannte Event-Typen werden nur nach gültiger Signatur persistiert und als `ignored` markiert.

Die Delivery-Verarbeitung ist idempotent: dieselbe Delivery-ID mit identischem Event und Payload wird nicht erneut als neue Arbeit verarbeitet; dieselbe Delivery-ID mit anderem Event oder anderem Payload ist ein Konflikt. Der aktive Statusvertrag für `github_webhook_events.processing_status` lautet `pending`, `processed`, `alerted`, `ignored`, `dead_letter`.

`nexusctl doctor --json` enthält den Abschnitt `github_webhook_contract` und zusätzlich den Readiness-Eintrag `github_webhook_contract`. Für `internal-production` muss dieser Vertrag grün sein: die erwarteten Fixtures sind vorhanden, es wurden keine offensichtlichen Secret-Marker in Fixture-Payloads gefunden, die unterstützten Event-Klassen und negativen Webhook-Verträge sind maschinenlesbar sichtbar, und die Authority-Regel weist GitHub ausdrücklich als nicht-autoritativ aus.


## GitHub-Live-Sandbox-Verifikation

Fixture-grüne Webhook- und Reconciliation-Tests sind ein lokaler Contract-Nachweis, aber kein Nachweis, dass eine echte GitHub-App-Installation, ein echtes Test-Repository, der Reverse Proxy und Secret Management korrekt zusammenspielen. Vor einem internen Produktions-Cutover muss deshalb ein isolierter Live-Sandboxlauf gegen eine separate GitHub-App und ein separates Repository durchgeführt werden. GitHub bleibt dabei Projektion und Signalquelle; `nexusctl` bleibt Lifecycle-Authority.

Voraussetzungen:

- separate GitHub-App nur für Sandbox oder Staging installieren, nicht die produktive App wiederverwenden;
- separates Test-Repository ohne echte Kundendaten verwenden;
- `GITHUB_WEBHOOK_SECRET`, GitHub-App-Private-Key und Installation-ID ausschließlich aus Secret Management laden;
- `NEXUSCTL_DEPLOYMENT_MODE=internal-production`, `NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED=1` und `NEXUSCTL_GITHUB_MODE=app` nur in der isolierten Sandbox setzen;
- `nexusctl doctor --json` muss vor dem Lauf grün sein, insbesondere `github_webhook_contract.status_code=ok`;
- Logs, Screenshots und Evidence dürfen keine Secrets, Tokens, Private Keys, echten Repository-Namen oder personenbezogenen Daten enthalten.

Auszuführende positive Fälle:

1. **Webhook-Delivery-Prüfung:** GitHub-App-Webhook mit gültigem Secret auslösen und prüfen, dass Delivery-ID, Event-Klasse und Signatur akzeptiert werden. Als Negativprobe dieselbe Payload mit ungültiger Signatur gegen den Sandbox-Endpunkt senden; sie muss abgelehnt werden, ohne persistierte Nutzdaten oder Secret-Rendering.
2. **PR-Projektion:** Aus einem Nexus-Work-Item oder Patch Proposal eine GitHub-Issue-/PR-Projektion in das Test-Repository erzeugen. Die Projektion muss Nexus-IDs enthalten und die Beschreibung muss die Nicht-Authority-Grenze nennen.
3. **Review-Signal:** Im Test-Repository ein Review-Signal erzeugen. Nexusctl darf daraus höchstens Signal, Alert oder Reconciliation-Status ableiten; es darf keine Business-Acceptance oder Lifecycle-Entscheidung aus GitHub übernehmen.
4. **Check-Run-Signal:** Einen erfolgreichen und einen fehlgeschlagenen Check-Run simulieren oder über die GitHub-App empfangen. Fehlgeschlagene Checks dürfen Gate- oder Alert-Zustände beeinflussen, aber keine Nexus-Review-Entscheidung ersetzen.
5. **Label-Drift:** Ein erwartetes Projektionslabel im Test-Repository manuell ändern. Die Reconciliation muss bekannten Drift erkennen oder reparieren; unbekannte Labels dürfen nicht als Feature-, Review- oder Acceptance-Status übernommen werden.
6. **Unauthorized Merge:** Einen Merge außerhalb des Nexus-Merge-Gates simulieren. Das Ergebnis muss ein kritischer Reconciliation-Alert sein, der Merge-Gates blockiert, bis er bewusst aufgelöst ist.

Secretfreier Evidence-Vertrag für den Operator-Archivnachweis:

| Feld | Inhalt | Secretfrei-Regel |
| --- | --- | --- |
| `run_id` | Eindeutige lokale Lauf-ID. | Keine GitHub-IDs mit Secret-Bezug. |
| `timestamp_utc` | Start- oder Abschlusszeit des Sandboxlaufs in UTC. | Nur Zeitstempel. |
| `environment` | `sandbox` oder `staging`. | Keine Hostnamen mit internen Secrets. |
| `github_app_installation_id_hash` | Hash oder gekürzte Referenz der Installation. | Nie die vollständige Installation-ID veröffentlichen, wenn sie intern als sensitiv gilt. |
| `repository_slug_hash` | Hash oder Alias des Test-Repositories. | Kein echter privater Owner-/Repository-Name. |
| `webhook_delivery_ids` | Gekürzte oder gehashte Delivery-IDs der geprüften Events. | Keine vollständigen Payloads. |
| `nexus_doctor_status_code` | `status_code` aus `nexusctl doctor --json` vor und nach dem Lauf. | Keine Secret-Werte aus der Umgebung. |
| `projection_issue_number` | Test-Issue-/PR-Nummer oder Alias. | Nur Sandboxnummer, kein produktiver Link. |
| `projection_work_item_id` | Nexus-Testobjekt-ID aus der Sandbox. | Keine Kundendaten im Titel oder Body. |
| `review_signal_status` | Erwarteter Status für Review-Signal verarbeitet/alerted/ignored. | Kein Review-Body. |
| `check_run_signal_status` | Erwarteter Status für Check-Run-Signal verarbeitet/alerted/ignored. | Keine externen Logs. |
| `label_drift_status` | Erkannter oder reparierter Drift beziehungsweise bewusster Alert. | Keine vollständige Label-Historie. |
| `unauthorized_merge_alert_id` | Nexus-Alert-ID oder Alias des kritischen Alerts. | Kein echter Branch- oder Commit-Secret. |
| `negative_signature_result` | Ergebnis der ungültigen Signaturprobe. | Keine Secret- oder HMAC-Werte. |
| `operator_result` | `passed`, `failed` oder `accepted_with_deviation`. | Abweichungen separat im Betriebslog begründen. |
| `redactions_applied` | Liste der angewendeten Redaktionen, zum Beispiel `repo_hash`, `delivery_id_prefix`. | Muss nicht leer sein; Redaktionen sind erwünscht. |

Der Doctor-Abschnitt `github_webhook_contract.live_sandbox_verification` spiegelt diese Felder maschinenlesbar als Zielvertrag. Ein grüner Doctor-Report bestätigt damit nur, dass der lokale Contract und das Evidence-Schema vorhanden sind. Das Feld `required_before_internal_production_cutover=true` bedeutet, dass der Operator den Live-Sandboxlauf extern durchführen und das secretfreie Evidence-Artefakt archivieren muss, bevor GitHub-Webhooks als produktionsnah freigegeben werden.

Nicht als Live-Evidence zulässig sind: echte Secrets, vollständige Private Keys, HMAC-Werte, vollständige Webhook-Payloads aus privaten Repositories, personenbezogene Review-Texte, produktive Repository-Links oder Screenshots mit Token-/Secret-UI.

Bei offenen Alerts gilt:

- Kritische Alerts, zum Beispiel unauthorized Merge oder sicherheitsrelevante manuelle Eingriffe, blockieren Merge-Gates bis zur Auflösung oder bewussten Schließung.
- Warnungen, zum Beispiel externe Review- oder Check-Run-Signale ohne Nexus-Verknüpfung, müssen bewertet und bei Bedarf reconciled werden.
- Label-Drift darf bekannte Projektion korrigieren, aber keine unverbundenen Labels als Lifecycle-Entscheidung übernehmen.

## Backup, Restore und Persistenz

Für internen Betrieb müssen mindestens diese Pfade persistent sein:

- SQLite-State: `NEXUSCTL_DB`, im Docker-Beispiel `/data/nexus.db` im Volume `nexus-data`.
- Backup-Ziel: im Docker-Beispiel `/backups` im Volume `nexus-backups`.
- Recovery-Evidence-Ziel: im Docker-Beispiel `/recovery-evidence` im Volume `recovery-evidence`.
- Arbeitsbereiche und Repo-Worktrees: `/workspaces` und `/repo-worktrees`, sofern lokale Workflows sie nutzen.
- Control Config: `nexus/*.yml`; diese Dateien sind Teil des Projektstands, beschreiben den designseitigen Soll-Zustand und werden in Containerbeispielen read-only eingebunden.

Die OpenClaw-Artefakte unter `generated/*` sind OpenClaw Runtime Config aus der Control Config in `nexus/*.yml` und werden über `nexusctl` erzeugt. Sie sollen versioniert oder vor Deployment reproduzierbar neu erzeugt werden; sie ersetzen kein Datenbankbackup und sind nicht die Source of Truth. Runtime-Cronjobs und Schedule-Artefakte gelten als `nexusctl`-kontrollierte Ausführungskonfiguration: Agents dürfen erlaubte Runs auslösen oder Änderungsbedarf formulieren, aber produktive Cron-Definitionen nicht direkt in der Runtime mutieren.

SQLite-Backup erstellen:

```bash
nexusctl db backup --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --path /backups/nexus.backup.sqlite3 --json
```

Backup vor Restore prüfen:

```bash
nexusctl db restore-check /backups/nexus.backup.sqlite3 --project-root "$NEXUSCTL_PROJECT_ROOT" --json
```

Restore in eine neue lokale Runtime-Datenbank:

```bash
nexusctl db restore /backups/nexus.backup.sqlite3 --db /data/nexus-restored.db --json
nexusctl doctor --db /data/nexus-restored.db --project-root "$NEXUSCTL_PROJECT_ROOT" --json
```

Der Restore-Pfad verweigert standardmäßig das Überschreiben bestehender Ziel-Datenbanken. Für einen bewusst ersetzenden Restore muss `--overwrite` explizit gesetzt werden. Nach jedem Restore ist `nexusctl doctor` der verpflichtende Betriebscheck, insbesondere wegen Event-Chain-Integrität und Migrationsstatus.

Automatisierter Restore-Drill für Vor-Inbetriebnahme- und Nach-Restore-Nachweise:

```bash
nexusctl db restore-drill --db "$NEXUSCTL_DB" --project-root "$NEXUSCTL_PROJECT_ROOT" --backup-dir "$NEXUSCTL_BACKUP_DIR" --json
```

Der Drill erzeugt entweder ein neues Backup oder prüft mit `--backup-path` ein explizit angegebenes Backup, restored immer in eine frisch erzeugte Drill-Datenbank und überschreibt keine Betreiber-Ziel-DB. Als grün gilt der maschinenlesbare Report nur, wenn `ok` `true`, `doctor_status` `ok`, `failed_checks` leer, `checked_events` größer als null und `schema_version` gesetzt ist. Betreiber müssen außerdem prüfen, dass `backup_path` und `restored_db` auf die erwarteten lokalen Recovery-Pfade zeigen und die `counts` zu den erwarteten Kernobjekten passen. Nicht-grüne `failed_checks` sind vor Inbetriebnahme beziehungsweise vor Abschluss eines Restore-Vorgangs zu beheben oder als bewusste Betriebsabweichung zu dokumentieren.

## Recovery Evidence Pack

Das Recovery Evidence Pack ist der operator-reviewbare Nachweis, dass lokale Backups, Restore-Drill, Event-Chain-Integrität und die betrieblichen Offsite-/Retention-Kontrollen zusammen geprüft wurden. Es ist kein Cloud- oder WORM-Client: Nexusctl erzeugt ein secretfreies JSON-Manifest; Kopie, Verschlüsselung, Unveränderbarkeit, Aufbewahrung und externe Lagerung bleiben Betreiberaufgabe.

Minimaler Operator-Vertrag:

- **Backup-Frequenz:** mindestens täglich für produktive interne Umgebungen und zusätzlich vor jedem Release, Rollback, Restore oder riskanten Wartungsfenster.
- **Restore-Drill-Frequenz:** vor Erstinbetriebnahme, nach jedem Restore, nach Backup-/Storage-Änderungen und regelmäßig als Betriebsnachweis, mindestens im selben Rhythmus wie die Recovery-Compliance des Betreibers.
- **Evidence-Manifest:** bei jedem Drill mit `--evidence-path` in `NEXUSCTL_RECOVERY_EVIDENCE_DIR` schreiben, anschließend unverändert archivieren und mit dem Betriebslog verknüpfen.
- **Offsite-Kopie:** Backup-Datei und Evidence-Manifest nach erfolgreicher lokaler Prüfung in ein operator-managed Offsite-Ziel kopieren. `NEXUSCTL_OFFSITE_BACKUP_TARGET` beschreibt dieses Ziel nur als Metadatum und darf keine Credentials enthalten.
- **Retention:** mindestens `NEXUSCTL_BACKUP_RETENTION_DAYS` Tage und `NEXUSCTL_BACKUP_RETENTION_MIN_COPIES` Kopien aufbewahren; Löschung alter Artefakte nur nach erfolgreichem neueren Drill und dokumentierter Offsite-Kopie.
- **Incident-Schwellen:** nicht-grünes Manifest, fehlende Offsite-Kopie, abgelaufene Retention, fehlender Evidence-Pfad, Event-Chain-Fehler oder `doctor_status` ungleich `ok` gelten als Recovery-Incident und müssen vor produktiver Freigabe behoben oder formal als Betriebsabweichung akzeptiert werden.

Empfohlener Nachweis-Befehl:

```bash
nexusctl db restore-drill   --db "$NEXUSCTL_DB"   --project-root "$NEXUSCTL_PROJECT_ROOT"   --backup-dir "$NEXUSCTL_BACKUP_DIR"   --evidence-path "$NEXUSCTL_RECOVERY_EVIDENCE_DIR/restore-drill-$(date +%Y%m%dT%H%M%SZ).json"   --json
```

Das JSON-Ergebnis enthält `recovery_evidence`; die Manifestdatei ist der archivierbare Recovery-Evidence-Nachweis. Grün ist der Nachweis nur, wenn lokaler Drill und `event_chain_status` grün sind, `failed_checks` leer ist und `retention_status` sowie `offsite_status` die gesetzten Betreiberkontrollen widerspiegeln. Provider-spezifische Upload-Logs, Verschlüsselungsnachweise, WORM-/Object-Lock-Quittungen oder Ticket-Links dürfen im externen Betriebslog ergänzt werden, gehören aber nicht als Secrets ins Repository.

Der Evidence-Payload enthält zusätzlich `operator_control_boundaries`. Dieses Feld ist kein Provider-Nachweis, sondern der stabile, secretfreie Grenzvertrag zwischen lokaler Produkt-Evidence und externen Betreiberkontrollen:

| Gruppe | Inhalt | Bedeutung |
| --- | --- | --- |
| `local_product_evidence` | SQLite-Backup-/Restore-Drill, `doctor_status`, Event-Chain, Schema, `failed_checks`. | Produktbestandteil von `nexusctl`; kann lokal und in CI/Sandbox geprüft werden. |
| `external_operator_controls` | Reverse Proxy/TLS, Secret Management, Offsite-Replikation, WORM/Object-Lock, externe Audit-Signaturen, Monitoring-System und Retention-Enforcement. | Betreiberpflicht; muss außerhalb des Repositorys implementiert und im Betriebslog nachgewiesen werden. |
| `incident_triggers` | Nicht-grüner Drill, nicht-grüner Doctor, nicht-grüne Event-Chain, fehlende oder nicht archivierte Evidence, nicht-grüne Retention-/Offsite-Kontrolle. | Auslöser für Incident- oder Abweichungsbearbeitung. |

## Monitoring- und Alert-Reaktion

`nexusctl` liefert lokale Readiness- und Evidence-Signale, betreibt aber kein eigenes produktives Monitoring-System, keinen Pager, keinen Provider-Offsite-Client und keinen WORM-Speicher. Für internen Produktionsbetrieb muss der Betreiber diese Signale regelmäßig einsammeln, in sein Monitoring überführen und mit konkreten Runbooks verbinden.

| Alarmklasse | Quelle | Trigger | Sofortreaktion | Abschlusskriterium |
| --- | --- | --- | --- | --- |
| Doctor-/Readiness-Alarm | `nexusctl doctor --json`, Felder `status_code`, `status_codes`, `operational_readiness`, `operational_warnings`. | `status_code != ok`, `status_codes.operations != ok`, kritische Readiness-ID oder steigende Warnungen. | Betroffene Readiness-ID prüfen, Secret-/TLS-/Pfad-/Backup-/GitHub-Vertrag korrigieren, danach Doctor erneut ausführen. | Doctor ist grün oder Abweichung ist mit Owner, Ablaufdatum und Risiko akzeptiert. |
| GitHub-Reconciliation-Alert | `doctor.alerts`, Tabelle `github_alerts`, Webhook-/Reconciliation-Logs. | offener kritischer Alert, `unauthorized_github_merge`, Head-SHA-Drift, Label-Drift, externe Review-/Check-Signale. | Merge-Gates blockiert lassen, Drift reparieren oder bewusst schließen, GitHub weiterhin nur als Signalquelle behandeln. | Kritische Alerts sind geschlossen oder dokumentiert akzeptiert; keine Business-Acceptance wurde aus GitHub übernommen. |
| Restore-Drill-/Recovery-Evidence-Alarm | `nexusctl db restore-drill --json`, Manifest in `NEXUSCTL_RECOVERY_EVIDENCE_DIR`. | `ok=false`, `doctor_status != ok`, `failed_checks` nicht leer, `event_chain_status.status_code != ok`, Manifest fehlt oder ist älter als Betreiberpolicy. | Neues Backup prüfen, Drill wiederholen, Event-Chain- oder DB-Fehler untersuchen, Evidence neu archivieren. | Erfolgreicher Drill mit aktuellem secretfreiem Manifest liegt lokal und im Betreiberarchiv vor. |
| Offsite-/Retention-Alarm | Betreiber-Monitoring plus Evidence-Felder `retention_status`, `offsite_status`. | Offsite-Kopie fehlt, Retention-Fenster unterschritten, WORM/Object-Lock-Quittung fehlt oder Löschung ohne neueren grünen Drill. | Offsite-Upload wiederholen, Retention-/Object-Lock-Konfiguration prüfen, fehlende Quittung im Betriebslog ergänzen. | Externe Provider-Evidence ist vorhanden und mit dem lokalen Manifest verknüpft. |
| TLS-/Secret-Alarm | Reverse Proxy, Secret Management, Doctor-IDs `api_binding`, `github_webhook_secret*`. | Remote-Binding ohne TLS-Boundary, Platzhaltersecret, Secret-Rotation überfällig, unzulässiges Secret in Logs/Evidence. | Traffic begrenzen, Secret rotieren, Proxy/TLS-Konfiguration prüfen, betroffene Logs/Evidence redigieren. | Doctor ist grün; Rotation und Redaktionen sind im Betriebslog nachweisbar. |

Für alle Alarmklassen gilt: Kritische Alerts blockieren produktionsnahe Merge- oder Cutover-Entscheidungen, bis sie aufgelöst oder explizit als Betriebsabweichung akzeptiert wurden. Nicht-grüne Recovery-Evidence darf nicht stillschweigend durch ein grünes lokales Fixture-Ergebnis ersetzt werden.

## Produktbestandteil vs. Betreiberpflicht

Produktbestandteil von OpenClaw Nexus beziehungsweise `nexusctl`:

- strukturierter `doctor`-Report mit Readiness-IDs, Betriebswarnungen, Event-Chain-Integrität, DB-/Migrationsstatus, GitHub-Webhook-Vertrag und offenen Alerts;
- lokaler SQLite-Backup-, Restore-Check- und Restore-Drill-Workflow;
- secretfrei sanitisiertes Recovery-Evidence-Manifest inklusive `operator_control_boundaries`;
- GitHub-Fixture-/Webhook-Verträge, Signaturprüfung, Delivery-Idempotenz und Reconciliation-Alert-Erzeugung;
- Dokumentation der nötigen Operator-Signale und erwarteten Reaktionen.

Betreiberpflicht außerhalb des Repository-Artefakts:

- Reverse Proxy/TLS, Authentifizierung am Edge, Netzwerkgrenzen und Request-Limits;
- Secret Management, Secret-Rotation und sichere Bereitstellung von GitHub-App-/Webhook-Secrets;
- produktives Monitoring-System, Scheduler, Alert-Routing, Pager und Betriebslog;
- Offsite-Replikation, Verschlüsselung, Retention-Automation, WORM/Object-Lock und Provider-Quittungen;
- externe Audit-Signaturen, Audit-Exports oder unveränderbare Speicher für langfristige Integritätsnachweise;
- produktionsspezifische Plattformmanifeste, Ressourcenlimits und Backup-/Recovery-Compliance.

Diese Betreiberpflichten dürfen in Doctor- oder Evidence-Ausgaben höchstens als Metadaten, Statuscodes, Hashes, Aliasse oder Redaktionshinweise erscheinen. Sie werden nicht durch lokale Repository-Tests, Fixture-Grün oder ein grünes `nexusctl doctor --json` ersetzt.

## Bekannte Betriebsgrenzen

- Die HTTP-API ist für den internen Produktionsbetrieb vorbereitet und bleibt verpflichtend hinter Reverse Proxy, TLS, Secret Management und Monitoring zu betreiben.
- Interner Produktionsmodus prüft Betriebsbedingungen und macht Verstöße sichtbar, erzwingt aber kein vollständiges Deployment-, TLS- oder Secret-Management.
- GitHub-App-/Webhook-Betrieb ist fixture- und contract-abgedeckt, ersetzt aber keine Live-Verifikation gegen echte GitHub-Repositories oder echte App-Installationen.
- Event-Typen und GitHub-Sonderformen außerhalb der Fixture-Abdeckung können zusätzliche Contract-Tests benötigen, bevor sie als produktionsrelevant gelten.
- Backup-Dateien und Recovery-Evidence-Manifeste sind lokale Nachweise; der lokale Restore-Drill ist aktiver Produktbestandteil. Verschlüsselung, Offsite-Replikation, WORM-/Unveränderbarkeitsnachweise, Aufbewahrungsrichtlinien und externe Recovery-Infrastruktur sind verpflichtende Betreiberaufgaben für produktionsreife Umgebungen.
- Event-Hashing macht Manipulationen an der SQLite-Audit-Historie erkennbar, ersetzt aber keine extern signierten Audit-Exporte, WORM-Speicher oder Offsite-Backups.
- Backup/Restore muss sorgfältig zwischen laufender SQLite-Nutzung und Offline-Restore unterschieden werden.
