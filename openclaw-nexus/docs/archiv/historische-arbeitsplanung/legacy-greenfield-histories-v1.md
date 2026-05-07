# OpenClaw + Nexusctl Greenfield-Phasenplan

Ziel: Das bestehende OpenClaw/Nexusctl-System wird als cleanes Greenfield-System neu realisiert, ohne Legacy-Altlasten, aber mit Erhalt und Verbesserung der vorhandenen Funktionen: Agenten, Domains, Goals, Capabilities, Runtime-Tools, Requests, Work, Scopes, Reviews, GitHub, Events, Docker, OpenClaw-Config, Skills und Cronjobs.

Arbeitsmodell: Jede Phase soll in einem neuen LLM-Chat ausführbar sein. Der Input ist immer der vollständige Projekt-Zip der vorherigen Phase plus die Anweisung: `Führ Phase X aus.` Der Output ist immer ein vollständiger neuer Projekt-Zip.
das bestehende system wird als setup beigelegt. es dient nur zur information, nicht zur verwendung und soll in jede folgende zip als referenz beigelegt werden.

## Globale Architekturregeln

1. Nexusctl ist Source of Truth für Domains, Goals, Metrics, Feature Requests, Scopes, Work, Reviews, GitHub-Sync, Schedules und Events.
2. OpenClaw ist Runtime: Agenten, Workspaces, Skills, Cronjobs, Gateway, Sessions.
3. GitHub ist sichtbare Projektions- und Kollaborationsschicht, aber nicht Lifecycle-Authority.
4. Markdown-Dateien für Agenten und Skills sind generierte Runtime-Artefakte, nicht manuelle Wahrheit.
5. Jeder Agent wird über Token authentifiziert; Nexusctl leitet daraus Agent, Domain, Rolle und Capabilities ab.
6. Normale Agenten geben keine `--domain`-Flags an; Nexusctl erkennt die Domain automatisch.
7. Cross-Domain-Arbeit läuft nur über Nexusctl Feature Requests.
8. Trading darf Software nutzen und beauftragen, aber nicht ändern.
9. Software darf technische Capabilities liefern, aber keine Trading-Ziele ändern.
10. Nur Nexusctl/GitHub-App darf Issues, Branches, PRs, Checks und Merge-Operationen auf GitHub ausführen.
11. Kein LLM-Agent bekommt direkte GitHub-Schreibrechte.
12. Kein Builder darf direkt den kanonischen Repo-Zustand verändern; er liefert Patch-Proposals oder Worktree-Diffs.
13. Jeder mutierende Vorgang erzeugt ein append-only Event.
14. Jede Phase muss Tests/Validatoren ergänzen oder aktualisieren.
15. Jede Phase muss `PROJECT_STATE.json` aktualisieren.

## Standard-Paketprotokoll für jede Phase

Jede Phase muss am Ende diese Dateien enthalten:

```text
PROJECT_STATE.json
PHASES.md
README.md
nexus/blueprint.yml
nexus/domains.yml
nexus/agents.yml
nexus/capabilities.yml
nexus/goals.yml
nexus/schedules.yml
nexus/github.yml
nexusctl/
config/
generated/
scripts/
tests/
```

`PROJECT_STATE.json` enthält mindestens:

```json
{
  "project": "openclaw-nexus-greenfield",
  "architecture_version": "greenfield-v1",
  "completed_phase": 0,
  "next_phase": 1,
  "source_of_truth": {
    "design": "nexus/*.yml",
    "runtime": "nexus.db",
    "generated": "generated/*"
  },
  "invariants": [
    "nexusctl_is_source_of_truth",
    "github_is_projection",
    "openclaw_runtime_is_generated",
    "agent_domain_is_auth_derived",
    "no_direct_agent_github_write",
    "no_direct_builder_repo_apply"
  ]
}
```

`PHASES.md` enthält diesen Plan oder eine gekürzte, aber vollständige Maschinen- und Menschenfassung.

## Ziel-Ordnerstruktur am Ende

