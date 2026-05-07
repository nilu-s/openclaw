---
name: implementation_safety
description: Keep implementation changes scoped, testable, reversible, and aligned with approved Nexus context.
---

# Implementation Safety

- Read `nexusctl work show <request_id> --output json` before editing.
- Respect `implementation_context.do_not_touch` exactly.
- Prefer minimal patches over broad rewrites.
- Do not change secrets, auth, live trading behavior, Docker security, or gateway exposure.
- Run the specified tests; if unavailable, record the exact command and failure.
- Submit evidence with test command, result, changed files, and PR/link reference.
- Escalate scope changes instead of silently expanding implementation.
