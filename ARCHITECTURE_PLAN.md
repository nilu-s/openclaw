# OpenClaw - Runtime and Architecture Plan
Version: 3.1
Date: 2026-05-02
Status: Active

---

## 0. Source of Truth

Dieses Dokument ist die einzige operative Source of Truth fuer den aktuellen OpenClaw-Live-Runtime-Zustand auf `root@100.102.209.68`.

Nicht als aktuelle Runtime-Quelle verwenden:
- alte Zwischenstandsdateien
- alte Zwischenstandsregister
- alte Backup- oder `*.bak`-Dateien
- alte Agent-Core-Dateien aus `agentDir`-Archiven

Fachliche Prozesse sind ausgelagert:
- Gesamtuebersicht: [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)
- Software Domain: [SOFTWARE_DEVELOPMENT_SYSTEM.md](SOFTWARE_DEVELOPMENT_SYSTEM.md)
- Trading Domain: [TRADING_SYSTEM.md](TRADING_SYSTEM.md)
- SW-Requirements-Artefakte: Requirements-Katalog und Requirements-State (verwaltet ueber `nexusctl`)
- Governance/Rollen sind in den Domain-Dokumenten integriert.

---

## 1. Deployment Environment

- Server: `ssh root@100.102.209.68`
- Host root: `/opt/openclaw`
- Runtime state: `/opt/openclaw/state`
- Workspace host path: `/opt/openclaw/workspace`
- Workspace container path: `/workspace`
- Agent root (container): `/home/node/.openclaw/agents`
- Agent root (host bind): `/opt/openclaw/state/agents`

---

## 2. Runtime Topologie

Container-Services:
- `openclaw-gateway`
- `nexusctl-server`
- `ollama`

Aktueller Service-Status:
- `openclaw-gateway`: healthy
- `nexusctl-server`: healthy
- `ollama`: running
- Gateway health endpoint: `http://127.0.0.1:18789/healthz` liefert `{"ok":true,"status":"live"}`

Build-Modell:
- lokales Image `openclaw-with-gh:latest`
- Basisimage `ghcr.io/openclaw/openclaw:latest`
- `nexusctl` ist via `pip install` ins Image gebacken (nicht via Workspace oder externe Mounts)
- Aktueller Live-Stand: `nexusctl` ist in den laufenden Containern per `pip install` aus `/opt/openclaw/nexusctl-pkg` installiert. Bei zukuenftigen Image-Rebuilds muss dieser Source verwendet und danach live validiert werden.

Wichtige Volumes (openclaw-gateway):
- `/opt/openclaw/state -> /home/node/.openclaw`
- `/opt/openclaw/workspace -> /workspace`
- `/opt/openclaw/data/clawmem -> /home/node/.openclaw/memory`
- `/opt/openclaw/data/ssh -> /home/node/.ssh` (read-only)

Wichtige Volumes (nexusctl-server):
- `/opt/openclaw/state -> /home/node/.openclaw`

---

## 3. Verzeichnisstruktur (Host)

```text
/opt/openclaw/
|- .env
|- docker-compose.yml
|- Dockerfile
|- openclaw.config.json
|- state/
|  |- openclaw.json
|  |- agents/
|  |- cron/
|  |- skills/
|  '- ...
'- workspace/
   |- agents/
   |- docs/
   '- software/repos/trading-system/
```

---

## 4. Harte Pfad-Trennung

`agentDir`:
- `/home/node/.openclaw/agents/<agent-id>/agent`
- Zweck: Auth-Profile, Model-Registry, `nexusctl` Session-Cache und agentenspezifische Runtime-Metadaten
- Enthalten darf es Runtime-Artefakte wie `auth-profiles.json`, `auth-state.json`, `models.json`, `.nexusctl`, `.openclaw`, `state` und `RUNTIME_STATE_NOTE.txt`.
- Es enthaelt keine kanonischen Agent-`*.md`-Dateien und keine Produkt-Repos.

`workspace`:
- `/workspace/agents/<agent-id>`
- Zweck: Agenten-Bootstrap, Rollen-Kontext und default cwd fuer Datei-Tools

Produkt-Repos:
- `/workspace/software/repos/<repo-name>`
- Zweck: Projektcode, Branches, Tests, PR-relevante Aenderungen

Regel:
- Keine Produktcode-Arbeit in `agentDir`.
- Keine Agenten-Core-Governance im Produktcode-Repo.
- Agenten-Governance-Dokumente liegen lesbar unter `/workspace/docs`.
- Agenten-Core-Dateien liegen genau einmal unter `/workspace/agents/<agent-id>`.

### Agent Workspace Alignment

