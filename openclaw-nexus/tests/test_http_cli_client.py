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
from nexusctl.interfaces.http.client import APIClientError, NexusctlAPIClient
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


def test_http_client_api_client_health_and_auth_me(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-analyst")

    with RunningServer(db) as server:
        client = NexusctlAPIClient(server.url, token=token, timeout=2.0)
        assert client.health()["ok"] is True
        auth = client.auth_me()
        assert auth["agent"]["agent_id"] == "trading-analyst"
        assert "goal.read" in auth["capabilities"]


def test_http_client_me_command_can_run_against_remote_api(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-analyst")

    with RunningServer(db) as server:
        result = run_cli(["me", "--api-url", server.url, "--json"], env={"NEXUSCTL_TOKEN": token})

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["transport"] == "http"
    assert payload["identity"]["agent_id"] == "trading-analyst"
    assert "goal.read" in payload["identity"]["capabilities"]


def test_http_client_me_capabilities_remote_preserves_cli_shape(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    token = login(db, "trading-analyst")

    with RunningServer(db) as server:
        result = run_cli(["me", "capabilities", "--api-url", server.url, "--json"], env={"NEXUSCTL_TOKEN": token})

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["transport"] == "http"
    assert payload["agent_id"] == "trading-analyst"
    assert "goal.measure" in payload["capabilities"]


def test_http_client_api_client_reports_http_errors(tmp_path: Path) -> None:
    db = tmp_path / "nexus.db"
    login(db, "trading-analyst")

    with RunningServer(db) as server:
        client = NexusctlAPIClient(server.url, token="not-a-real-token", timeout=2.0)
        try:
            client.auth_me()
        except APIClientError as exc:
            assert "invalid" in str(exc).lower() or "token" in str(exc).lower()
        else:  # pragma: no cover - defensive assertion path
            raise AssertionError("expected APIClientError")
