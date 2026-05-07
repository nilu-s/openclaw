# OpenClaw + Nexusctl Greenfield

This repository is a clean Greenfield rebuild of the OpenClaw/Nexusctl system.

## Architectural principles

- Nexusctl is the source of truth for domains, goals, metrics, feature requests, scopes, work, reviews, GitHub sync, schedules, and events.
- OpenClaw is runtime only: agents, workspaces, skills, cronjobs, gateway, and sessions are generated from Nexus definitions.
- GitHub is a projection and collaboration surface, never lifecycle authority.
- Agent domain, role, and capabilities are derived from authenticated identity, not from manually supplied domain flags.
- Agent markdown and skill files under `generated/*` are generated artifacts and must not be treated as hand-maintained truth.
- Agents never get direct GitHub write tokens.
- Builders never apply directly to the canonical repository; they submit scoped patch proposals.
- Cross-domain needs flow through Nexusctl Feature Requests; a request never grants the source domain target-domain implementation scope.

## Current phase

Phase 14 is complete. Nexusctl now generates OpenClaw runtime artifacts from `nexus/*.yml`: `generated/openclaw/openclaw.json`, per-agent markdown files, skill definitions, per-agent skill allowlists, and per-agent tool-policy JSON. Generated artifacts carry checksums and `nexusctl doctor --json` detects manual drift. Phase 13 webhook reconciliation and Phase 12 merge/apply gates remain active through the dedicated `nexus-applier` control agent:

- `nexusctl merge <feature_request_or_patch_or_pr_id> --json` resolves the merge target and applies it only after all Nexus policy gates are green;
- only `nexus-applier` has `repo.apply`, while builders and reviewers remain unable to merge or directly mutate the canonical repository;
- the merge gate requires scope compliance, current PR head SHA, green persisted policy checks, mirrored GitHub Check Runs, approved software review, required source-domain acceptance, no safety veto, and no open critical GitHub alerts;
- approved merges are projected through the mockable GitHub PR merge adapter, stored in `merge_records`, and reflected back onto work, patch, Feature Request, event, and label state;
- issue and PR acceptance/review/merge labels are persisted in `github_projection_labels`; PR-review mappings are stored in `github_pr_review_links`.

Initialize a database:

```bash
python -m nexusctl.interfaces.cli.main db init --db nexus.db --project-root . --json
```

Create local-test tokens:

```bash
TRADING_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent trading-strategist --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')

NEXUS_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent nexus --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')

ARCHITECT_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent software-architect --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')

TECHLEAD_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent software-techlead --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')

REVIEWER_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent software-reviewer --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')

SENTINEL_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent trading-sentinel --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')

APPLIER_TOKEN=$(python -m nexusctl.interfaces.cli.main auth login --agent nexus-applier --db nexus.db --project-root . --json \
  | python -c 'import json,sys; print(json.load(sys.stdin)["credential"]["token"])')
```

Create, route, project, plan, assign, and lease one software request:

```bash
FR_ID=$(NEXUSCTL_TOKEN="$TRADING_TOKEN" python -m nexusctl.interfaces.cli.main feature-request create \
  --target software \
  --goal trade_success_quality \
  --title "Need portfolio risk dashboard export" \
  --db nexus.db \
  --project-root . \
  --json | python -c 'import json,sys; print(json.load(sys.stdin)["feature_request"]["id"])')

NEXUSCTL_TOKEN="$NEXUS_TOKEN" python -m nexusctl.interfaces.cli.main feature-request route "$FR_ID" \
  --target software --db nexus.db --project-root . --json

NEXUSCTL_TOKEN="$NEXUS_TOKEN" python -m nexusctl.interfaces.cli.main github issue sync "$FR_ID" \
  --db nexus.db --project-root . --json

WORK_ID=$(NEXUSCTL_TOKEN="$ARCHITECT_TOKEN" python -m nexusctl.interfaces.cli.main work plan "$FR_ID" \
  --db nexus.db --project-root . --json | python -c 'import json,sys; print(json.load(sys.stdin)["work"]["id"])')

NEXUSCTL_TOKEN="$TECHLEAD_TOKEN" python -m nexusctl.interfaces.cli.main work assign "$FR_ID" \
  --builder software-builder \
  --reviewer software-reviewer \
  --db nexus.db \
  --project-root . \
  --json

NEXUSCTL_TOKEN="$NEXUS_TOKEN" python -m nexusctl.interfaces.cli.main scopes lease \
  --agent software-builder \
  --request "$FR_ID" \
  --paths 'nexusctl/src/**' \
  --ttl 2h \
  --db nexus.db \
  --project-root . \
  --json
```

