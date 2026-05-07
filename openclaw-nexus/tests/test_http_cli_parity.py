from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import json
import os
from pathlib import Path
import sys
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.interfaces.cli.main import main as cli_main
from nexusctl.interfaces.http.server import make_server


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
        "auth", "login", "--agent", agent,
        "--db", str(db), "--project-root", str(ROOT), "--json",
    ])
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["credential"]["token"]


class RunningServer:
    def __init__(self, db: Path):
        self.server = make_server("127.0.0.1", 0, db_path=db, project_root=ROOT)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "RunningServer":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def remote_json(args: list[str], *, server_url: str, token: str) -> dict:
    result = run_cli([*args, "--api-url", server_url, "--json"], env={"NEXUSCTL_TOKEN": token})
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["transport"] == "http"
    return payload


def test_http_cli_parity_feature_request_create_list_and_route_can_use_remote_api(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    trading_token = login(db, "trading-strategist")
    nexus_token = login(db, "control-router")

    with RunningServer(db) as server:
        created = remote_json([
            "feature-request", "create",
            "--target", "software",
            "--goal", "trade_success_quality",
            "--title", "Remote API parity request",
        ], server_url=server.url, token=trading_token)["feature_request"]
        assert created["source_domain"] == "trading"
        assert created["target_domain"] == "software"
        assert created["status"] == "proposed"

        listed = remote_json(["feature-request", "list"], server_url=server.url, token=trading_token)
        assert [item["id"] for item in listed["feature_requests"]] == [created["id"]]

        routed = remote_json([
            "feature-request", "route", created["id"], "--target", "software",
        ], server_url=server.url, token=nexus_token)["feature_request"]
        assert routed["id"] == created["id"]
        assert routed["status"] == "routed"


def test_http_cli_parity_work_plan_and_assign_can_use_remote_api(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    trading_token = login(db, "trading-strategist")
    nexus_token = login(db, "control-router")
    architect_token = login(db, "software-architect")
    techlead_token = login(db, "software-techlead")

    with RunningServer(db) as server:
        request = remote_json([
            "feature-request", "create",
            "--target", "software",
            "--goal", "trade_success_quality",
            "--title", "Remote planning workflow",
        ], server_url=server.url, token=trading_token)["feature_request"]
        remote_json(["feature-request", "route", request["id"], "--target", "software"], server_url=server.url, token=nexus_token)

        issue = run_cli([
            "github", "issue", "sync", request["id"],
            "--db", str(db), "--project-root", str(ROOT), "--json",
        ], env={"NEXUSCTL_TOKEN": nexus_token})
        assert issue.returncode == 0, issue.stderr or issue.stdout

        planned = remote_json(["work", "plan", request["id"]], server_url=server.url, token=architect_token)["work"]
        assert planned["feature_request_id"] == request["id"]
        assert planned["status"] == "planned"

        assigned = remote_json([
            "work", "assign", request["id"],
            "--builder", "software-builder",
            "--reviewer", "software-reviewer",
        ], server_url=server.url, token=techlead_token)["work"]
        assert assigned["id"] == planned["id"]
        assert assigned["status"] == "ready"
        assert assigned["builder"] == "software-builder"
