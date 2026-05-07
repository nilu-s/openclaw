# OpenClaw Nexus Produktüberblick

OpenClaw Nexus beschreibt eine produktionsorientierte Control Plane für kontrollierte agentische Entwicklung, bei der Governance, Nachvollziehbarkeit, Scope-Kontrolle, GitHub-Projektion und Runtime-Konfiguration aus einer gemeinsamen Control Config entstehen.

## Produktumfang

OpenClaw Nexus umfasst aktuell diese Kernbereiche:

- `nexus/*.yml` als designseitige Control Config für Domains, Agenten, Capabilities, Policies, Ziele, Schedules, GitHub-Projektion und Runtime-Tools.
- `nexusctl`-Domänenmodell mit Services für Goals, Evidence, Feature Requests, Work Items, Scope Leases, Patch Proposals, Reviews, Acceptance, Merge-Gates, GitHub-Sync, Reconciliation, Runtime-Tools und OpenClaw-Generierung.
- SQLite-State mit Migrationen, Repository-Schicht und append-only Event Store.
- CLI und HTTP-API als Interfaces auf dieselbe Businesslogik.
- GitHub-App-Abstraktion mit Projektion, Checks, PR-Bezug und Webhook-Reconciliation.
- Generierte OpenClaw-Artefakte unter `generated/*` für Agenten, Skills, Tool Policies, Schedules und Runtime-Konfiguration.
- Tests und Validatoren für Architekturgrenzen, Policy-Regeln, Runtime-Artefakte, HTTP/CLI-Parität, Merge-Gates und Delivery-Flows.

## Target-Version-Contract

OpenClaw Nexus unterstützt genau eine aktuelle Zielarchitektur. Maßgeblich sind die aktiven `nexus/*.yml`-Konfigurationen, das `nexusctl`-Domänenmodell, die App-Services, die Adaptergrenzen, die fachlich benannten Tests und die generierten OpenClaw-Artefakte unter `generated/*`.

Frühere Paketlayouts, entfernte Befehle, alte Aliasnamen, historische Importreports und archivierte Setup-Bäume sind nicht Teil des öffentlichen Produktvertrags. Neue Entwicklung richtet sich ausschließlich nach der aktuellen Zielstruktur.

Aktuelle Kontrollfeatures bleiben ausdrücklich Teil der Zielversion: Drift Detection, Reconciliation, Audit Events, Merge Staleness Gates, Policy Gates, Doctor Reports und Generated Artifact Checks sichern Integrität, Governance und Nachvollziehbarkeit.

## Sprach- und Architekturvertrag

OpenClaw Nexus verwendet absichtlich wenige offizielle Systemnamen. Der Begriff `Nexus` bleibt Projekt- und Authority-Kontext, wird aber nicht als tiefes internes Prefix-Schema für jede Komponente ausgebaut. Insbesondere sind Bezeichnungen wie `Nexus Core`, `Nexus Ledger`, `Nexus Blueprint` oder `Nexus Scheduler` keine offiziellen aktiven Komponentennamen.

| Begriff | Aktive Bedeutung | Authority-Grenze |
| --- | --- | --- |
| OpenClaw Nexus | Projekt- und Architekturkontext der lokalen Control Plane | benennt den Gesamtzusammenhang, ist aber keine einzelne ausführende Komponente |
| `nexusctl` | autoritative Control-Software mit CLI, HTTP-API, App-Services, Policy-Checks und Adaptern | entscheidet und schreibt Lifecycle-State über geprüfte Services |
| Control Config | designseitiger Soll-Zustand in `nexus/*.yml` | wird als autoritative Konfiguration behandelt und nicht durch generierte Runtime-Dateien ersetzt |
| Control Store | SQLite-State mit Repositories, Migrationen und append-only Events | hält operativen State und Audit-Historie |
| Policy Engine | Regel- und Gate-Entscheidungen in `nexusctl.authz` und zugehörigen Services | entscheidet Capabilities, Scope, Review-, Acceptance- und Merge-Gates |
| OpenClaw Runtime Config | generierte Artefakte unter `generated/*` | wird aus der Control Config erzeugt und nicht manuell gepflegt |
| OpenClaw Runtime | ausführende Agenten-/Skill-/Tool-/Schedule-Umgebung | konsumiert generierte Runtime-Konfiguration, ist aber keine Lifecycle-Authority |
| Agents | handelnde Rollen mit Domain, Rolle und Capabilities | erzeugen Requests, Proposals oder erlaubte Ausführungsschritte; sie mutieren autoritativen State nicht direkt |

Source-of-Truth-Regel: Autoritative Änderungen laufen über `nexusctl` und dessen geprüfte Services. Agents dürfen Anfragen stellen, Patch Proposals erzeugen, erlaubte Runs auslösen und delegierte Arbeit ausführen, aber keine direkte Mutation der Control Config, des Control Store, der GitHub-Lifecycle-Projektion oder der generierten OpenClaw Runtime Config als eigene Authority vornehmen. Schedule-/Cronjob-Verwaltung ist ebenfalls ein `nexusctl`-kontrollierter Flow: Agents dürfen bestehende, erlaubte Schedule-Runs triggern oder Änderungsbedarf formulieren, aber keine Runtime-Cronjobs oder generierten Schedule-Artefakte direkt ändern.

## Leitprinzipien

1. `nexusctl` ist Source of Truth für Lifecycle-Entscheidungen.
2. GitHub ist Projektion, nicht Lifecycle-Authority.
3. OpenClaw-Artefakte unter `generated/*` sind generiert und nicht manuell zu pflegen.
4. Schedules und Cronjobs werden über `nexusctl`-Schedule-/Generation-Flows kontrolliert; die OpenClaw Runtime konsumiert sie nur als generierte Konfiguration.
5. Agent-Domain, Rolle und Capabilities werden aus Authentifizierung abgeleitet.
6. Cross-Domain-Arbeit läuft über Feature Requests.
7. Builder dürfen nicht direkt mergen, reviewen oder den kanonischen Repo-Zustand ändern.
8. Reviewer dürfen nicht die Builder-Rolle ersetzen.
9. Business-Acceptance und technische Review bleiben getrennt.
10. Jede Mutation erzeugt ein append-only Event.
11. Tests sind fachlich gruppiert und an Produktverträge gekoppelt.

## Architekturüberblick

```text
nexus/*.yml
  -> nexusctl-Domänenmodell
  -> SQLite-State + Event Store
  -> CLI / HTTP API
  -> GitHub-Projektion
  -> generated/* OpenClaw Runtime
```

## Weitere Projektunterlagen

- `.chatgpt/state/CURRENT_STATE.md` beschreibt den aktuellen geprüften Ist-Zustand, bekannte Grenzen und empfohlene nächste Arbeiten.
- `.chatgpt/README.md` ist der Einstieg für projektbezogene ChatGPT-/Agent-Skills.
- `.chatgpt/skills/sprint-workflow/SKILL.md` beschreibt die aktive Skill-Anweisung für wiederholbare Änderungssprints.
- `.chatgpt/state/phases.md` hält den aktuellen Sprint-Arbeitsstand fest und darf leer sein.

## Archivierung

Archivierte Dateien dienen nur als Historie. Sie werden nicht von Validator, Testklassifizierung oder aktiver Dokumentation vorausgesetzt.