```text
openclaw-nexus/
  README.md
  PROJECT_STATE.json
  PHASES.md

  nexus/
    blueprint.yml
    domains.yml
    agents.yml
    capabilities.yml
    goals.yml
    schedules.yml
    github.yml
    policies.yml
    standing-orders.yml

  nexusctl/
    pyproject.toml
    src/nexusctl/
      domain/
        models.py
        states.py
        policies.py
        errors.py
        events.py
      authz/
        subject.py
        capability_matrix.py
        policy_engine.py
        leases.py
      app/
        domain_service.py
        goal_service.py
        feature_request_service.py
        work_service.py
        scope_service.py
        patch_service.py
        review_service.py
        acceptance_service.py
        github_service.py
        schedule_service.py
        generation_service.py
        audit_service.py
      storage/
        sqlite/
          connection.py
          schema.py
          migrations.py
          repositories.py
        event_store.py
      adapters/
        github/
          app_auth.py
          client.py
          issues.py
          pulls.py
          checks.py
          webhooks.py
          mapper.py
        git/
          worktree.py
          diff.py
          applier.py
        openclaw/
          config_writer.py
          agent_writer.py
          skill_writer.py
          schedule_writer.py
      interfaces/
        cli/
          main.py
          commands/
            me.py
            domains.py
            goals.py
            feature_requests.py
            work.py
            scopes.py
            patches.py
            reviews.py
            acceptance.py
            github.py
            schedules.py
            generate.py
            doctor.py
        http/
          server.py
          routes.py
          schemas.py
    tests/
      unit/
      integration/
      contract/

  generated/
    openclaw/
      openclaw.json
    agents/
      operator/
      nexus/
      platform-maintainer/
      software-architect/
      software-techlead/
      software-builder/
      software-reviewer/
      trading-strategist/
      trading-analyst/
      trading-sentinel/
    skills/

  config/
    docker-compose.yml
    Dockerfile.openclaw
    Dockerfile.nexusctl
    .env.example

  scripts/
    validate_project.py
    package_project.py
    run_tests.sh
```

## Agenten und Domains

### Domains

```text
control
platform
software
trading
research (optional vorbereitet, aber nicht MVP-kritisch)
```

### Agenten

```text
control:
  operator
  nexus

platform:
  platform-maintainer

software:
  software-architect
  software-techlead
  software-builder
  software-reviewer

trading:
  trading-strategist
  trading-analyst
  trading-sentinel
```

### Grundrechte

- `operator`: User-Schnittstelle, Triage, Status, Freigaben; keine Codeänderung.
- `nexus`: Source of Truth, Routing, Scopes, Cross-Domain-Handoffs; keine Implementierung, kein Review-Approval.
- `platform-maintainer`: OpenClaw-/Docker-/Generator-/Runtime-Hygiene; keine Trading- oder Softwarefachentscheidungen.
- `software-architect`: technische Planung; keine Implementierung, kein Merge.
- `software-techlead`: technische Governance, Work-Readiness, Release-Readiness; kein eigener Build-Bypass.
- `software-builder`: Implementierung als Patch Proposal; kein Scope-Grant, kein Review, kein Merge.
- `software-reviewer`: Review und Qualitätsgate; keine Implementierung, kein Merge.
- `trading-strategist`: Strategieziele, Featurebedarf, fachliche Acceptance; keine Softwareänderung.
- `trading-analyst`: Messungen, Evidence, Backtests, Goal-Evaluation; keine Softwareänderung.
- `trading-sentinel`: Trading-Risiko, Safety-Veto, Drawdown-/Datenqualitätsüberwachung; kein allgemeiner Software-Security-Agent.

## MVP-GitHub-Prinzip

GitHub ist ab MVP enthalten. Nexusctl erstellt und synchronisiert:

- Issues für Feature Requests
- Labels für Domain, Status und Nexus-ID
- Branches für Work Items
- Pull Requests für Patch-Proposals
- PR Reviews aus Nexusctl-Reviews
- Checks/Status aus Nexusctl-Policy und CI
- Webhook-Events zurück in den Nexus-Event-Store

Nexusctl nutzt eine GitHub App. Agenten erhalten keine GitHub-Token.

---

# Phase 0 — Greenfield-Skeleton und Paketprotokoll

**Aufwand:** ca. 4 Stunden

## Ziel

Ein leeres, sauberes Greenfield-Projekt entsteht. Noch keine vollständige Business-Logik. Fokus: Ordnerstruktur, Phasenfähigkeit, Projektzustand, Validator-Grundlage.

## Kontext

Input kann das alte Clean-Zip sein, aber es wird nicht umgebaut. Es wird nur als Referenz für Funktionen verwendet. Es dürfen keine alten God-Files wie `storage.py` oder `cli.py` kopiert werden.

## Aufgaben

