from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.app.scope_service import PathScope, ScopeService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.domain.errors import PolicyDeniedError, ValidationError
from nexusctl.storage.event_store import EventStore
from nexusctl.storage.sqlite.connection import connect_database


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


from nexusctl.interfaces.cli.main import main as cli_main


def login(db: Path, agent: str) -> str:
    result = run_cli([
        "auth",
        "login",
        "--agent",
        agent,
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ])
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["credential"]["token"]


def create_route_and_sync_request(db: Path) -> tuple[dict, dict[str, str]]:
    tokens = {
        "trading": login(db, "trading-strategist"),
        "control": login(db, "control-router"),
        "architect": login(db, "software-architect"),
        "techlead": login(db, "software-techlead"),
        "builder": login(db, "software-builder"),
    }
    created = run_cli([
        "feature-request",
        "create",
        "--target",
        "software",
        "--goal",
        "trade_success_quality",
        "--title",
        "Need scoped work planning for execution export",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["trading"]})
    assert created.returncode == 0, created.stderr or created.stdout
    request = json.loads(created.stdout)["feature_request"]

    routed = run_cli([
        "feature-request",
        "route",
        request["id"],
        "--target",
        "software",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert routed.returncode == 0, routed.stderr or routed.stdout
    request = json.loads(routed.stdout)["feature_request"]

    issue = run_cli([
        "github",
        "issue",
        "sync",
        request["id"],
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert issue.returncode == 0, issue.stderr or issue.stdout
    return request, tokens


def test_work_scopes_work_plan_and_assign_references_feature_request_and_github_issue(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, tokens = create_route_and_sync_request(db)

    planned = run_cli([
        "work",
        "plan",
        request["id"],
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["architect"]})
    assert planned.returncode == 0, planned.stderr or planned.stdout
    work = json.loads(planned.stdout)["work"]
    assert work["feature_request_id"] == request["id"]
    assert work["feature_request"]["target_domain"] == "software"
    assert work["github_issue"]["issue_number"] == 1
    assert work["status"] == "planned"

    assigned = run_cli([
        "work",
        "assign",
        request["id"],
        "--builder",
        "software-builder",
        "--reviewer",
        "software-reviewer",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["techlead"]})
    assert assigned.returncode == 0, assigned.stderr or assigned.stdout
    assigned_work = json.loads(assigned.stdout)["work"]
    assert assigned_work["id"] == work["id"]
    assert assigned_work["builder"] == "software-builder"
    assert assigned_work["reviewer"] == "software-reviewer"
    assert assigned_work["status"] == "ready"

    connection = connect_database(db)
    try:
        row = connection.execute("SELECT feature_request_id, reviewer_agent_id FROM work_items WHERE id = ?", (work["id"],)).fetchone()
        assert row["feature_request_id"] == request["id"]
        assert row["reviewer_agent_id"] == "software-reviewer"
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("work_item", work["id"])]
        assert "work_item.planned" in events
        assert "work_item.assigned" in events
    finally:
        connection.close()


def test_work_scopes_scope_lease_is_granted_by_nexus_path_bounded_and_usable_by_builder(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, tokens = create_route_and_sync_request(db)
    assign = run_cli([
        "work",
        "assign",
        request["id"],
        "--builder",
        "software-builder",
        "--reviewer",
        "software-reviewer",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["techlead"]})
    assert assign.returncode == 0, assign.stderr or assign.stdout

    lease_result = run_cli([
        "scopes",
        "lease",
        "--agent",
        "software-builder",
        "--request",
        request["id"],
        "--paths",
        "nexusctl/src/**,tests/test_work_scopes.py",
        "--ttl",
        "2h",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert lease_result.returncode == 0, lease_result.stderr or lease_result.stdout
    lease = json.loads(lease_result.stdout)["scope_lease"]
    assert lease["status"] == "active"
    assert lease["agent_id"] == "software-builder"
    assert lease["capabilities"] == ["patch.submit"]
    assert "nexusctl/src/**" in lease["paths"]

    connection = connect_database(db)
    try:
        registry = AgentTokenRegistry(connection)
        builder_session = registry.authenticate(tokens["builder"])
        service = ScopeService(connection, PolicyEngine(CapabilityMatrix.from_project_root(ROOT)))
        ok = service.assert_usable(
            builder_session.subject,
            lease_id=lease["id"],
            capability_id="patch.submit",
            path="nexusctl/src/nexusctl/app/work_service.py",
        )
        assert ok["ok"] is True
        with pytest.raises(PolicyDeniedError) as denied:
            service.assert_usable(
                builder_session.subject,
                lease_id=lease["id"],
                capability_id="patch.submit",
                path="nexus/trading.yml",
            )
        assert denied.value.rule_id == "scope_path_bound"
    finally:
        connection.close()


def test_work_scopes_builder_cannot_grant_and_trading_cannot_receive_software_lease(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    request, tokens = create_route_and_sync_request(db)
    assign = run_cli([
        "work",
        "assign",
        request["id"],
        "--builder",
        "software-builder",
        "--reviewer",
        "software-reviewer",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["techlead"]})
    assert assign.returncode == 0, assign.stderr or assign.stdout

    builder_grant = run_cli([
        "scopes",
        "lease",
        "--agent",
        "software-builder",
        "--request",
        request["id"],
        "--paths",
        "nexusctl/src/**",
        "--ttl",
        "30m",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["builder"]})
    assert builder_grant.returncode == 3

    trading_recipient = run_cli([
        "scopes",
        "lease",
        "--agent",
        "trading-strategist",
        "--request",
        request["id"],
        "--paths",
        "nexusctl/src/**",
        "--ttl",
        "30m",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert trading_recipient.returncode == 3
    assert json.loads(trading_recipient.stdout)["rule_id"] == "trading_cannot_receive_software_lease"


def test_work_scopes_ttl_expiry_and_path_scope_validation(tmp_path: Path) -> None:
    assert PathScope.from_patterns(["nexusctl/src/**"]).allows("nexusctl/src/nexusctl/app/scope_service.py")
    assert not PathScope.from_patterns(["nexusctl/src/**"]).allows("README.md")
    with pytest.raises(ValidationError):
        PathScope.from_patterns(["../outside"])

    db = tmp_path / "nexus.db"
    request, tokens = create_route_and_sync_request(db)
    assign = run_cli([
        "work",
        "assign",
        request["id"],
        "--builder",
        "software-builder",
        "--reviewer",
        "software-reviewer",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["techlead"]})
    assert assign.returncode == 0, assign.stderr or assign.stdout
    lease_result = run_cli([
        "scopes",
        "lease",
        "--agent",
        "software-builder",
        "--request",
        request["id"],
        "--paths",
        "nexusctl/src/**",
        "--ttl",
        "1h",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": tokens["control"]})
    assert lease_result.returncode == 0, lease_result.stderr or lease_result.stdout
    lease_id = json.loads(lease_result.stdout)["scope_lease"]["id"]

    connection = connect_database(db)
    try:
        expired_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        connection.execute("UPDATE scope_leases SET expires_at = ? WHERE id = ?", (expired_at, lease_id))
        connection.commit()
        registry = AgentTokenRegistry(connection)
        builder_session = registry.authenticate(tokens["builder"])
        service = ScopeService(connection, PolicyEngine(CapabilityMatrix.from_project_root(ROOT)))
        shown = service.show(builder_session.subject, lease_id)
        assert shown["status"] == "expired"
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("scope_lease", lease_id)]
        assert "scope_lease.expired" in events
    finally:
        connection.close()