- `agentDir` stores per-agent OpenClaw state: auth profiles, model registry, nexusctl session cache, and runtime metadata.
- `workspace` stores per-agent OpenClaw bootstrap/context files and is the default cwd for file tools.
- Product repositories are not `agentDir` and are not the agent bootstrap workspace. They are referenced through explicit absolute paths in cron prompts and workspace policy files.
- For this deployment, product repo root is `/workspace/software/repos/trading-system`.
- Current OpenClaw runtime rejects `repoRoot` inside `agents.list`; do not add that key unless the runtime schema is upgraded.
- Cron prompts must use explicit `NEXUSCTL_AGENT_ID`, `NEXUSCTL_AGENT_DIR`, and absolute repo paths.

---

## 5. Agent-Roster

Zentral:
- `main`
- `nexus`

Software:
- `sw-architect`
- `sw-techlead`
- `sw-builder`
- `sw-reviewer`

Trading:
- `trading-strategist`
- `trading-analyst`
- `trading-sentinel`

---

## 6. Core-File Vertrag (Runtime)

Pflichtdateien pro Agent unter `/workspace/agents/<agent-id>/`:
- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `HEARTBEAT.md`
- `BOOTSTRAP.md`
- `MEMORY.md`
- `WORKSPACE.md`

`agentDir` darf diese Dateien nicht enthalten oder spiegeln.

---

## 7. Betriebsregeln

- Persistenter Work-State bleibt in GitHub-Artefakten.
- Ticket-/Issue-Koordination fuer Handoffs liegt in der `nexus`-Agent-Lane; `nexusctl` speichert Handoff- und Linkage-State, erstellt aber keine Tickets automatisch.
- Health-Check des Gateways muss aktiv sein.
- Cron-/Session-Logs duerfen fuer Neustarts bereinigt werden, ohne Core-Governance zu veraendern.
- Capability-Status darf nicht aus Memory allein abgeleitet werden.
- `nexusctl` Session-State wird im Agent-Kontext (`agentDir`) gehalten, nicht im Projekt-Workspace.
- Dadurch ist `nexusctl` Session-Nutzung terminalunabhaengig fuer denselben Agenten im selben Projekt.
- Session-Scope fuer `nexusctl`: `agent_id + project_id`, mit TTL gemaess CLI-Spezifikation.
- In Multi-Agent-Runtimes muessen manuelle und automatisierte `nexusctl`-Aufrufe den Scope explizit setzen (`NEXUSCTL_AGENT_DIR` oder `NEXUSCTL_AGENT_ID`), um mehrdeutige Session-Aufloesung zu vermeiden.

### Cron Workflow Contract

- Cron prompts are thin triggers. Durable runtime rules, paths, authority boundaries, and tool contracts belong in `/workspace/agents/<agent-id>/*.md`.
- Cron payloads should reference the agent workspace contract instead of duplicating long path/env/role text.
- Cronjobs duerfen keine historischen Lifecycle-Dateien als harte Validierungsquelle verlangen.
- Lifecycle-Quelle ist die installierte `nexusctl` CLI zusammen mit `nexusctl context --output json`.
- Cronjobs mit `delivery.mode = none` duerfen keinen `delivery.channel` setzen.
- Rollen ohne Mutationsrecht melden den benoetigten naechsten Schritt an `nexus`, statt Lifecycle-Zustaende direkt zu aendern.
- `sw-builder` darf PRs vorbereiten, muss aber die Transition zu `in-review` an `nexus` uebergeben, solange `nexusctl context` nur Leserechte ausweist.
- `sw-reviewer` darf bei GitHub-Eigenreview-Blockern eine PR-Kommentar-Review schreiben und muss die formale Lifecycle-Transition an `nexus` uebergeben.
- Trading-Jobs nutzen `GOALS.md` als autoritative Zielquelle; `TRADING_STATE.md` ist kein Ambient-Memory-Input fuer diese Rollen.

### Gateway Operating Mode

- Aktueller stabiler Live-Modus: `openclaw-gateway` laeuft mit `NODE_ENV=test` und `OPENCLAW_TEST_MINIMAL_GATEWAY=1`.
- Wirkung: HTTP, WebSocket, Control UI, Cron-RPC und `nexusctl`-Kontext funktionieren; der Gateway meldet `http server listening (0 plugins, ...)`.
- Aktuelle Grenze: OpenClaw Plugins, inklusive Browser-Plugin, werden in diesem Modus nicht geladen.
- Betriebsgrund: Der normale Full-Plugin-Bootstrap haengt auf diesem Host vor dem HTTP-Listen im pre-listen Plugin/Startup-Bootstrap. Der Minimalmodus ist der aktuelle stabile Betriebszustand.
- Recreate-Hinweis: `nexusctl-server` muss im normalen `NODE_ENV=production` bleiben; der Minimalmodus gilt nur fuer `openclaw-gateway`.
- Cron-Hotfix aktiv seit 2026-05-02:
  - Compose mountet `/opt/openclaw/scripts/cron-gateway-hotfix.js` nach `/opt/openclaw-hotfix/cron-gateway-hotfix.js`.
  - Gateway-Entrypoint fuehrt den Hotfix vor `docker-entrypoint.sh openclaw gateway --allow-unconfigured` aus.
  - `OPENCLAW_CRON_PROVIDER_PLUGIN_IDS=ollama` begrenzt Runtime-Provider-Plugin-Loading fuer den Gateway.
  - `OPENCLAW_CRON_SKIP_PROVIDER_CATALOG_AUGMENT=1` ueberspringt Provider-Katalog-Augmentierung.
  - Cron-Timeout startet vor Agent-Pre-Execution-Arbeit, nicht erst nach `onExecutionStarted`.

