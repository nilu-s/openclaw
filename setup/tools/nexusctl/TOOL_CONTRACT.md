# Nexusctl Tool Contract

Current active implementation: call `nexusctl` via OpenClaw runtime/exec tools.

Future custom plugin shape, if you decide to implement one:

- `nexus.context()` -> wraps `nexusctl context --output json`
- `nexus.request.list(status, limit)`
- `nexus.request.show(request_id)`
- `nexus.request.transition(request_id, to, reason)`
- `nexus.work.show(request_id)`
- `nexus.work.transition(request_id, to, reason, override=false)`
- `nexus.github.sync(request_id)`
- `nexus.reviews.submit(request_id, verdict, summary)`

Plugin should enforce:

- JSON output only
- no shell interpolation
- strict enum validation for status, risk, priority, and verdict
- scoped Nexus session identity from `OPENCLAW_AGENT_ID`
- no direct GitHub credential exposure to worker agents