1. Neue Zielstruktur anlegen.
2. `PROJECT_STATE.json` mit `completed_phase=0` erstellen.
3. `PHASES.md` mit Phasenübersicht erstellen.
4. `README.md` mit Architekturleitsätzen erstellen.
5. `scripts/validate_project.py` anlegen.
6. `scripts/package_project.py` anlegen.
7. Leere Python-Package-Struktur für `nexusctl` erstellen.
8. Minimalen `pyproject.toml` erstellen.
9. Platzhaltertests für Strukturvalidierung anlegen.

## Akzeptanzkriterien

- `python scripts/validate_project.py` läuft grün.
- `python scripts/package_project.py` erzeugt ein vollständiges Zip.
- Keine alten Agent-MD-Dateien aus dem Legacy-Paket sind vorhanden.
- Keine Datei `storage.py` mit Legacy-Inhalt existiert.
- Keine Datei `cli.py` mit Legacy-Inhalt existiert.

## Nicht tun

- Keine alten Nexusctl-Implementierungen kopieren.
- Keine OpenClaw-Config manuell schreiben außer als Platzhalter.
- Kein GitHub-Code.

---

# Phase 1 — Blueprint als Design-Source-of-Truth

**Aufwand:** ca. 4 Stunden

## Ziel

Alle Domains, Agenten, Rollen, Capabilities, Goals, Schedules und GitHub-Mappings sind deklarativ in `nexus/*.yml` beschrieben.

## Aufgaben

1. `nexus/blueprint.yml` erstellen.
2. `nexus/domains.yml` erstellen.
3. `nexus/agents.yml` mit allen 10 Agenten erstellen.
4. `nexus/capabilities.yml` erstellen.
5. `nexus/goals.yml` mit mindestens Trading- und Software-Beispielzielen erstellen.
6. `nexus/schedules.yml` mit MVP-Cronjobs erstellen.
7. `nexus/github.yml` mit Repo-, Label- und Workflow-Projektion erstellen.
8. `nexus/policies.yml` mit harten Domain- und Capability-Regeln erstellen.
9. `nexus/standing-orders.yml` erstellen; Inhalte sind Quelle für später generierte `AGENTS.md`.
10. Validator erweitern: Schema, IDs, Referenzen, keine unbekannten Agenten/Skills.

## Mindest-Goals

Trading:

```text
trade_success_quality:
  win_rate >= 60%
  average_profit_pct >= 5%
  max_drawdown_pct <= 12%
  min_sample_size >= 50
  window = rolling_90d
```

Software:

```text
software_delivery_quality:
  tests_required = true
  review_required = true
  no_scope_violation = true
```

Platform:

```text
runtime_integrity:
  generated_drift = 0
  backup_success = true
```

## Akzeptanzkriterien

- Alle Agenten haben genau eine Domain.
- Normale Agenten haben keine Cross-Domain-Mutating-Capabilities.
- Trading-Agenten haben keine Software-Code-Capabilities.
- Software-Agenten haben keine Trading-Strategy-Mutation-Capabilities.
- GitHub wird als Projection gekennzeichnet, nicht als Source of Truth.

---

# Phase 2 — Nexusctl Domain Model und Policy-Grundlage

**Aufwand:** ca. 4 Stunden

## Ziel

Der Python-Kern bekommt saubere Domain-Modelle, States, Errors und eine erste Policy Engine. Noch ohne DB-Persistenz.

## Aufgaben

1. `domain/models.py` mit Dataclasses/Pydantic-Modellen für Domain, Agent, Goal, Metric, FeatureRequest, WorkItem, ScopeLease, Review, GitHubLink anlegen.
2. `domain/states.py` mit Status-Enums anlegen.
3. `domain/errors.py` anlegen.
4. `authz/subject.py` anlegen: `Subject(agent_id, domain, role, capabilities)`.
5. `authz/capability_matrix.py` aus Blueprint laden.
6. `authz/policy_engine.py` implementieren.
7. Unit-Tests für Policy-Regeln.

## Akzeptanzkriterien

- `trading-strategist` darf `feature_request.create` mit target `software`, aber nicht `patch.submit`.
- `software-builder` darf `patch.submit`, aber nicht `review.approve` oder `repo.apply`.
- `nexus` darf routen und Scopes vergeben, aber nicht Review-Approval simulieren.
- Domain-Override für normale Agenten ist verboten.

---

# Phase 3 — SQLite Storage, Migrationen und Event Store

**Aufwand:** ca. 4 Stunden

## Ziel

