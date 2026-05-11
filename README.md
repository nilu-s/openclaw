# OpenClaw Nexus

OpenClaw Nexus ist eine lokale Control Plane für agentengestützte Software- und Projektarbeit mit OpenClaw. `nexusctl` bildet die fachliche Steuerungsschicht für Ziele, Domains, Agentenrollen, Capabilities, Feature Requests, Work Items, Scope Leases, Patch Proposals, Reviews, Business-Acceptance, Merge-Gates, GitHub-Projektionen, Runtime-Generierung und Audit-Events.

Das Projekt trennt bewusst Verantwortlichkeiten:

- Nexusctl ist die Source of Truth für Lifecycle-Entscheidungen; konkret mutiert `nexusctl` autoritativen State nur über geprüfte Services.
- GitHub ist Kollaborations- und Projektionsfläche, aber keine Lifecycle-Authority.
- OpenClaw ist die Runtime und erhält generierte Artefakte aus der Control Config.
- Agents arbeiten rollen-, domain- und capability-basiert; sie erzeugen Requests/Proposals oder erlaubte Ausführungsschritte, sind aber nicht selbst Source of Truth.
- Reviews, Business-Acceptance und Merge-Ausführung sind getrennte Verantwortlichkeiten.
- Jede fachliche Mutation wird über append-only Events nachvollziehbar.

## Einstieg

| Thema | Datei |
| --- | --- |
| Produktumfang, Zielarchitektur, Sprachkontrakt und Leitprinzipien | [`docs/product/overview.md`](docs/product/overview.md) |
| Architekturindex und aktive Architekturverträge | [`docs/architecture/index.md`](docs/architecture/index.md) |
| Feature-Manifest, README-Konvention und erstes Feature-Inventar | [`docs/architecture/feature-manifest-contract.md`](docs/architecture/feature-manifest-contract.md) |
| Lokale Nutzung und Testläufe | [`docs/product/local-development.md`](docs/product/local-development.md) |
| Interner Betrieb, Produktionsprofil, Backup und Restore | [`docs/operations/internal-production.md`](docs/operations/internal-production.md) |
| Deployment-Strategie inklusive geführtem Wizard, Volumes, Tokens, Rollout und Rollback | [`docs/operations/deployment-strategy.md`](docs/operations/deployment-strategy.md) |
| Operations-Runbooks fuer Installation, Upgrade, Rollback, Restore, Rotation, Incident und Reconciliation | [`docs/operations/runbooks.md`](docs/operations/runbooks.md) |
| Change-Governance fuer ADRs, Releases, Breaking Changes, Migrationen und Deprecations | [`docs/architecture/change-governance.md`](docs/architecture/change-governance.md) |
| ChatGPT-/Agent-Arbeitsbereich | [`.chatgpt/README.md`](.chatgpt/README.md) |
| Aktueller geprüfter Projektzustand | [`.chatgpt/state/CURRENT_STATE.md`](.chatgpt/state/CURRENT_STATE.md) |
| Aktives Sprint-Log | [`.chatgpt/state/phases.md`](.chatgpt/state/phases.md) |

## Projektstruktur

```text
openclaw-nexus/
  README.md                 # schlanker Einstieg und Link-Hub
  .chatgpt/                 # ChatGPT-/Agent-Skills und aktive Arbeitszustände
    state/                  # CURRENT_STATE.md und phases.md
    skills/                 # wiederverwendbare Agent-Skills
  docs/product/             # Produkt-, Architektur- und lokale Entwicklungsdoku
  docs/operations/          # Betriebsdokumentation
  docs/archiv/              # historische Dokumente und archivierte Referenzen
  nexus/                    # Control Config und designseitiger Soll-Zustand
  nexusctl/                 # Python-Paket für CLI, HTTP, App-Services und Adapter
  generated/                # generierte OpenClaw-Artefakte
  config/                   # Docker- und Umgebungsbeispiele
  scripts/                  # Validierung, Testlauf, Packaging
  tests/                    # fachlich benannte Tests
```

## Kurzbefehle

Geführtes Deployment-Bundle erzeugen:

```bash
python scripts/deployment_wizard.py
```

Projektvalidierung:

```bash
python scripts/validate_project.py
```

Tests und Batch-Planung:

```bash
./scripts/run_tests.sh verify-plan
./scripts/run_tests.sh list unit
./scripts/run_tests.sh smoke
./scripts/run_tests.sh batch smoke-contracts
```

Hinweis zu Sandbox-Timeouts:

Wenn ein Lauf in einer Sandbox, einem CI-Job, Editor-Agenten oder ähnlichen Harness mit einer Meldung wie `command failed because it timed out` abbricht, ist das kein Pytest-Fehler und kein Timeout aus `scripts/run_tests.sh`. Diese Meldung kommt von der äußeren Ausführungsumgebung, die den gesamten Prozess beendet hat. OpenClaw Nexus vermeidet das strukturell, indem große Suites nicht als ein Shell-Command ausgeführt werden. Stattdessen erzeugt `scripts/test_scheduler.py` kurze, deterministische Batches mit hartem internem Batchlimit.

Für enge Agent-/Sandbox-Harnesses sind `./scripts/run_tests.sh verify-plan`, `./scripts/run_tests.sh list <suite>` und `./scripts/run_tests.sh batch <batch-id>` die dokumentierten Diagnosepfade. Die vollständige Testabdeckung läuft über viele einzelne Batch-Kommandos, lokal oder in CI als Matrix. Die verbindliche Test-Policy liegt unter `.chatgpt/testing/test-policy.md`.

OpenClaw-Artefakte liegen unter `generated/*` und werden aus der Control Config in `nexus/*.yml` abgeleitet. Sie beschreiben den Runtime-Zustand, der von OpenClaw konsumiert werden kann.

## Dokumentationsregel

Die Root-README bleibt bewusst kurz. Produkt- und Betriebsdetails liegen unter `docs/`, während entwicklungs- und agentenbezogene Arbeitsdateien unter `.chatgpt/` gepflegt werden.
nInternalnInternal
Live push verification 1778543415
