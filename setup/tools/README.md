# Tools

Active tool access is configured in `config/openclaw.json`. The `tools/nexusctl` directory defines the local tool contract and command map for Nexus v2; it is documentation and wrapper guidance, not an auto-loaded OpenClaw plugin.

Recommended current approach: use OpenClaw `exec` with the installed `nexusctl` CLI, guided by the shared Nexus skills. Build a custom plugin only if you want typed function calls instead of shell commands.
