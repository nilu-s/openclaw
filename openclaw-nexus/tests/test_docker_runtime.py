from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_compose() -> dict:
    return yaml.safe_load((ROOT / "config" / "docker-compose.yml").read_text(encoding="utf-8"))


def test_docker_runtime_compose_defines_required_services_volumes_and_healthchecks() -> None:
    compose = load_compose()
    services = compose.get("services", {})
    assert set(services) == {"openclaw-gateway", "nexusctl-api", "nexusctl-worker", "nexusctl-cli"}
    assert {"nexus-data", "workspaces", "repo-worktrees"}.issubset(set(compose.get("volumes", {})))

    for name in ["openclaw-gateway", "nexusctl-api", "nexusctl-worker"]:
        assert "healthcheck" in services[name], f"{name} must declare a healthcheck"

    api_volumes = services["nexusctl-api"].get("volumes", [])
    assert any("nexus-data:/data" in volume for volume in api_volumes)
    assert any("repo-worktrees:/repo-worktrees" in volume for volume in api_volumes)
    assert any("workspaces:/workspaces" in volume for volume in api_volumes)

    openclaw_volumes = services["openclaw-gateway"].get("volumes", [])
    assert any(str(volume).endswith(":/generated:ro") for volume in openclaw_volumes)
    assert any("workspaces:/workspaces" in volume for volume in openclaw_volumes)


def test_docker_runtime_dockerfiles_and_env_contract() -> None:
    nexusctl_dockerfile = (ROOT / "config" / "Dockerfile.nexusctl").read_text(encoding="utf-8")
    openclaw_dockerfile = (ROOT / "config" / "Dockerfile.openclaw").read_text(encoding="utf-8")
    env_example = (ROOT / "config" / ".env.example").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in nexusctl_dockerfile
    assert "pip install /tmp/nexusctl" in nexusctl_dockerfile
    assert "HEALTHCHECK" in nexusctl_dockerfile
    assert "VOLUME" in nexusctl_dockerfile

    assert "ARG OPENCLAW_BASE_IMAGE" in openclaw_dockerfile
    assert "OPENCLAW_CONFIG" in openclaw_dockerfile
    assert "HEALTHCHECK" in openclaw_dockerfile

    for required in [
        "GITHUB_APP_ID=",
        "GITHUB_APP_PRIVATE_KEY_PATH=",
        "GITHUB_APP_INSTALLATION_ID=",
        "GITHUB_WEBHOOK_SECRET=",
        "NEXUSCTL_DB=/data/nexus.db",
    ]:
        assert required in env_example


def test_docker_runtime_http_server_has_health_endpoint() -> None:
    from nexusctl.interfaces.http.server import make_server

    server = make_server("127.0.0.1", 0, db_path=ROOT / "nexus.db", project_root=ROOT)
    try:
        assert server.server_address[1] > 0
        assert server.RequestHandlerClass.project_root == ROOT
    finally:
        server.server_close()


def test_docker_runtime_current_state_documents_runtime_boundary() -> None:
    state = (ROOT / ".chatgpt" / "state" / "CURRENT_STATE.md").read_text(encoding="utf-8")
    assert "Docker-Konfiguration" in state
    assert "OpenClaw-Runtime" in state
    assert "HTTP-API" in state


def test_docker_runtime_separates_development_and_internal_production_profiles() -> None:
    compose = load_compose()
    dev_env = compose["x-nexusctl-dev-env"]
    prod_env = compose["x-nexusctl-internal-production-env"]
    common_env = compose["x-nexusctl-common"]["environment"]

    assert dev_env["NEXUSCTL_DEPLOYMENT_MODE"] == "development"
    assert dev_env["NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND"] == "1"
    assert prod_env["NEXUSCTL_DEPLOYMENT_MODE"] == "internal-production"
    assert prod_env["NEXUSCTL_API_TLS_ENABLED"] == "1"
    assert prod_env["NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND"] == "0"
    assert common_env["NEXUSCTL_BACKUP_DIR"] == "/backups"

    env_example = (ROOT / "config" / ".env.example").read_text(encoding="utf-8")
    assert "NEXUSCTL_DEPLOYMENT_MODE=development" in env_example
    assert "NEXUSCTL_WEBHOOK_RECONCILIATION_ENABLED=0" in env_example
    assert "change-me" in env_example
