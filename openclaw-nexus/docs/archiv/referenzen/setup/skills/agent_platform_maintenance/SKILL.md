---
name: agent_platform_maintenance
description: Maintain and optimize OpenClaw agents, skills, cron jobs, prompts, and orchestration with safe, reversible patches.
---

# Agent Platform Maintenance

Use for prompt/skill/config/cron optimization and repeated failure analysis.

Workflow:

1. Observe evidence: session output, cron logs, Nexus state, GitHub adapter state, config, and agent files.
2. Classify the failure: stale assumption, duplicate process text, role confusion, missing tool, bad schedule, invalid lifecycle command, or config drift.
3. Prefer shared skill change over editing many agent files.
4. Make the smallest reversible patch.
5. Validate with syntax/config checks and a targeted dry-run when possible.
6. Record reason, expected effect, validation, and rollback path.

Do not change secrets, auth profiles, gateway exposure, Docker security, or live trading mode without explicit same-task instruction.
