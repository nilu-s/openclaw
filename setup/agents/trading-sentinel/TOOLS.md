# TOOLS
- Prefer JSON for machine-readable state: `nexusctl context --output json`, `request show --output json`, `work show --output json`.
- Use Nexus commands for lifecycle state and evidence; use GitHub only through `nexusctl github ...` unless explicitly approved.
- Use filesystem/runtime tools only inside the active workspace and current role boundaries.
- Before config edits, use the OpenClaw config safety skill and keep a rollback path.