Schlanke persistente Nexus-Datenbank ohne God-Object. Event-Store ist append-only.

## Aufgaben

1. `storage/sqlite/connection.py` implementieren.
2. `storage/sqlite/schema.py` implementieren.
3. `storage/sqlite/migrations.py` implementieren.
4. Repositories minimal aufbauen.
5. Event-Store mit append-only Triggern implementieren.
6. DB-Init-Command vorbereiten.
7. Tests für Schema und Event-Append-Only.

## MVP-Tabellen

```text
agents
domains
domain_memberships
capabilities
goals
goal_metrics
goal_measurements
goal_evaluations
feature_requests
work_items
scope_leases
patch_proposals
reviews
acceptances
evidence
events
github_repositories
github_issue_links
github_pull_links
github_webhook_events
schedule_runs
backups
```

## Akzeptanzkriterien

- DB kann aus Blueprint initialisiert werden.
- Events können nicht aktualisiert oder gelöscht werden.
- Alle mutierenden Repository-Methoden schreiben Event-Records oder sind dafür vorbereitet.

---

# Phase 4 — Auth, Agent Identity und `nexusctl me`

**Aufwand:** ca. 4 Stunden

## Ziel

Nexusctl erkennt Agent, Domain, Rolle und Capabilities aus einem verifizierten Token. Agenten müssen ihre Domain nicht angeben.

## Aufgaben

1. Token-Hashing und Agent Registry implementieren.
2. Session-Ausgabe mit TTL implementieren.
3. CLI-Kommandos:
   - `nexusctl me --json`
   - `nexusctl me capabilities --json`
   - `nexusctl auth login --agent <id>` für lokale Tests
   - `nexusctl auth rotate-token <agent>` nur für control/platform erlaubt
4. `--domain` für normale Agent-Kommandos verbieten.
5. Tests für Domain-Auflösung.

## Akzeptanzkriterien

- `trading-analyst` ruft `nexusctl goals status --json` ohne Domain-Flag auf und sieht nur Trading-Sicht.
- `trading-analyst --domain software` wird abgelehnt.
- `nexus --domain trading` ist für read/routing erlaubt, je nach Policy.

---

# Phase 5 — Domain Goals, Metrics, Evidence und Evaluation

**Aufwand:** ca. 4 Stunden

## Ziel

Goals werden aus Nexusctl verwaltet und gemessen, nicht in Markdown gesucht.

## Aufgaben

1. `goal_service.py` implementieren.
2. Commands:
   - `nexusctl goals list --json`
   - `nexusctl goals status --json`
   - `nexusctl goals show <goal> --json`
   - `nexusctl goals measure <goal> --json`
   - `nexusctl goals evaluate <goal> --json`
   - `nexusctl evidence add --goal <goal> --file <path> --json`
3. Modelle für Metric, Measurement, Evaluation implementieren.
4. Trading-Beispielziel testbar machen.
5. Events für Messung/Evaluation schreiben.

## Akzeptanzkriterien

- Trading-Agenten sehen Trading-Goals ohne Domain-Flag.
- Software-Agenten sehen keine Trading-Goals, außer über konkreten FeatureRequest-Kontext.
- Goal-Evaluation ergibt `passing`, `warning`, `failing` oder `unknown`.
- Evidence ist referenziert und auditierbar.

---

# Phase 6 — Cross-Domain Feature Requests

**Aufwand:** ca. 4 Stunden

## Ziel

Domains können Bedarf an andere Domains formulieren. Trading kann Software-Features anfordern, aber keine Software-Scopes bekommen.

## Aufgaben

1. `feature_request_service.py` implementieren.
2. Commands:
   - `nexusctl feature-request create --target <domain> --goal <goal> --title <title> --json`
   - `nexusctl feature-request list --json`
   - `nexusctl feature-request show <id> --json`
   - `nexusctl feature-request route <id> --target <domain> --json`
   - `nexusctl feature-request transition <id> <status> --json`
3. Acceptance- und Safety-Contracts modellieren.
4. Dedupe-Key und Audit-Events implementieren.
5. Policy: Source-Domain kommt aus Subject, nicht aus CLI.

## Akzeptanzkriterien

- `trading-strategist` erzeugt FeatureRequest an `software`.
- Request enthält `source_domain=trading`, automatisch.
- Trading-Agent kann keinen Request mit `source_domain=software` fälschen.
- Nexus kann Request routen.

---

# Phase 7 — GitHub App Grundintegration und Issue-Projektion