Goal/evidence, Feature Request, and GitHub projection commands from earlier phases remain available:

```bash
NEXUSCTL_TOKEN="$TRADING_TOKEN" python -m nexusctl.interfaces.cli.main goals status --db nexus.db --project-root . --json
NEXUSCTL_TOKEN="$TRADING_TOKEN" python -m nexusctl.interfaces.cli.main feature-request list --db nexus.db --project-root . --json
NEXUSCTL_TOKEN="$NEXUS_TOKEN" python -m nexusctl.interfaces.cli.main github app status --db nexus.db --project-root . --json
```

Validate the project with:

```bash
python scripts/validate_project.py
```

Run tests with:

```bash
PYTHONPATH=nexusctl/src pytest -q
```

Create a distributable package with the same base name as the project directory:

```bash
python scripts/package_project.py
```

The previous setup is preserved unpacked under `referenzen/setup/` for non-runtime reference only. It is not imported, executed, or treated as source of truth.

## Phase 9: Patch Proposal, Worktree, Branch/PR Projection

Phase 9 adds scoped implementation flow without giving agents direct repository
or GitHub write access. The assigned `software-builder` can start a work item,
submit a patch proposal from a local worktree, and Nexusctl validates every
changed repository-relative path against the active scope lease before the patch
is stored.

Core commands:

```bash
nexusctl work start <work_id> --json
nexusctl patch submit <work_or_request_id> --from-worktree <path> --json
nexusctl patch show <patch_id> --json
nexusctl github pr create <patch_id> --json
```

`github pr create` is available only through Nexusctl/GitHub-App authority. The
mock client records branch and pull-request projection metadata in
`github_pull_links`; no builder can create a PR, merge, or mutate the canonical
repository directly.

## Phase 10: Checks, CI-Sync, and Policy Gates

Phase 10 keeps GitHub as a projection while Nexusctl remains the gate authority.
`policy check` reads Nexusctl state and reports whether a patch is merge-ready;
`github checks sync` is reserved for Nexusctl and mirrors the gate results as
mockable GitHub Check Runs. Pending review or acceptance keeps the PR non-green,
and a later PR head-SHA change invalidates the previously validated patch state.

Core commands:

```bash
nexusctl policy check <patch_id> --json
nexusctl github checks sync <patch_id> --json
```

## Phase 11: Software Review and Trading Acceptance

Phase 11 turns the review and acceptance gates into first-class workflows.
Software reviewers can approve or block patch proposals, but they cannot provide
Trading acceptance. Trading strategists can accept or reject the business result,
but their acceptance cannot replace technical review. Trading sentinels can file
a safety veto, which blocks the `no_safety_veto` policy gate even when review and
acceptance are otherwise green.

Core commands:

```bash
nexusctl review queue --json
nexusctl review submit <patch_or_work_id> --verdict approved --json
nexusctl acceptance submit <feature_request_or_patch_id> --verdict accepted --json
nexusctl acceptance submit <feature_request_or_patch_id> --verdict vetoed --json
nexusctl acceptance status <feature_request_or_patch_id> --json
```

Nexusctl stores authoritative rows in `reviews` and `acceptances`, projects PR
review metadata through `github_pr_review_links`, and records issue/PR label
state in `github_projection_labels`.

## Phase 12: Merge/Apply Gate and GitHub Merge

Phase 12 adds the final apply path while preserving GitHub as a projection.
`nexus-applier` is the only agent authorized for `repo.apply`; the command still
re-evaluates policy state and refuses to merge unless Nexusctl has persisted
green policy checks, matching GitHub Check Runs, accepted source-domain
acceptance where required, approved software review, no safety veto, current PR
head SHA, and no open critical GitHub alerts.

