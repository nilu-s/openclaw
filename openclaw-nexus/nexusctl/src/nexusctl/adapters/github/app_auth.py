"""GitHub App authentication configuration for Nexusctl projections.

GitHub projection workflow deliberately keeps GitHub credentials inside the Nexusctl/GitHub-App
boundary. Agents authenticate to Nexusctl with agent tokens; they never receive
GitHub write tokens. Local development and tests use mock mode when app
credentials are absent.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class GitHubAppConfig:
    """Configuration required to authenticate a GitHub App installation."""

    mode: str = "mock"
    app_id: str | None = None
    installation_id: str | None = None
    private_key_path: str | None = None
    webhook_secret_set: bool = False
    api_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "GitHubAppConfig":
        env = environ or os.environ
        explicit_mode = env.get("NEXUSCTL_GITHUB_MODE", "").strip().lower()
        app_id = _none_if_blank(env.get("GITHUB_APP_ID"))
        installation_id = _none_if_blank(env.get("GITHUB_APP_INSTALLATION_ID"))
        private_key_path = _none_if_blank(env.get("GITHUB_APP_PRIVATE_KEY_PATH") or env.get("GITHUB_APP_PRIVATE_KEY_FILE"))
        webhook_secret = _none_if_blank(env.get("GITHUB_WEBHOOK_SECRET"))
        has_credentials = bool(app_id and installation_id and private_key_path)
        if explicit_mode in {"mock", "dry-run", "dry_run"}:
            mode = "mock"
        elif explicit_mode in {"github", "real", "app"}:
            mode = "github"
        else:
            mode = "github" if has_credentials else "mock"
        return cls(
            mode=mode,
            app_id=app_id,
            installation_id=installation_id,
            private_key_path=private_key_path,
            webhook_secret_set=bool(webhook_secret),
            api_url=env.get("GITHUB_API_URL", "https://api.github.com"),
        )

    @property
    def mock_mode(self) -> bool:
        return self.mode == "mock"

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.installation_id and self.private_key_path)

    @property
    def private_key_exists(self) -> bool:
        return bool(self.private_key_path and Path(self.private_key_path).expanduser().is_file())

    def missing_credentials(self) -> list[str]:
        missing: list[str] = []
        if not self.app_id:
            missing.append("GITHUB_APP_ID")
        if not self.installation_id:
            missing.append("GITHUB_APP_INSTALLATION_ID")
        if not self.private_key_path:
            missing.append("GITHUB_APP_PRIVATE_KEY_PATH")
        elif not self.private_key_exists:
            missing.append("GITHUB_APP_PRIVATE_KEY_PATH:file_not_found")
        return missing

    def status(self) -> dict[str, Any]:
        missing = self.missing_credentials()
        return {
            "mode": self.mode,
            "mock_mode": self.mock_mode,
            "configured": self.configured and not missing,
            "api_url": self.api_url,
            "app_id_present": self.app_id is not None,
            "installation_id_present": self.installation_id is not None,
            "private_key_path_present": self.private_key_path is not None,
            "private_key_file_present": self.private_key_exists,
            "webhook_secret_set": self.webhook_secret_set,
            "missing_credentials": missing,
            "agents_receive_github_tokens": False,
        }


class GitHubAppAuthenticator:
    """Small facade used by GitHub clients to report availability.

    Token minting for real GitHub App JWTs is intentionally not implemented in
    GitHub projection workflow because local tests must remain credential-free. The class still
    centralizes configuration so a later adapter can add real network auth
    without changing service-level policy.
    """

    def __init__(self, config: GitHubAppConfig | None = None) -> None:
        self.config = config or GitHubAppConfig.from_env()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "GitHubAppAuthenticator":
        return cls(GitHubAppConfig.from_env(environ))

    def status(self) -> dict[str, Any]:
        return self.config.status()

    def installation_token(self) -> str:
        """Return an installation token in future real mode.

        GitHub projection workflow never exposes a GitHub token to agents. Real token exchange is
        deferred; mock mode avoids blocking tests and local development when app
        credentials are absent.
        """

        raise RuntimeError("real GitHub App token exchange is not implemented in GitHub projection workflow; use mock mode")


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
