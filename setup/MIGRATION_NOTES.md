# Migration Notes

## What changed

- Agent files were reduced to role, authority, done criteria, and concise tool notes.
- Reusable process instructions moved into shared skills under `skills/`.
- `openclaw.json` no longer restricts all agents to only `agents_list`.
- Per-agent skill allowlists are explicit.
- Nexus v2 terminology is canonical: `goal_ref` / `--goal-ref`, `request`, `work`, `reviews`, and `nexusctl github ...`.
- Legacy GitHub-label lifecycle authority and legacy issue-linking commands were removed from agent/skill prompts.
- Runtime artifacts were removed from the packaged Nexusctl tree: logs, sqlite smoke DB, pytest cache, pycache, egg-info.

## Recommended validation

```bash
python3 scripts/validate_optimized_setup.py .
python -m json.tool config/openclaw.json >/dev/null
openclaw config schema >/tmp/openclaw-schema.json  # if available
openclaw doctor                              # if available
```

## Safe rollout

1. Unzip into a temporary directory.
2. Compare `config/openclaw.json` against your current production config.
3. Run the validation script.
4. Install with `scripts/install_optimized.sh` or manually copy files.
5. Restart the OpenClaw gateway.
6. Run each agent once with a harmless context check.




## Agent name update

Replaced the previous alias/persona layer with simple display names:

- `profiles/agent-name-roster.md` lists all display names, roles, and voices.
- `skills/agent_persona_contract/` was removed; personality rules now live only in each agent's `IDENTITY.md` and `SOUL.md`.
- Each `agents/*/AGENTS.md` references the display name without aliases.
- `config/openclaw.json` keeps canonical `id` values unchanged but updates display `name`, `identity.name`, `systemPromptOverride`, and skill allowlists.

Important: route by canonical ids such as `sw-builder`; use names such as `Gendry` for readability only.
