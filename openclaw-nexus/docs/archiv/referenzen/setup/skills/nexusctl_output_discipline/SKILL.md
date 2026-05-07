---
name: nexusctl_output_discipline
description: Keep Nexus/OpenClaw outputs concise, machine-verifiable, and useful for the next owner.
---

# Output Discipline

For lifecycle actions, output:

- item id
- old status and new status, or no-op reason
- command used or evidence source
- next owner
- next action
- blocker and exact error code if blocked

Prefer compact JSON-derived summaries over long prose. Do not paste large raw JSON unless requested.
