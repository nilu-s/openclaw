# Endzustand: OpenClaw Nexus Zielarchitektur

Status: stabiler Konzeptanker  
Änderungsregel: Diese Datei soll nach ihrer Einführung nicht in jeder Entwicklungsphase fortgeschrieben werden. Laufende Arbeit, Fortschritt und Phasenstatus gehören ausschließlich in `phasen.md`.

## 1. Zielbild

OpenClaw Nexus ist eine kontrollierte Multi-Agent-Control-Plane. Nexusctl verwaltet die fachliche Wahrheit, OpenClaw führt Agenten aus, und GitHub zeigt Projektionszustände für Menschen, Reviews und CI an.

Der Zielzustand ist erreicht, wenn das System folgende Eigenschaften dauerhaft erfüllt:

- Nexusctl ist die einzige Lifecycle-Authority.
- GitHub ist Projektions- und Kollaborationsfläche, aber keine Quelle für Work-, Review-, Acceptance- oder Merge-Entscheidungen.
- OpenClaw-Agenten, Skills, Tool-Policies, Allowlists und Schedules werden aus `nexus/*.yml` generiert.
- Generierte Artefakte enthalten Checksums und können durch `doctor` auf Drift geprüft werden.
- Agenten erhalten keine direkten GitHub-Schreibrechte.
- Builder arbeiten ausschließlich über Scope Leases und Patch Proposals.
- Reviewer, Builder, Business-Acceptance und Applier sind getrennte Verantwortlichkeiten.
- Jede Mutation ist append-only auditierbar.

## 2. Schichtenmodell

```text
nexus/*.yml
  -> Domain Models + Capability Matrix + Policy Engine
  -> App Services
  -> SQLite Storage + Event Store
  -> Adapter: GitHub, Git, OpenClaw
  -> Interfaces: CLI und HTTP
  -> generated/* Runtime-Artefakte
```

## 3. Verantwortlichkeiten

### `nexus/*.yml`

Design-Source-of-Truth für Domains, Agenten, Capabilities, Ziele, Policies, Runtime Tools, Schedules und GitHub-Projektionsregeln.

### `nexusctl/src/nexusctl/domain/`

Enthält reine Domänenmodelle, Statuswerte, Fehler und fachliche Value Objects. Diese Schicht kennt keine CLI, keine HTTP-Details und keine konkreten SQL-Statements.

### `nexusctl/src/nexusctl/authz/`

Enthält Identität, Token-/Session-Ableitung, Capability Matrix und Policy Engine. Die Authz-Schicht beantwortet: Wer handelt? Aus welcher Domain? Mit welcher Rolle? Welche Capability ist erlaubt? Welche globale Invariante darf nie verletzt werden?

### `nexusctl/src/nexusctl/app/`

Enthält Use-Case-Services. App-Services orchestrieren Domänenlogik, Persistenz, Events, Checks und Adapter. Sie dürfen fachliche Entscheidungen treffen, sollen aber langfristig nicht direkt SQL über das ganze Projekt verteilen.

### `nexusctl/src/nexusctl/storage/`

Enthält SQLite-Verbindung, Schema, Migrationen, Repositories und Event Store. Ziel ist eine konsequente Repository-Schicht, damit SQL nicht über App-Services und Interfaces verstreut bleibt.

### `nexusctl/src/nexusctl/adapters/`

Kapselt externe oder externe-ähnliche Systeme: GitHub, Git-Worktrees und OpenClaw-Generierung. Adapter müssen mockbar bleiben.

### `nexusctl/src/nexusctl/interfaces/`

Enthält CLI und HTTP. Interfaces validieren Eingaben, authentifizieren Requests und rufen App-Services auf. Sie sollen keine eigenständige Business-Logik enthalten.

## 4. Sicherheitsinvarianten

1. `agent_domain_is_auth_derived`
2. `github_is_projection`
3. `openclaw_runtime_is_generated`
4. `no_direct_agent_github_write`
5. `no_direct_builder_repo_apply`
6. `builder_no_review_or_merge`
7. `reviewer_no_builder_substitution`
8. `merge_only_nexusctl_applier`
9. `cross_domain_work_uses_feature_requests`
10. `events_append_only`

## 5. Ziel-Workflow

```text
Goal / Need
  -> Feature Request
  -> Nexus Routing
  -> Work Item
  -> Scope Lease
  -> Patch Proposal
  -> Policy Checks
  -> Software Review
  -> Business Acceptance
  -> Safety Gate
  -> nexus-applier Merge
  -> GitHub Projection + Audit Event
```

## 6. Zielzustand der Dokumentation

- `README.md` erklärt das Projekt, verlinkt Konzept und Phasensteuerung und bleibt bewusst schlank.
- `endzustand.md` definiert dieses stabile Zielbild.
- `phasen.md` ist die einzige Datei für laufende Phasen, Fortschritt und aktuelle Phase.
- Alte Phasenpläne werden unter `docs/archiv/phasen/` abgelegt und nicht weiter im aktiven Phasendokument mitgeführt.

## 7. Zielzustand der nächsten Verbesserungsrunde

Nach Abschluss der nächsten Verbesserungsphasen soll das Projekt folgende zusätzliche Eigenschaften haben:

- Die CLI ist modularisiert; `interfaces/cli/main.py` ist nur noch Einstiegspunkt und Dispatcher.
- Wiederholtes Service-Wiring ist in einer zentralen Runtime-/Unit-of-Work-Abstraktion gekapselt.
- App-Services nutzen Repositories konsequenter und enthalten weniger direktes SQL.
- HTTP und CLI teilen dieselben Use Cases und Policy-Prüfungen.
- Aus der Referenz übernommene gute Operational-Details sind integriert, ohne das Storage-God-Object-Modell zu übernehmen.
- Tests sind in schnelle, langsame und Integrationssuiten markiert und blockieren nicht unkontrolliert.
- `doctor`, Audit-Reports und Dokumentation zeigen Architekturdrift klar an.