---

### Current Nexus Permissions

Live `nexusctl context --output json` mit explizitem `NEXUSCTL_AGENT_ID` und `NEXUSCTL_AGENT_DIR`:

| Rolle | Mutationsrechte |
|---|---|
| `nexus` | `request.transition`, `request.set-issue` |
| `sw-techlead` | `capabilities.set-status` |
| `trading-strategist` | `request.create` |
| `main` | read-only context/request/capability |
| `sw-architect` | read-only context/request/capability |
| `sw-builder` | read-only context/request/capability |
| `sw-reviewer` | read-only context/request/capability |
| `trading-sentinel` | read-only context/request/capability |
| `trading-analyst` | read-only context/request/capability |

### Current Cron State

- Configured jobs: 8
- Current execution status: built-in OpenClaw `agentTurn` cron jobs are ENABLED in live `jobs.json` as of 2026-05-02 06:01 UTC.
- Root cause fixed operationally: 2026-05-02 canary tests reproduced gateway blocking during pre-execution model catalog / provider plugin loading. The deployed hotfix bounds this path to Ollama, skips provider catalog augmentation, disables runtime dependency installation in the Gateway plugin path, and starts the cron timeout before pre-execution work.
- Validation after hotfix:
  - 300s diagnostic canary on production completed `ok` in 21604ms via `ollama/kimi-k2.6:cloud`.
  - Real `Trading Sentinel Capability Watch` run completed `ok` in 122638ms via `ollama/kimi-k2.6:cloud`.
  - `/healthz` stayed responsive during the long production checks.
- Runtime schema note: `wakeMode: "skip"` and `sessionTarget: "shared"` are invalid for the deployed runtime. Valid wake modes are `now` and `next-heartbeat`; valid session targets include `main`, `isolated`, `current`, and `session:<id>`.
- Default model: all cron payloads use `"model": "ollama/kimi-k2.6:cloud"` to route traffic through the Kimi-K cloud via the Ollama docker.
- Thinking level: all cron payloads use `thinking=off`, because the deployed Ollama/Kimi path downgrades unsupported thinking levels anyway.
- Full gateway mode was tested on a copied state directory on 2026-05-02 and hung before the HTTP listener became healthy; it is not a safe quick fix for cron execution.
- Active cadence and timeout policy:
  - `trading-sentinel`: every 1h, timeout 300s
  - `nexus`: every 1h, timeout 420s
  - `sw-architect`: every 2h, timeout 420s
  - `trading-strategist`: every 4h, timeout 420s
  - `sw-techlead`: every 4h, timeout 420s
  - `sw-reviewer`: every 4h, timeout 420s
  - `sw-builder`: every 6h, timeout 600s
  - `main-system-optimizer-v1`: every 6h, timeout 600s
- Agent workspace contracts define explicit `NEXUSCTL_AGENT_ID`, `NEXUSCTL_AGENT_DIR`, and `/workspace/software/repos/trading-system`.
- Cron payloads reference those workspace contracts instead of duplicating the full runtime contract.
- Cron payloads do not use `NEXUSCTL_FUNCTIONS.md` as a lifecycle gate.
- Cron jobs with `delivery.mode = none` do not set `delivery.channel`.
- `main-system-optimizer-v1` is configured with `agentId=main` and `thinking=off`; it audits agent/cron behavior and may make at most one bounded orchestration improvement per run.
- `main` treats orchestration changes as eval-style experiments. It records each hypothesis/action/expected signal in `/home/node/.openclaw/main-optimizer/experiments.jsonl` and should close any open experiment before starting another.

### Current Cleanup State

- No agent-core `*.md` files exist under `/opt/openclaw/state/agents/*/agent`.
- Canonical agent-core files exist only under `/opt/openclaw/workspace/agents/<agent-id>`.
- `/opt/openclaw/state/workspace` has been removed.
- Duplicate `*-01` state dirs have been removed.
- Old `/opt/openclaw/state/agents/sw-builder/agent/repo` has been removed.
- Old root-level runtime Markdown docs have been moved to `/opt/openclaw/workspace/docs`.

---

## 8. Change Policy

Bei Architektur-/Runtime-Aenderungen:
- Datum und Version aktualisieren.
- Auswirkungen auf Pfade, Volumes, Agentenlaufzeit und Betrieb explizit dokumentieren.
