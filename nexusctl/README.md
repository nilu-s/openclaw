# nexusctl (Python MVP, Real DB)

CLI + Backend fuer Capability-Preflight und Capability-Status im OpenClaw-MVP.

## Implementierter Scope

- `auth`
- `capabilities list`
- `capabilities show`
- `capabilities set-status` (lokal bereits auf `sw-techlead` + `--to available` begrenzt)
- `handoff submit` (nur `trading-strategist`, persistiert Handoff im Backend)
- `handoff list` (Queue-Read fuer orchestrierende Rollen wie `nexus`)
- `handoff set-issue` (nur `nexus`, schreibt Issue-Linkage zurueck in Nexus)
- `nexusctl-server` (echter HTTP-Service mit SQLite-Persistenz)
- Session-Store mit TTL-Check
- Exit-Code- und Fehlercode-Mapping gemaess `NEXUSCTL_FUNCTIONS.md`

## Installation

```bash
pip install -e .
```

Danach steht `nexusctl` als Kommando zur Verfuegung.

## Backend starten (echte DB)

```bash
nexusctl-server --db-path .nexusctl/nexusctl.sqlite3 --seed
```

Der Schalter `--seed` legt initiale MVP-Daten an (nur wenn die DB leer ist).

## Schnellstart

```bash
nexusctl auth --agent-token "$NEXUS_AGENT_TOKEN" --output table
nexusctl capabilities list --status all --output table
nexusctl capabilities show F-001 --output json
nexusctl capabilities set-status F-002 --to available --reason "All requirements verified and evidence linked." --output json
nexusctl handoff submit --objective "Reduce reaction latency for risk-limit breaches." --missing-capability "Automatic hard-stop trigger when risk threshold is exceeded." --business-impact "Prevents prolonged exposure during volatility spikes." --expected-behavior "System halts new entries within breach window." --acceptance-criteria "Given threshold breach, new entries are blocked within 500ms." --risk-class high --priority P1 --trading-goals-ref "trading-goal://risk/limit-hard-stop" --output json
nexusctl handoff list --status submitted --limit 20 --output json
nexusctl handoff set-issue HC-2026-0001 --issue-ref "issue://github/owner/repo#42" --issue-number 42 --issue-url "https://github.com/owner/repo/issues/42" --output json
```

## Konfiguration (Env)

- `NEXUSCTL_API_BASE_URL` (default: `http://127.0.0.1:8080`)
- `NEXUS_AGENT_TOKEN` (Fallback fuer `auth`, wenn `--agent-token` fehlt)
- `NEXUSCTL_AGENT_DIR` (empfohlen; Agent-Kontextpfad)
- `NEXUSCTL_AGENT_ID` oder `OPENCLAW_AGENT_ID` (nur relevant ohne `NEXUSCTL_AGENT_DIR`)
- `NEXUSCTL_SESSION_BASE` (default: `~/.openclaw/agents`, nur ohne `NEXUSCTL_AGENT_DIR`)

Hinweis: Domain-Overrides sind absichtlich gesperrt (`auth --domain`, `capabilities list --domain`).

## Session-Speicher

Wenn `NEXUSCTL_AGENT_DIR` gesetzt ist:

- `<NEXUSCTL_AGENT_DIR>/.nexusctl/sessions/<project-id>.json`
- `<NEXUSCTL_AGENT_DIR>/.nexusctl/sessions/current.json`

## Exit-Codes

- `0` Erfolg
- `2` Validation Error
- `3` Not Found
- `4` Permission Denied
- `6` Precondition Failed
- `10` Infrastructure Error

## Tests

```bash
pytest
```

Enthalten sind:

- Unit-Tests fuer Validierung, Rollen- und Exit-Code-Verhalten
- Integrations-/AC-Tests fuer AC-001 bis AC-009 gegen echten `nexusctl-server` mit echter SQLite-DB
- Integrations-/AC-Tests fuer AC-001 bis AC-011 gegen echten `nexusctl-server` mit echter SQLite-DB
