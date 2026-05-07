---
name: openclaw_config_safety
description: Safely edit OpenClaw configuration with schema lookup, backups, atomic writes, and rollback instructions.
---

# OpenClaw Config Safety

OpenClaw config is schema validated. Unknown keys or wrong types can prevent the Gateway from starting.

Before edits:

```bash
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)
```

When the gateway tool is available, prefer schema lookup before patching:

- `config.schema.lookup` for the target subtree
- `config.get` to obtain current config and hash
- `config.patch` for partial changes
- Avoid full `config.apply` unless replacing the whole file intentionally

Never edit tokens, provider API keys, auth profiles, gateway public exposure, or trusted proxies unless explicitly asked.