**Aufwand:** ca. 4 Stunden

## Ziel

Feature Requests erscheinen als GitHub Issues. GitHub ist Projektion, Nexusctl bleibt Authority.

## Aufgaben

1. `adapters/github/app_auth.py` implementieren.
2. `adapters/github/client.py` implementieren mit Mock-Modus.
3. `github_service.py` Grundfunktionen.
4. Commands:
   - `nexusctl github app status --json`
   - `nexusctl github repos sync --json`
   - `nexusctl github labels sync --json`
   - `nexusctl github issue sync <feature_request_id> --json`
5. Issue-Templates und Labels aus `nexus/github.yml` generieren.
6. Tests mit Fake-GitHub-Client.

## GitHub-Mapping

- `FeatureRequest` -> Issue
- `nexus:<id>` -> Label
- `domain:<source>` -> Label
- `target:<target>` -> Label
- `status:<state>` -> Label
- Acceptance/Safety -> Issue Body Sections

## Akzeptanzkriterien

- FeatureRequest-Erstellung kann automatisch Issue-Projektion erzeugen.
- GitHub API ist austauschbar/mockbar.
- Keine Agenten bekommen GitHub-Token.
- Fehlende GitHub-Credentials blockieren lokale Tests nicht.

---

# Phase 8 — Software Work, Scope Leases und Planning

**Aufwand:** ca. 4 Stunden

## Ziel

Software-Domain kann geroutete Feature Requests planen und engen Work-Scope vergeben bekommen.

## Aufgaben

1. `work_service.py` implementieren.
2. `scope_service.py` implementieren.
3. Commands:
   - `nexusctl work plan <feature_request_id> --json`
   - `nexusctl work assign <feature_request_id> --builder <agent> --reviewer <agent> --json`
   - `nexusctl work show <id> --json`
   - `nexusctl scopes lease --agent <agent> --request <id> --paths <glob> --ttl <duration> --json`
   - `nexusctl scopes revoke <lease_id> --json`
4. Path-Scope-Modell implementieren.
5. TTL und Expiry implementieren.

## Akzeptanzkriterien

- Nur `nexus` oder berechtigte Control-Policy kann Scope-Leases erteilen.
- `software-builder` kann Lease nutzen, aber nicht selbst erteilen.
- Trading-Agenten können keine Software-Lease erhalten.
- Work Item verweist auf FeatureRequest und GitHub Issue.

---

# Phase 9 — Patch Proposal, Git Worktree und Branch-Push

**Aufwand:** ca. 4 Stunden

## Ziel

Builder erzeugt Patch-Proposals. Nexusctl validiert Diff gegen Scope und pusht Branches nach GitHub.

## Aufgaben

1. `adapters/git/worktree.py`, `diff.py`, `applier.py` implementieren.
2. `patch_service.py` implementieren.
3. Commands:
   - `nexusctl work start <id> --json`
   - `nexusctl patch submit <work_or_request_id> --from-worktree <path> --json`
   - `nexusctl patch show <id> --json`
   - `nexusctl github pr create <id> --json`
4. Diff-Path-Validation gegen Scope-Leases.
5. Branch-Erzeugung und Push durch Nexusctl/GitHub-App oder lokalem Bot-Remote.
6. PR-Erstellung via GitHub-Adapter.

## Akzeptanzkriterien

- Patch außerhalb erlaubter Pfade wird abgelehnt.
- Builder kann keinen Merge ausführen.
- Nexusctl erstellt Branch/PR und verknüpft PR mit FeatureRequest.
- Alle GitHub-Schreiboperationen laufen über Nexusctl.

---

# Phase 10 — Checks, CI-Sync und Policy Gates

**Aufwand:** ca. 4 Stunden

## Ziel

Nexusctl synchronisiert GitHub Actions/Checks und erzeugt eigene Policy-Checks.

## Aufgaben

1. `adapters/github/checks.py` implementieren.
2. `github checks sync` implementieren.
3. Policy-Checks definieren:
   - scope respected
   - required review pending/passed
   - acceptance pending/passed
   - no safety veto
   - head SHA matches validated patch
4. Commands:
   - `nexusctl github checks sync <id> --json`
   - `nexusctl policy check <id> --json`
5. Tests für Gate-Kombinationen.

## Akzeptanzkriterien

- PR ohne grüne Checks kann nicht gemerged werden.
- PR mit geändertem Head-SHA nach Review benötigt neue Prüfung.
- Nexusctl kann Check-Status als Event speichern.

