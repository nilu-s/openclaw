from __future__ import annotations

import json
from pathlib import Path
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.token_registry import AgentTokenRegistry, hash_token_secret, verify_token_secret
from nexusctl.domain.errors import PolicyDeniedError
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database
from nexusctl.interfaces.cli.main import main as cli_main


def test_auth_token_hashing_never_stores_plain_secret() -> None:
    secret = "local-test-secret"
    encoded = hash_token_secret(secret)

    assert secret not in encoded
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_token_secret(secret, encoded) is True
    assert verify_token_secret("wrong-secret", encoded) is False


def test_auth_agent_registry_authenticates_subject_and_session_ttl(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        registry = AgentTokenRegistry(connection, session_ttl_seconds=900)
        credential, session = registry.issue_local_login("trading-analyst")
        connection.commit()

        assert credential.agent_id == "trading-analyst"
        assert credential.token.startswith("nxs1_tok-")
        assert session.subject.domain == "trading"
        assert session.subject.role == "measurement_analyst"
        assert "goal.read" in session.subject.capabilities
        assert 0 < session.to_json()["ttl_seconds"] <= 900

        stored = connection.execute(
            "SELECT token_hash FROM agent_tokens WHERE token_id = ?", (credential.token_id,)
        ).fetchone()["token_hash"]
        assert credential.token not in stored

        authenticated = registry.authenticate(credential.token)
        assert authenticated.subject.agent_id == "trading-analyst"
        assert authenticated.subject.domain == "trading"
    finally:
        connection.close()


def test_auth_rotate_token_is_control_or_platform_only(tmp_path: Path) -> None:
    connection = connect_database(tmp_path / "nexus.db")
    try:
        init_database(connection, ROOT, seed_blueprint=True)
        registry = AgentTokenRegistry(connection)
        _, trading_session = registry.issue_local_login("trading-analyst")
        _, nexus_session = registry.issue_local_login("control-router")

        with pytest.raises(PolicyDeniedError):
            registry.rotate_token("software-builder", actor=trading_session.subject)

        rotated = registry.rotate_token("software-builder", actor=nexus_session.subject)
        assert rotated.agent_id == "software-builder"
        assert rotated.token.startswith("nxs1_tok-")
    finally:
        connection.close()


def test_auth_domain_override_policy_allows_nexus_but_not_normal_agents() -> None:
    matrix = CapabilityMatrix.from_project_root(ROOT)
    policy = PolicyEngine(matrix)

    analyst = matrix.subject_for_agent("trading-analyst")
    denied = policy.authorize(analyst, "goal.read", resource_domain="software", requested_domain="software")
    assert denied.allowed is False
    assert denied.rule_id == "agent_domain_is_auth_derived"

    nexus = matrix.subject_for_agent("control-router")
    allowed = policy.authorize(nexus, "goal.read", resource_domain="trading", requested_domain="trading")
    assert allowed.allowed is True


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def run_cli(args: list[str], *, env: dict[str, str] | None = None) -> CliResult:
    old_env = os.environ.copy()
    os.environ.update(env or {})
    stdout = StringIO()
    stderr = StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = cli_main(args)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    return CliResult(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def test_auth_cli_me_capabilities_and_goal_domain_resolution(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    init = run_cli(["db", "init", "--db", str(db), "--project-root", str(ROOT), "--json"])
    assert init.returncode == 0, init.stderr

    login = run_cli([
        "auth",
        "login",
        "--agent",
        "trading-analyst",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ])
    assert login.returncode == 0, login.stderr
    token = json.loads(login.stdout)["credential"]["token"]
    env = {"NEXUSCTL_TOKEN": token}

    me = run_cli(["me", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert me.returncode == 0, me.stderr
    identity = json.loads(me.stdout)["identity"]
    assert identity["agent_id"] == "trading-analyst"
    assert identity["domain"] == "trading"
    assert identity["domain_source"] == "auth_token"

    caps = run_cli(["me", "capabilities", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert caps.returncode == 0, caps.stderr
    assert "goal.measure" in json.loads(caps.stdout)["capabilities"]

    status = run_cli(["goals", "status", "--db", str(db), "--project-root", str(ROOT), "--json"], env=env)
    assert status.returncode == 0, status.stderr
    body = json.loads(status.stdout)
    assert body["visible_domain"] == "trading"
    assert {goal["domain"] for goal in body["goals"]} == {"trading"}

    denied = run_cli(
        ["goals", "status", "--domain", "software", "--db", str(db), "--project-root", str(ROOT), "--json"],
        env=env,
    )
    assert denied.returncode == 3
    assert json.loads(denied.stdout)["rule_id"] == "agent_domain_is_auth_derived"


def test_auth_cli_control_router_can_read_policy_limited_domain_override(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    login = run_cli([
        "auth",
        "login",
        "--agent",
        "control-router",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ])
    assert login.returncode == 0, login.stderr
    token = json.loads(login.stdout)["credential"]["token"]

    status = run_cli(
        ["goals", "status", "--domain", "trading", "--db", str(db), "--project-root", str(ROOT), "--json"],
        env={"NEXUSCTL_TOKEN": token},
    )
    assert status.returncode == 0, status.stderr
    body = json.loads(status.stdout)
    assert body["agent_id"] == "control-router"
    assert body["visible_domain"] == "trading"
    assert body["domain_source"] == "policy_allowed_override"
