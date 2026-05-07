from __future__ import annotations

import json
from pathlib import Path
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nexusctl" / "src"))

from nexusctl.domain.errors import ValidationError
from nexusctl.interfaces.http.client import NexusctlAPIClient
from nexusctl.interfaces.http.operational import HTTPClientSettings, HTTPServerSettings, SessionStore
from nexusctl.interfaces.http.server import make_server


def test_operational_hardening_server_settings_default_to_loopback_and_bounded_bodies(monkeypatch) -> None:
    monkeypatch.delenv("NEXUSCTL_API_HOST", raising=False)
    monkeypatch.delenv("NEXUSCTL_API_MAX_BODY_BYTES", raising=False)

    settings = HTTPServerSettings.from_environment()

    assert settings.host == "127.0.0.1"
    assert settings.max_body_bytes == 1_048_576


def test_operational_hardening_remote_plain_http_bindings_require_explicit_operator_opt_in(tmp_path: Path) -> None:
    try:
        make_server("0.0.0.0", 0, db_path=tmp_path / "nexus.db", project_root=ROOT)
    except ValidationError as exc:
        assert "require TLS" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected remote plain HTTP binding to be rejected")

    server = make_server(
        "0.0.0.0",
        0,
        db_path=tmp_path / "nexus.db",
        project_root=ROOT,
        allow_insecure_remote_bind=True,
    )
    server.server_close()


def test_operational_hardening_client_rejects_insecure_non_loopback_urls_without_opt_in() -> None:
    try:
        NexusctlAPIClient("http://nexusctl-api:8080", token="x")
    except ValidationError as exc:
        assert "must use HTTPS" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected non-loopback plain HTTP URL to be rejected")

    client = NexusctlAPIClient("http://nexusctl-api:8080", token="x", allow_insecure_remote=True)
    assert client.base_url == "http://nexusctl-api:8080/"


def test_operational_hardening_client_settings_are_centralized_in_environment(monkeypatch) -> None:
    monkeypatch.setenv("NEXUSCTL_API_TIMEOUT_SECONDS", "3.25")
    monkeypatch.setenv("NEXUSCTL_API_READ_RETRIES", "2")

    settings = HTTPClientSettings.from_environment()
    client = NexusctlAPIClient("http://127.0.0.1:1", token="x")

    assert settings.timeout_seconds == 3.25
    assert settings.read_retries == 2
    assert client.timeout == 3.25
    assert client.read_retries == 2


def test_operational_hardening_body_size_limit_is_enforced_before_route_dispatch(tmp_path: Path) -> None:
    server = make_server("127.0.0.1", 0, db_path=tmp_path / "nexus.db", project_root=ROOT, max_body_bytes=8)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        request = Request(
            f"http://{host}:{port}/feature-requests",
            data=json.dumps({"payload": "too-large"}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
        except HTTPError as exc:
            assert exc.code == 413
            assert "exceeds" in exc.read().decode("utf-8")
        else:  # pragma: no cover - defensive assertion path
            raise AssertionError("expected HTTP 413")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operational_hardening_session_store_issues_and_touches_transport_sessions() -> None:
    store = SessionStore(ttl_seconds=60)
    session_id = store.issue(agent_id="control-router")

    session = store.touch(session_id)

    assert session is not None
    assert session["agent_id"] == "control-router"
    assert session["transport"] == "http"