---

# Phase 11 — Software Review und Trading Acceptance

**Aufwand:** ca. 4 Stunden

## Ziel

Review und fachliche Abnahme werden getrennt. Software-Review ist nicht Trading-Acceptance.

## Aufgaben

1. `review_service.py` implementieren.
2. `acceptance_service.py` implementieren.
3. Commands:
   - `nexusctl review queue --json`
   - `nexusctl review submit <id> --verdict approved|changes-requested|rejected --json`
   - `nexusctl acceptance submit <id> --verdict accepted|rejected --json`
   - `nexusctl acceptance status <id> --json`
4. GitHub PR Review Mapping implementieren.
5. Issue/PR Labels für Acceptance aktualisieren.

## Akzeptanzkriterien

- Software-Reviewer darf Review schreiben, aber keine fachliche Trading-Acceptance.
- Trading-Strategist darf fachlich akzeptieren, aber keinen Software-Review ersetzen.
- Trading-Sentinel kann Safety-Veto einreichen.
- Merge-Gate verlangt technische und fachliche Gates passend zum Request.

---

# Phase 12 — Merge/Apply Gate und GitHub Merge

**Aufwand:** ca. 4 Stunden

## Ziel

Nur Nexusctl-Applier merged nach erfolgreichen Gates.

## Aufgaben

1. Merge-Service implementieren.
2. Command:
   - `nexusctl merge <feature_request_or_pr_id> --json`
3. Merge-Gate prüft:
   - Scope eingehalten
   - PR Head SHA aktuell
   - Required checks grün
   - Software Review approved
   - Trading Acceptance vorhanden, wenn source_domain=trading
   - Kein Safety-Veto
   - Keine offenen kritischen GitHub Alerts
4. GitHub PR Merge via Adapter.
5. FeatureRequest/Work Status nach Merge aktualisieren.

## Akzeptanzkriterien

- Manuelle oder unautorisierte GitHub-Merges werden als Incident/Event erkannt, sobald Webhook-Sync aktiv ist.
- Builder/Reviewer können Merge-Command nicht erfolgreich ausführen.
- Nexusctl aktualisiert GitHub Issue/PR Labels nach Merge.

---

# Phase 13 — GitHub Webhooks und Reconciliation

**Aufwand:** ca. 4 Stunden

## Ziel

GitHub-Änderungen werden zurückgespiegelt, signiert geprüft und gegen Nexusctl-Policy bewertet.

## Aufgaben

1. `adapters/github/webhooks.py` implementieren.
2. HTTP-Route für Webhooks.
3. Signaturprüfung.
4. Persistenz von `github_webhook_events`.
5. Verarbeitung für:
   - issues
   - issue_comment
   - pull_request
   - pull_request_review
   - check_run
   - workflow_run
   - push
6. Command:
   - `nexusctl github reconcile --json`
   - `nexusctl github webhook verify --json`

## Akzeptanzkriterien

- Replay/duplicate delivery wird idempotent behandelt.
- Unbekannte GitHub-Änderung erzeugt Alert, nicht stillen State-Drift.
- GitHub-Labels werden auf Nexusctl-State zurückgeführt.

---

# Phase 14 — OpenClaw Generator: Config, Agents, Skills

**Aufwand:** ca. 4 Stunden

## Ziel

OpenClaw-Runtime-Artefakte werden aus Nexus-Blueprint generiert. Keine manuell gepflegten Agent-MDs.

## Aufgaben

1. `generation_service.py` implementieren.
2. `adapters/openclaw/config_writer.py` implementieren.
3. `agent_writer.py` implementieren.
4. `skill_writer.py` implementieren.
5. Commands:
   - `nexusctl generate openclaw --json`
   - `nexusctl generate agents --json`
   - `nexusctl generate skills --json`
   - `nexusctl doctor --json`
6. Generierte Dateien mit Header und Checksum versehen.
7. Skill-Allowlists pro Agent generieren.
8. Tool-Policies pro Agent generieren.

## Generierte Agent-Dateien

```text
AGENTS.md
SOUL.md
TOOLS.md
IDENTITY.md
USER.md
HEARTBEAT.md
BOOTSTRAP.md
MEMORY.md
```

## Akzeptanzkriterien

- `generated/agents/*` wird vollständig aus `nexus/*.yml` erzeugt.
- Manuelle Änderung in `generated/*` wird durch Checksum erkannt.
- OpenClaw-Agenten haben eigene `agentDir` und Workspaces.
- Skills sind pro Agent final allowlisted.

