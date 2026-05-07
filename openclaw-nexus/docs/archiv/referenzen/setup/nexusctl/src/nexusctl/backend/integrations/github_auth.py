from __future__ import annotations

import os
from typing import Mapping

from nexusctl.backend.integrations.github_models import GitHubRepository
from nexusctl.errors import NexusError


class GitHubAuthProvider:
    def get_token(self, repo: GitHubRepository) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class EnvGitHubAuthProvider(GitHubAuthProvider):
    def __init__(self, env: Mapping[str, str] | None = None):
        self._env = env if env is not None else os.environ

    def get_token(self, repo: GitHubRepository) -> str:
        token = (self._env.get("NEXUS_GITHUB_TOKEN") or "").strip()
        if not token:
            raise NexusError("NX-GH-AUTH", "missing NEXUS_GITHUB_TOKEN")
        return token