Core command:

```bash
nexusctl merge <feature_request_or_patch_or_pr_id> --json
```

Successful merges are recorded in `merge_records`, mark the patch as `merged`,
close the Feature Request, mark the Work Item `done`, append merge events, and
update projected issue/PR labels to `status:merged`.

## Phase 13: GitHub Webhooks and Reconciliation

Phase 13 adds signed GitHub webhook ingress plus a Nexusctl reconciliation loop. Webhook deliveries are HMAC-SHA256 verified with `GITHUB_WEBHOOK_SECRET`, stored idempotently in `github_webhook_events`, and later processed by Nexusctl authority. Unknown GitHub changes create `github_alerts` instead of silently mutating Nexus state; issue and PR labels are reset to the Nexusctl projection in `github_projection_labels`. PR head-SHA drift is written back to `github_pull_states`, causing the existing policy gate to fail until the patch is revalidated. Unauthorized GitHub merges become critical alerts that continue to block the Phase 12 merge gate.

Core commands:

```bash
nexusctl github webhook verify --payload '{"zen":"ok"}' --signature sha256:<digest> --json
nexusctl github reconcile --json
```

HTTP webhook ingress is available as a framework-free route function at `nexusctl.interfaces.http.routes.handle_github_webhook` and a small stdlib server factory at `nexusctl.interfaces.http.server.make_server` for `/webhooks/github`.



## Phase 14: OpenClaw Generator

Phase 14 renders OpenClaw runtime files from Nexus design truth. `platform-maintainer` is the runtime-generation actor because it owns `runtime.generate`; builders and trading agents cannot generate runtime artifacts.

Core commands:

```bash
nexusctl generate openclaw --json
nexusctl generate agents --json
nexusctl generate skills --json
nexusctl generate all --json
nexusctl doctor --json
```

Generated files include checksum metadata. Manual edits under `generated/*` are reported by `doctor` and by `scripts/validate_project.py`.


## Phase 15: Schedules, Cronjobs und Standing Orders

Phase 15 renders OpenClaw cron descriptors from `nexus/schedules.yml` and keeps `nexus/standing-orders.yml` as the source of truth for the actual recurring instructions. Generated cron prompts reference a standing-order id instead of duplicating the standing-order text.

Core commands:

```bash
nexusctl schedules list --json
nexusctl schedules validate --json
nexusctl schedules render-openclaw --json
nexusctl schedules reconcile-openclaw --json
nexusctl schedules run <schedule> --dry-run --json
```

Guardrails: autonomous `software-builder` cronjobs are rejected, Trading schedules are limited to Trading-domain effects and Feature Request creation, and every schedule run is persisted in `schedule_runs` with an append-only event.

## Phase 16: Docker Compose Runtime

Phase 16 adds a containerized runtime boundary for Nexusctl and OpenClaw. The Compose stack defines `nexusctl-api`, `nexusctl-worker`, `nexusctl-cli`, and `openclaw-gateway` services with explicit healthchecks and volumes for persistent state, agent workspaces, and repository worktrees.

Core commands:

```bash
cd config
docker compose up --build nexusctl-api nexusctl-worker openclaw-gateway
docker compose run --rm nexusctl-cli doctor --json
```

Runtime layout:

- Nexusctl stores `nexus.db` in the persistent `nexus-data` volume at `/data/nexus.db`.
- OpenClaw receives generated runtime artifacts mounted read-only at `/generated`.
- Agent workspaces use the shared `workspaces` volume.
- Repository worktrees use the shared `repo-worktrees` volume and remain separate from agent workspaces.
- GitHub App settings are declared in `config/.env.example`; mock/test runs can leave credentials empty.


## Phase 17 — Runtime Tools und Guardrails

Phase 17 ergänzt eine Nexusctl-verwaltete Runtime-Tool-Registry in `nexus/runtime-tools.yml`. Die CLI stellt `nexusctl runtime-tools list --json`, `nexusctl runtime-tools show <id> --json` und `nexusctl runtime-tools check <id> --json` bereit. Toolchecks geben eine Guardrail-Entscheidung `allow`, `deny` oder `approval_required` aus.