---

# Phase 15 — Schedules, Cronjobs und Standing Orders

**Aufwand:** ca. 4 Stunden

## Ziel

Cronjobs werden aus Nexus-Blueprint nach OpenClaw gerendert. Standing Orders definieren das Was, Cron das Wann.

## Aufgaben

1. `schedule_service.py` implementieren.
2. `adapters/openclaw/schedule_writer.py` implementieren.
3. Commands:
   - `nexusctl schedules list --json`
   - `nexusctl schedules validate --json`
   - `nexusctl schedules render-openclaw --json`
   - `nexusctl schedules reconcile-openclaw --json`
   - `nexusctl schedules run <schedule> --dry-run --json`
4. Standing Orders aus `nexus/standing-orders.yml` in generierte Agent-Dateien integrieren.
5. Schedule-Run-Events implementieren.

## MVP-Schedules

Control:
- `nexus_domain_inbox_triage`
- `nexus_scope_expiry_guard`

Software:
- `software_review_queue_check`
- `software_release_readiness`

Trading:
- `trading_goal_daily_evaluation`
- `trading_risk_daily_audit`
- `trading_feature_need_detection`

Platform:
- `platform_generated_runtime_drift`
- `platform_db_backup`

## Akzeptanzkriterien

- Keine autonomen Builder-Cronjobs.
- Trading-Cronjobs können Feature Requests erzeugen, aber keine Software ändern.
- Cron-Prompts referenzieren Standing Orders statt sie zu duplizieren.

---

# Phase 16 — Docker Compose Runtime

**Aufwand:** ca. 4 Stunden

## Ziel

OpenClaw und Nexusctl laufen containerisiert mit klaren Volumes und Schreibrechten.

## Aufgaben

1. `config/Dockerfile.nexusctl` erstellen.
2. `config/Dockerfile.openclaw` oder dokumentierter OpenClaw-Image-Wrapper erstellen.
3. `config/docker-compose.yml` erstellen.
4. Services:
   - `openclaw-gateway`
   - `nexusctl-api`
   - `nexusctl-worker`
   - `nexusctl-cli`
5. Volumes:
   - `nexus-data`
   - `generated-openclaw:ro` für OpenClaw
   - `workspaces`
   - `repo-worktrees`
6. `.env.example` mit GitHub-App-Variablen.
7. Healthchecks.

## Akzeptanzkriterien

- Nexusctl DB liegt in persistentem Volume.
- OpenClaw bekommt generated config/skills read-only.
- Agenten-Workspaces sind getrennt.
- Nexusctl kann CLI in Container ausführen.

---

# Phase 17 — Runtime Tools und Guardrails

**Aufwand:** ca. 4 Stunden

## Ziel

Die alte Runtime-Tools-Funktion bleibt erhalten, aber domain-sicherer.

## Aufgaben

1. Runtime Tool Registry modellieren.
2. Commands:
   - `nexusctl runtime-tools list --json`
   - `nexusctl runtime-tools show <id> --json`
   - `nexusctl runtime-tools check <id> --json`
3. Guardrail-Entscheidungen:
   - allow
   - deny
   - approval_required
4. Side-effect levels:
   - read_only
   - simulation
   - paper_trade
   - live_trade
   - destructive
5. Trading-spezifische Tools nur read/simulation/paper im MVP.
6. Live-Trade-Tools blockiert oder human approval required.

## Akzeptanzkriterien

- Toolzugriff wird über Nexusctl geprüft.
- Trading-Agenten können keine Software-Tools invoke'n.
- Live-/destructive Tools sind standardmäßig blockiert.

---

# Phase 18 — HTTP API und Agent/API-Stabilisierung

**Aufwand:** ca. 4 Stunden

## Ziel

Neben CLI existiert eine schlanke HTTP API für OpenClaw/GitHub-Webhooks/Worker.

## Aufgaben

1. `interfaces/http/server.py` implementieren.
2. Routes modularisieren.
3. Auth-Middleware.
4. JSON-Schema/Validation.
5. Endpunkte für:
   - auth/me
   - goals
   - feature-requests
   - work
   - reviews
   - github/webhook
   - schedules
6. API-Client optional.

## Akzeptanzkriterien

- CLI und HTTP nutzen dieselben App-Services.
- Keine doppelte Businesslogik in CLI/HTTP.
- Webhook-Route ist isoliert und signaturgeprüft.

