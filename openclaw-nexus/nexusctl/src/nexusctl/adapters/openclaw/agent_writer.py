"""Generated OpenClaw agent markdown writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .config_writer import DriftResult, ManagedArtifactWriter, WriteResult

AGENT_FILE_NAMES = (
    "AGENTS.md",
    "SOUL.md",
    "TOOLS.md",
    "IDENTITY.md",
    "USER.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "MEMORY.md",
)


class OpenClawAgentWriter:
    """Render the OpenClaw generation OpenClaw markdown set for each agent."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.writer = ManagedArtifactWriter(project_root)

    def write_agents(
        self,
        *,
        agents: Iterable[Mapping[str, Any]],
        standing_orders: Mapping[str, Any],
        skill_descriptions: Mapping[str, str],
    ) -> list[WriteResult]:
        results: list[WriteResult] = []
        for agent in sorted(agents, key=lambda item: str(item.get("id", ""))):
            agent_id = str(agent["id"])
            for filename, body in self.render_agent_files(
                agent=agent,
                standing_orders=standing_orders,
                skill_descriptions=skill_descriptions,
            ).items():
                results.append(self.writer.write_markdown(f"generated/agents/{agent_id}/{filename}", body))
        return results

    def render_agent_files(
        self,
        *,
        agent: Mapping[str, Any],
        standing_orders: Mapping[str, Any],
        skill_descriptions: Mapping[str, str],
    ) -> dict[str, str]:
        agent_id = str(agent["id"])
        display = str(agent.get("display_name") or agent_id)
        domain = str(agent.get("domain") or "unknown")
        role = str(agent.get("role") or "unknown")
        description = str(agent.get("description") or "")
        capabilities = sorted(str(item) for item in (agent.get("capabilities") or []))
        skills = sorted(str(item) for item in (agent.get("skills") or []))
        agent_orders = list((standing_orders.get("agents") or {}).get(agent_id, []))
        global_orders = list(standing_orders.get("global") or [])
        schedule_orders = [
            f"`{key}` — {value}"
            for key, value in sorted((standing_orders.get("schedules") or {}).items())
            if key.startswith(f"{domain}.")
        ]

        skill_lines = [
            f"- `{skill}` — {skill_descriptions.get(skill, 'No description in nexus/capabilities.yml.')}"
            for skill in skills
        ] or ["- No skills allowlisted."]
        cap_lines = [f"- `{capability}`" for capability in capabilities] or ["- No capabilities granted."]
        global_lines = [f"- {order}" for order in global_orders] or ["- No global standing orders."]
        agent_order_lines = [f"- {order}" for order in agent_orders] or ["- No agent-specific standing orders."]
        schedule_order_lines = [f"- {order}" for order in schedule_orders] or ["- No scheduled standing orders for this domain."]

        return {
            "AGENTS.md": f"""# {display}

Agent ID: `{agent_id}`  
Domain: `{domain}`  
Role: `{role}`

{description}

## Runtime contract

- Nexusctl is source of truth for lifecycle state.
- OpenClaw receives this file as generated runtime context only.
- The authenticated token, not a manual flag, determines domain and capability scope.
""",
            "SOUL.md": f"""# Operating Principles

## Global Standing Orders

{chr(10).join(global_lines)}

## Agent Standing Orders

{chr(10).join(agent_order_lines)}

## Scheduled Standing Orders for `{domain}`

{chr(10).join(schedule_order_lines)}
""",
            "TOOLS.md": f"""# Tool Policy

## Allowlisted skills

{chr(10).join(skill_lines)}

## Granted Nexusctl capabilities

{chr(10).join(cap_lines)}

## Prohibitions

- Do not use direct GitHub write credentials.
- Do not directly apply repository changes.
- Do not edit files under `generated/*` manually.
""",
            "IDENTITY.md": f"""# Identity

- `agent_id`: `{agent_id}`
- `display_name`: `{display}`
- `domain`: `{domain}`
- `role`: `{role}`
- `normal_agent`: `{bool(agent.get('normal_agent', True))}`
- `domain_source`: `auth_token`
""",
            "USER.md": f"""# User Interface Contract

Represent the `{display}` runtime context. Explain policy denials clearly and route cross-domain work through Nexusctl Feature Requests.
""",
            "HEARTBEAT.md": f"""# Heartbeat

Report status by reading Nexusctl state. For mutating work, create or advance Nexusctl-owned records and rely on append-only events. Cron-triggered work must reference scheduled standing orders from `nexus/standing-orders.yml` instead of duplicating their text.
""",
            "BOOTSTRAP.md": f"""# Bootstrap

1. Authenticate with a Nexusctl token for `{agent_id}`.
2. Read identity with `nexusctl me --json`.
3. Use only allowlisted skills and granted capabilities.
4. Treat `nexus/*.yml` as design source-of-truth and `generated/*` as derived runtime output.
""",
            "MEMORY.md": f"""# Memory

Durable state belongs in Nexusctl storage and event records. Do not store lifecycle truth in this generated OpenClaw markdown file.
""",
        }

    def expected_paths(self, agents: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
        paths: list[str] = []
        for agent in sorted(agents, key=lambda item: str(item.get("id", ""))):
            agent_id = str(agent["id"])
            paths.extend(f"generated/agents/{agent_id}/{name}" for name in AGENT_FILE_NAMES)
        return tuple(paths)

    def check(self, agents: Iterable[Mapping[str, Any]]) -> list[DriftResult]:
        return [self.writer.check_markdown(path) for path in self.expected_paths(agents)]
