from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WIZARD_PATH = ROOT / "scripts" / "deployment_wizard.py"


def load_wizard():
    spec = importlib.util.spec_from_file_location("deployment_wizard", WIZARD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["deployment_wizard"] = module
    spec.loader.exec_module(module)
    return module


def test_deployment_wizard_generates_reviewable_named_volume_bundle(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(WIZARD_PATH),
            "--non-interactive",
            "--profile",
            "internal-production",
            "--volume-mode",
            "named",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    env_file = tmp_path / ".env.internal-production"
    compose_override = tmp_path / "docker-compose.override.yml"
    bootstrap = tmp_path / "bootstrap-operator-token.sh"
    readme = tmp_path / "README.md"

    assert env_file.exists()
    assert compose_override.exists()
    assert bootstrap.exists()
    assert readme.exists()

    env_text = env_file.read_text(encoding="utf-8")
    assert "NEXUSCTL_DEPLOYMENT_MODE=internal-production" in env_text
    assert "NEXUSCTL_API_TLS_ENABLED=1" in env_text
    assert "NEXUSCTL_API_ALLOW_INSECURE_REMOTE_BIND=0" in env_text
    assert "GITHUB_WEBHOOK_SECRET=change-me" not in env_text
    assert "NEXUSCTL_RECOVERY_EVIDENCE_DIR=/recovery-evidence" in env_text
    assert "NEXUSCTL_BACKUP_RETENTION_DAYS=30" in env_text
    assert "NEXUSCTL_BACKUP_RETENTION_MIN_COPIES=7" in env_text
    assert "NEXUSCTL_OFFSITE_BACKUP_ENABLED=0" in env_text
    assert "NEXUSCTL_OFFSITE_BACKUP_TARGET=operator-managed-offsite-location" in env_text
    assert "NEXUSCTL_OFFSITE_BACKUP_SCHEDULE=daily" in env_text
    secret_line = next(line for line in env_text.splitlines() if line.startswith("GITHUB_WEBHOOK_SECRET="))
    assert len(secret_line.split("=", 1)[1]) >= 48

    compose_text = compose_override.read_text(encoding="utf-8")
    assert "openclaw-nexus-data" in compose_text
    assert "openclaw-nexus-backups" in compose_text
    assert "openclaw-nexus-recovery-evidence" in compose_text

    bootstrap_text = bootstrap.read_text(encoding="utf-8")
    assert "nexusctl-cli db init" in bootstrap_text
    assert "auth login --agent operator" in bootstrap_text
    assert "credential.token" in bootstrap_text

    readme_text = readme.read_text(encoding="utf-8")
    assert "DB-gebundenen Operator-Token" in readme_text
    assert "generated/` wird von OpenClaw read-only konsumiert" in readme_text
    assert "Recovery Evidence Pack" in readme_text
    assert "Internal-Production-Preflight" in readme_text
    assert "nexusctl db init" in readme_text
    assert "nexusctl doctor --json" in readme_text
    assert "--evidence-path" in readme_text
    assert "NEXUSCTL_RECOVERY_EVIDENCE_DIR" in readme_text
    assert "Retention" in readme_text
    assert "Offsite" in readme_text


def test_deployment_wizard_host_volume_override_mounts_persistent_targets(tmp_path: Path) -> None:
    wizard = load_wizard()
    config = wizard.WizardConfig(
        profile="development",
        output_dir=tmp_path / "bundle",
        api_host="0.0.0.0",
        api_port=8080,
        openclaw_gateway_port=8090,
        volume_mode="host",
        host_volume_root=tmp_path / "volumes",
        github_mode="mock",
        webhook_reconciliation=False,
        generate_webhook_secret=True,
        github_webhook_secret="x" * 64,
    )

    written = wizard.write_bundle(config)

    for dirname in ["nexus_data", "nexus_backups", "recovery_evidence", "workspaces", "repo_worktrees"]:
        assert (tmp_path / "volumes" / dirname).is_dir()

    compose_text = written["compose_override"].read_text(encoding="utf-8")
    assert f"{(tmp_path / 'volumes' / 'nexus_data').as_posix()}:/data" in compose_text
    assert f"{(tmp_path / 'volumes' / 'nexus_backups').as_posix()}:/backups" in compose_text
    assert f"{(tmp_path / 'volumes' / 'recovery_evidence').as_posix()}:/recovery-evidence" in compose_text
    assert f"{(tmp_path / 'volumes' / 'workspaces').as_posix()}:/workspaces" in compose_text
    assert f"{(tmp_path / 'volumes' / 'repo_worktrees').as_posix()}:/repo-worktrees" in compose_text
    assert "../nexus:/workspace/nexus:ro" in compose_text
    assert "../generated:/generated:ro" in compose_text