---

# Phase 19 — Migration/Importer aus altem Clean-Paket

**Aufwand:** ca. 4 Stunden

## Ziel

Optionaler Importer liest alte Funktionen/Daten, aber übernimmt keine Legacy-Struktur.

## Aufgaben

1. Import-Script erstellen:
   - alte Agentenrollen -> neue Domain-Agenten prüfen
   - alte Goals -> neue Goals/Metrics soweit möglich
   - alte Capabilities -> neue Capabilities
   - alte GitHub-Repo-Config -> `nexus/github.yml`
2. Import nur als einmaliger Konverter, nicht Runtime-Abhängigkeit.
3. Report erzeugen: übernommen, manuell zu prüfen, verworfen.

## Akzeptanzkriterien

- Kein Legacy-Code wird ins Runtime-Paket kopiert.
- Import ist idempotent.
- Import erzeugt Review-Report.

---

# Phase 20 — End-to-End MVP-Demo und Hardening

**Aufwand:** ca. 4 Stunden

## Ziel

Kompletter Ablauf funktioniert von Trading-Goal bis GitHub PR und Merge-Gate.

## Demo-Szenario

1. `trading-analyst` evaluiert `trade_success_quality`.
2. Fehlende Capability wird erkannt.
3. `trading-strategist` erstellt FeatureRequest an Software.
4. Nexusctl erstellt GitHub Issue.
5. `nexus` routet an Software.
6. `software-architect` plant.
7. `nexus` erteilt Scope-Lease an Builder.
8. `software-builder` submit't Patch Proposal.
9. Nexusctl erstellt Branch und PR.
10. Checks laufen/synchronisieren.
11. `software-reviewer` approved.
12. `trading-strategist` akzeptiert fachlich.
13. Nexusctl merged via GitHub App.
14. Events zeigen komplette Audit-Chain.

## Aufgaben

1. E2E-Test implementieren mit Fake-GitHub oder Test-Repo-Modus.
2. Validator komplettieren.
3. README finalisieren.
4. Security-Invarianten testen.
5. Paketierung finalisieren.

## Akzeptanzkriterien

- Voller E2E-Flow läuft lokal im Testmodus.
- Kein Agent kann Domain-Grenzen umgehen.
- GitHub-Projektion ist nachvollziehbar.
- OpenClaw-Artefakte sind generiert und driftgeprüft.
- Docker Compose startet Kernservices.

---

## Phasenabhängigkeiten

```text
0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17 -> 18 -> 20
                                      \-> 19 optional vor 20
```

Phase 19 ist optional und sollte erst ausgeführt werden, wenn der Greenfield-Kern stabil ist.

## Pro Phase verpflichtende Ausgabe

Jede Phase muss am Ende im finalen Chat antworten mit:

```text
Phase X abgeschlossen.
Geänderte Kernbereiche: ...
Validierung: ...
Nicht erledigt / bewusst vertagt: ...
Nächste Phase: X+1
Download: <zip>
```

## Drift-Schutz je Phase

Jede Phase muss prüfen:

1. Keine manuell gepflegten Dateien in `generated/*` ohne Checksum.
2. Keine Agentenrolle ohne Domain.
3. Keine Domain-Override-Möglichkeit für normale Agenten.
4. Keine direkten GitHub-Schreibrechte für Agenten.
5. Keine direkte Repo-Apply-Fähigkeit für Builder.
6. Alle Mutationen gehen durch App-Services.
7. CLI und HTTP enthalten keine Businesslogik, nur Interface-Code.
8. GitHub-Mapping verweist immer auf Nexus-ID.
9. Jeder mutierende Vorgang schreibt Event.
10. `PROJECT_STATE.json` ist aktuell.

## Schlanke MVP-Grenze

MVP heißt hier nicht minimal im Sinne von unfertig, sondern minimal im Sinne von klar:

- Domains funktionieren.
- Goals funktionieren.
- Cross-Domain-Requests funktionieren.
- GitHub Issues/PRs funktionieren.
- Scope/Review/Acceptance/Merge-Gates funktionieren.
- OpenClaw-Artefakte werden generiert.
- Cronjobs sind definiert und renderbar.
- Docker Runtime ist vorhanden.

Nicht im MVP:

- Live-Trading-Ausführung.
- Komplexe GitHub Projects v2 Dashboards.
- Vollständige Research-Domain-Automation.
- Freie Third-Party-Skills.
- Autonome Builder-Cronjobs.