Side-Effect-Level sind `read_only`, `simulation`, `paper_trade`, `live_trade` und `destructive`. Im MVP bleiben Trading-Tools auf Read/Simulation/Paper begrenzt; Live-Trading wird nicht automatisch erlaubt und destruktive Tools sind standardmäßig blockiert. Trading-Agenten können keine Software-Tools invoken.

## Phase 18 — HTTP API und Agent/API-Stabilisierung

Phase 18 ergänzt eine schlanke stdlib-basierte HTTP API neben der CLI. Die API verwendet dieselbe SQLite-Initialisierung, dieselbe Token Registry, dieselbe CapabilityMatrix, denselben PolicyEngine-Pfad und dieselben App-Services wie `nexusctl`. Dadurch bleibt die Businesslogik in den Services; CLI und HTTP bleiben reine Interfaces.

Verfügbare Kernrouten:

- `GET /healthz` — API-Healthcheck
- `GET /auth/me` — tokenbasierte Agent-Identität und Capabilities
- `GET /goals`, `GET /goals/{id}` — Goal-Lesen via `GoalService`
- `GET /feature-requests`, `POST /feature-requests`, `POST /feature-requests/{id}/route`, `POST /feature-requests/{id}/transition`
- `POST /work/plan`, `POST /work/assign`, `GET /work/{id}`
- `GET /reviews`, `POST /reviews`
- `GET /acceptance/{id}`, `POST /acceptance`
- `GET /schedules`, `GET /schedules/validate`, `POST /schedules/{id}/run`
- `POST /github/webhook` und `POST /webhooks/github` — isolierter GitHub-Webhook mit HMAC-Signaturprüfung

Authentifizierte Routen erwarten `Authorization: Bearer <token>`. Webhook-Routen sind tokenlos und werden ausschließlich über GitHub-HMAC verifiziert.
## Phase 19 — Legacy Importer

Phase 19 adds a one-shot `nexusctl legacy-import` converter for the referenced legacy setup in `referenzen/setup`. The converter creates review reports in `generated/imports/` and intentionally does not copy legacy code into the Nexusctl runtime.

```bash
PYTHONPATH=nexusctl/src python -m nexusctl.interfaces.cli.main legacy-import --project-root . --legacy-root referenzen/setup --output-dir generated/imports --json
```

Outputs:

- `generated/imports/legacy_import_report.json`
- `generated/imports/legacy_import_report.md`


## Phase 20 — End-to-End MVP Demo und finaler Paketstatus

Phase 20 schließt den Greenfield-MVP ab. Der lokale Demo-Flow läuft vollständig im Testmodus mit Fake-GitHub-Projektion und deckt die komplette Audit-Kette ab:

1. `trading-analyst` fügt Evidence für `trade_success_quality` hinzu, misst die Metriken und erkennt eine Zielverletzung.
2. `trading-strategist` erstellt daraus einen Software-FeatureRequest; `source_domain=trading` wird aus dem Token abgeleitet.
3. `nexus` projiziert den Request als GitHub-Issue und routet ihn an Software.
4. `software-architect` plant, `software-techlead` weist Builder/Reviewer zu, und `nexus` erteilt eine pfadgebundene Scope-Lease.
5. `software-builder` reicht ausschließlich ein Patch-Proposal ein; direkte Reviews, PRs oder Merges bleiben blockiert.
6. `nexus` erzeugt PR und Checks, `software-reviewer` genehmigt technisch, `trading-strategist` akzeptiert fachlich.
7. `nexus-applier` merged erst nach grünen Gates; alle Mutationen erscheinen als append-only Events.
8. `platform-maintainer` kann die OpenClaw-Artefakte erneut generieren; Paketierung bewahrt alle Dateien unter dem Root-Namen `openclaw-nexus`.

Ausführbar ist der finale Nachweis über:

```bash
./scripts/run_tests.sh
python scripts/package_project.py --output ../openclaw-nexus.zip
```

Der ZIP-Ausgabename bleibt bewusst identisch zum Eingabenamen `openclaw-nexus.zip`; der Inhalt liegt vollständig unter `openclaw-nexus/`.
