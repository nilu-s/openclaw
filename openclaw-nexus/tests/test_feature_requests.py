from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.interfaces.cli.main import main as cli_main
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


def create_request(db: Path, token: str, title: str = "Need portfolio risk dashboard export") -> dict:
    result = run_cli([
        "feature-request",
        "create",
        "--target",
        "software",
        "--goal",
        "trade_success_quality",
        "--title",
        title,
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": token})
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["feature_request"]


def test_feature_requests_trading_strategist_creates_software_feature_request_from_auth_domain(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-strategist")

    request = create_request(db, token)

    assert request["source_domain"] == "trading"
    assert request["target_domain"] == "software"
    assert request["goal_id"] == "trade_success_quality"
    assert request["created_by"] == "trading-strategist"
    assert request["status"] == "proposed"
    assert request["acceptance_contract"]["required_acceptance_domain"] == "trading"
    assert "repo.apply" in request["safety_contract"]["forbidden_source_capabilities"]
    assert request["dedupe_key"].startswith("frd-")

    listed = run_cli([
        "feature-request",
        "list",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": token})
    assert listed.returncode == 0, listed.stderr
    body = json.loads(listed.stdout)
    assert body["domain_source"] == "auth_token"
    assert [item["id"] for item in body["feature_requests"]] == [request["id"]]

    connection = connect_database(db)
    try:
        row = connection.execute("SELECT source_domain_id, target_domain_id, dedupe_key FROM feature_requests").fetchone()
        assert row["source_domain_id"] == "trading"
        assert row["target_domain_id"] == "software"
        assert row["dedupe_key"] == request["dedupe_key"]
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("feature_request", request["id"])]
        assert "feature_request.created" in events
    finally:
        connection.close()


def test_feature_requests_source_domain_cannot_be_forged_via_goal_or_cli(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-strategist")

    forged = run_cli([
        "feature-request",
        "create",
        "--target",
        "software",
        "--goal",
        "software_delivery_quality",
        "--title",
        "Pretend this came from software",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": token})

    assert forged.returncode == 3
    body = json.loads(forged.stdout)
    assert body["rule_id"] == "feature_request_source_domain_from_subject"


def test_feature_requests_nexus_can_route_and_transition_requests(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    trading_token = login(db, "trading-strategist")
    request = create_request(db, trading_token)
    nexus_token = login(db, "control-router")

    route = run_cli([
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
    ], env={"NEXUSCTL_TOKEN": nexus_token})
    assert route.returncode == 0, route.stderr or route.stdout
    routed = json.loads(route.stdout)["feature_request"]
    assert routed["status"] == "routed"
    assert routed["source_domain"] == "trading"
    assert routed["target_domain"] == "software"

    transition = run_cli([
        "feature-request",
        "transition",
        request["id"],
        "in_progress",
        "--db",
        str(db),
        "--project-root",
        str(ROOT),
        "--json",
    ], env={"NEXUSCTL_TOKEN": nexus_token})
    assert transition.returncode == 0, transition.stderr or transition.stdout
    assert json.loads(transition.stdout)["feature_request"]["status"] == "in_progress"

    connection = connect_database(db)
    try:
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("feature_request", request["id"])]
        assert "feature_request.routed" in events
        assert "feature_request.transitioned" in events
    finally:
        connection.close()


def test_feature_requests_dedupe_returns_existing_request_and_audits_it(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-strategist")

    first = create_request(db, token, title="Deduplicate this software request")
    second = create_request(db, token, title="  Deduplicate   this software request  ")

    assert second["id"] == first["id"]
    assert second["dedupe_key"] == first["dedupe_key"]
    assert second["deduplicated"] is True

    connection = connect_database(db)
    try:
        assert connection.execute("SELECT COUNT(*) AS c FROM feature_requests").fetchone()["c"] == 1
        events = [event.event_type for event in EventStore(connection).list_for_aggregate("feature_request", first["id"])]
        assert "feature_request.deduplicated" in events
    finally:
        connection.close()
