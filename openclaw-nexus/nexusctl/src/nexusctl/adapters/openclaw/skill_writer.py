"""Generated OpenClaw skill and tool-policy writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .config_writer import DriftResult, ManagedArtifactWriter, WriteResult


class OpenClawSkillWriter:
    """Render skills, per-agent allowlists, and per-agent tool policies."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.writer = ManagedArtifactWriter(project_root)

    def write_skills(
        self,
        *,
        agents: Iterable[Mapping[str, Any]],
        skills: Iterable[Mapping[str, Any]],
        capabilities_by_id: Mapping[str, Mapping[str, Any]],
    ) -> list[WriteResult]:
        agents_list = list(agents)
        skill_list = list(skills)
        results: list[WriteResult] = []
        for skill in sorted(skill_list, key=lambda item: str(item.get("id", ""))):
            skill_id = str(skill["id"])
            allowed_agents = sorted(
                str(agent["id"]) for agent in agents_list if skill_id in set(agent.get("skills") or [])
            )
            payload = {
                "schema_version": 1,
                "id": skill_id,
                "description": skill.get("description", ""),
                "source": "nexus/capabilities.yml",
                "allowed_agents": allowed_agents,
            }
            results.append(self.writer.write_json(f"generated/skills/{skill_id}.json", payload, artifact_kind="skill"))

        for agent in sorted(agents_list, key=lambda item: str(item.get("id", ""))):
            agent_id = str(agent["id"])
            allowlist_payload = {
                "schema_version": 1,
                "agent_id": agent_id,
                "domain": agent.get("domain"),
                "skills": sorted(agent.get("skills") or []),
                "source": "nexus/agents.yml",
            }
            results.append(
                self.writer.write_json(
                    f"generated/skills/allowlists/{agent_id}.json",
                    allowlist_payload,
                    artifact_kind="agent_skill_allowlist",
                )
            )

            capabilities = sorted(str(item) for item in (agent.get("capabilities") or []))
            policy_payload = {
                "schema_version": 1,
                "agent_id": agent_id,
                "domain": agent.get("domain"),
                "role": agent.get("role"),
                "capabilities": capabilities,
                "mutating_capabilities": [
                    capability for capability in capabilities if bool((capabilities_by_id.get(capability) or {}).get("mutating"))
                ],
                "read_only_capabilities": [
                    capability for capability in capabilities if not bool((capabilities_by_id.get(capability) or {}).get("mutating"))
                ],
                "github_direct_write": bool((agent.get("github") or {}).get("direct_write", True)),
                "repo_direct_apply": bool((agent.get("repo") or {}).get("direct_apply", True)),
                "domain_source": "auth_token",
                "source": "nexus/agents.yml + nexus/capabilities.yml",
            }
            results.append(
                self.writer.write_json(
                    f"generated/skills/tool-policies/{agent_id}.json",
                    policy_payload,
                    artifact_kind="agent_tool_policy",
                )
            )
        return results

    def expected_paths(
        self,
        *,
        agents: Iterable[Mapping[str, Any]],
        skills: Iterable[Mapping[str, Any]],
    ) -> tuple[str, ...]:
        paths: list[str] = []
        for skill in sorted(skills, key=lambda item: str(item.get("id", ""))):
            paths.append(f"generated/skills/{skill['id']}.json")
        for agent in sorted(agents, key=lambda item: str(item.get("id", ""))):
            paths.append(f"generated/skills/allowlists/{agent['id']}.json")
            paths.append(f"generated/skills/tool-policies/{agent['id']}.json")
        return tuple(paths)

    def check(self, *, agents: Iterable[Mapping[str, Any]], skills: Iterable[Mapping[str, Any]]) -> list[DriftResult]:
        return [self.writer.check_json(path) for path in self.expected_paths(agents=agents, skills=skills)]
