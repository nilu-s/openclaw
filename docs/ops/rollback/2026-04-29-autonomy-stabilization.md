# Rollback Runbook: Autonomy Stabilization (2026-04-29)

## Scope
Restore the pre-change versions of:
- `/opt/openclaw/openclaw.config.json`
- `/opt/openclaw/state/cron/jobs.json`
- `/opt/openclaw/state/cron/jobs-state.json`
- `/opt/openclaw/.env`

Backups used:
- `/opt/openclaw/backups/openclaw.config.json.bak-2026-04-29`
- `/opt/openclaw/backups/jobs.json.bak-2026-04-29`
- `/opt/openclaw/backups/jobs-state.json.bak-2026-04-29`
- `/opt/openclaw/backups/.env.bak-2026-04-29`

## Preconditions
- SSH access to `root@100.102.209.68`
- `/opt/openclaw/backups/*-2026-04-29` files exist

## Restore Commands (exact)
Run from local workstation:

```bash
ssh root@100.102.209.68 "set -e; \
cp -a /opt/openclaw/backups/openclaw.config.json.bak-2026-04-29 /opt/openclaw/openclaw.config.json; \
cp -a /opt/openclaw/backups/jobs.json.bak-2026-04-29 /opt/openclaw/state/cron/jobs.json; \
cp -a /opt/openclaw/backups/jobs-state.json.bak-2026-04-29 /opt/openclaw/state/cron/jobs-state.json; \
cp -a /opt/openclaw/backups/.env.bak-2026-04-29 /opt/openclaw/.env"
```

## Post-restore Verification (exact)

```bash
ssh root@100.102.209.68 "set -e; ls -l \
/opt/openclaw/openclaw.config.json \
/opt/openclaw/state/cron/jobs.json \
/opt/openclaw/state/cron/jobs-state.json \
/opt/openclaw/.env"
```