---
name: openclaw_orchestration
description: Route user requests across Main, Nexus, software, trading, and platform optimizer agents without taking over specialist authority.
---

# OpenClaw Orchestration

Routing map:

- Lifecycle, handoff gate, GitHub/Nexus mismatch: `nexus`
- Architecture planning and implementation context: `sw-architect`
- Engineering governance and capability release: `sw-techlead`
- Code implementation: `sw-builder`
- Independent software review: `sw-reviewer`
- Strategy/adoption/capability-gap decisions: `trading-strategist`
- Research evidence: `trading-analyst`
- Monitoring/risk alerts: `trading-sentinel`
- Prompt/config/cron/orchestration optimization: `platform-optimizer`

Main should produce one of: answer, route, approval request, or escalation.
