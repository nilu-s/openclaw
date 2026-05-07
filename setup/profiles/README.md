# Profiles

These files are human-readable policy snippets. They are not loaded by OpenClaw automatically. The active schema-valid configuration is `config/openclaw.json`.

The optimized config uses:

- global `tools.profile: "coding"` so agents can use filesystem/runtime/web/session/memory tools and call `nexusctl` through `exec`
- `agents.list[].tools.alsoAllow` only where needed for orchestration or gateway maintenance
- per-agent skill allowlists so shared skills replace duplicated prompt text
