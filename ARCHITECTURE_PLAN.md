# OpenClaw - Runtime and Architecture Plan
Version: 2.6
Date: 2026-04-26
Status: Active

---

## 0. Dokumentationsmodell

Dieses Dokument beschreibt nur Runtime, Deployment, Pfade und Betriebsarchitektur.

Fachliche Prozesse sind ausgelagert:
- Gesamtuebersicht: [SYSTEM_OVERVIEW.md](C:/projects/DebugMyself/openclaw/SYSTEM_OVERVIEW.md)
- Software Domain: [SOFTWARE_DEVELOPMENT_SYSTEM.md](C:/projects/DebugMyself/openclaw/SOFTWARE_DEVELOPMENT_SYSTEM.md)
- Trading Domain: [TRADING_SYSTEM.md](C:/projects/DebugMyself/openclaw/TRADING_SYSTEM.md)
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

Container-Service:
- `openclaw-gateway`

Build-Modell:
- lokales Image `openclaw-with-gh:latest`
- Basisimage `ghcr.io/openclaw/openclaw:latest`

Wichtige Volumes:
- `/opt/openclaw/state -> /home/node/.openclaw`
- `/opt/openclaw/workspace -> /workspace`
- `/opt/openclaw/data/clawmem -> /home/node/.openclaw/memory`
- `/opt/openclaw/data/ssh -> /home/node/.ssh` (read-only)

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
   '- software/repos/
      '- trading-system/
```

---

## 4. Harte Pfad-Trennung

`agentDir`:
- `/home/node/.openclaw/agents/<agent-id>/agent`
- Zweck: Identitaet, Guardrails, Core-Files, agentenspezifische Metadaten

`workspace`:
- `/workspace/...`
- Zweck: Projektcode, Repos, Branches, Tests, PR-relevante Aenderungen

Regel:
- Keine Produktcode-Arbeit in `agentDir`.
- Keine Agenten-Core-Governance im Projektcode-Workspace.

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

Pflichtdateien pro Agent unter `/home/node/.openclaw/agents/<agent-id>/agent/`:
- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `HEARTBEAT.md`
- `BOOTSTRAP.md`
- `MEMORY.md`

---

## 7. Betriebsregeln

- Persistenter Work-State bleibt in GitHub-Artefakten.
- Schreibende Agentenoperationen auf GitHub-Artefakten ueber `nexusctl` sind optionales Phase-2-Zielbild.
- Health-Check des Gateways muss aktiv sein.
- Cron-/Session-Logs duerfen fuer Neustarts bereinigt werden, ohne Core-Governance zu veraendern.
- Capability-Status darf nicht aus Memory allein abgeleitet werden.
- `nexusctl` Session-State wird im Agent-Kontext (`agentDir`) gehalten, nicht im Projekt-Workspace.
- Dadurch ist `nexusctl` Session-Nutzung terminalunabhaengig fuer denselben Agenten im selben Projekt.
- Session-Scope fuer `nexusctl`: `agent_id + project_id`, mit TTL gemaess CLI-Spezifikation.

---

## 8. Change Policy

Bei Architektur-/Runtime-Aenderungen:
- Datum und Version aktualisieren.
- Auswirkungen auf Pfade, Volumes, Agentenlaufzeit und Betrieb explizit dokumentieren.
