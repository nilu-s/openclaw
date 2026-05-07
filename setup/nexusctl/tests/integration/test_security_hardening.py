from __future__ import annotations

import io
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from nexusctl.backend.server import BackendConfig, start_server
from nexusctl.backend.storage import Storage, initialize_database, seed_mvp_data
from nexusctl.cli import run
import nexusctl.api as api_module

pytestmark = pytest.mark.integration


def _auth(base_url: str, token: str) -> dict:
    req = Request(
        url=f"{base_url}/v1/nexus/auth",
        method="POST",
        data=json.dumps({"agent_token": token}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"},
    )
    with urlopen(req, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def test_server_rejects_non_localhost_bind_without_tls(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    try:
        running = start_server(BackendConfig(host="0.0.0.0", port=0, db_path=db_path))
    except Exception:
        return
    running.stop()
    raise AssertionError("expected non-localhost bind to be rejected without TLS")


def test_embedded_server_stops_without_requests(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    running = start_server(BackendConfig(host="127.0.0.1", port=0, db_path=db_path))
    running.stop(timeout_seconds=1.0)


def test_seed_defaults_do_not_accept_demo_tokens(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path)
    storage = Storage(db_path)
    try:
        storage.authenticate(agent_token="tok_trading")
    except Exception:
        return
    raise AssertionError("expected demo token to be rejected in default seed mode")


def test_initialize_database_uses_hard_cutoff_agent_registry_schema(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)

    storage = Storage(db_path)
    conn = storage._connect()
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(agent_registry)").fetchall()}
    finally:
        conn.close()

    assert "agent_token" not in columns
    assert "default_system_id" in columns
    assert {"agent_token_hash", "agent_token_salt"}.issubset(columns)


def test_cli_rejects_insecure_remote_http_base_url(cli_env):
    env = dict(cli_env)
    env["NEXUSCTL_API_BASE_URL"] = "http://192.0.2.20:8080"
    rc = run(["auth", "--agent-token", "tok_trading"], env=env)
    assert rc == 2


@pytest.mark.networkish
def test_cli_allows_insecure_remote_http_base_url_when_explicitly_enabled(cli_env, monkeypatch):
    def fail_fast_urlopen(*_args, **_kwargs):
        raise URLError("network disabled in test")

    monkeypatch.setattr(api_module, "urlopen", fail_fast_urlopen)
    env = dict(cli_env)
    env["NEXUSCTL_API_BASE_URL"] = "http://192.0.2.20:8080"
    env["NEXUSCTL_ALLOW_INSECURE_REMOTE"] = "true"
    env["NEXUSCTL_AUTH_TIMEOUT_SECONDS"] = "0.2"
    rc = run(["auth", "--agent-token", "tok_trading"], env=env)
    assert rc == 10


def test_auth_rejects_domain_override_parameter(cli_env):
    rc = run(["auth", "--agent-token", "tok_trading", "--domain", "Software", "--output", "json"], env=cli_env)
    assert rc == 2


def test_seeded_registry_does_not_store_plaintext_tokens(backend_server):
    columns = {row[1] for row in backend_server.fetchall("PRAGMA table_info(agent_registry)")}
    assert "agent_token" not in columns
    assert {"agent_token_hash", "agent_token_salt"}.issubset(columns)

    rows = backend_server.fetchall("SELECT agent_token_hash, agent_token_salt FROM agent_registry")
    assert rows
    assert all(row[0] and row[1] for row in rows)


def test_auth_id_and_session_id_are_randomized(cli_env):
    out = io.StringIO()
    err = io.StringIO()
    rc = run(["auth", "--agent-token", "tok_trading", "--output", "json"], env=cli_env, out=out, err=err)
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert re.match(r"^AUTH-2026-[0-9a-f]{16}$", payload["auth_id"])
    assert re.match(r"^S-2026-[0-9a-f]{16}$", payload["session_id"])


def test_status_event_id_is_randomized(cli_env, backend_server):
    assert run(["auth", "--agent-token", "tok_techlead", "--output", "json"], env=cli_env) == 0
    backend_server.execute(
        "UPDATE capability_requirements SET status = 'verified' WHERE capability_id = ?",
        ("F-002",),
    )
    backend_server.execute(
        "UPDATE capability_evidence SET issue_ref = ?, pr_ref = ?, test_ref = ? WHERE capability_id = ?",
        ("issue://123", "pr://123", "test://123", "F-002"),
    )
    out = io.StringIO()
    err = io.StringIO()
    rc = run(
        [
            "capabilities",
            "set-status",
            "F-002",
            "--to",
            "available",
            "--reason",
            "All requirements verified and evidence linked.",
            "--output",
            "json",
        ],
        env=cli_env,
        out=out,
        err=err,
    )
    assert rc == 0, err.getvalue()
    payload = json.loads(out.getvalue())
    assert re.match(r"^CAP-STATUS-2026-[0-9a-f]{16}$", payload["event_id"])


def test_large_json_payload_is_rejected(backend_server):
    request = Request(
        url=f"{backend_server.base_url}/v1/nexus/auth",
        method="POST",
        data=json.dumps({"agent_token": "tok_trading", "padding": "x" * (70 * 1024)}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"},
    )
    try:
        with urlopen(request, timeout=2):
            raise AssertionError("expected oversized payload to be rejected")
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error_code"] == "NX-VAL-001"
        finally:
            exc.close()


def test_agent_header_must_match_session(backend_server):
    auth_payload = _auth(backend_server.base_url, "tok_trading")
    request = Request(
        url=f"{backend_server.base_url}/v1/nexus/capabilities?status=all",
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Nexus-Session-Id": auth_payload["session_id"],
            "X-Nexus-Agent-Id": "sw-techlead-01",
            "Connection": "close",
        },
    )
    try:
        with urlopen(request, timeout=2):
            raise AssertionError("expected mismatched agent header to be rejected")
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 403
            assert payload["error_code"] == "NX-PERM-001"
        finally:
            exc.close()


def test_capabilities_endpoint_rejects_domain_query_override(backend_server):
    auth_payload = _auth(backend_server.base_url, "tok_trading")
    request = Request(
        url=f"{backend_server.base_url}/v1/nexus/capabilities?status=all&domain=Trading",
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Nexus-Session-Id": auth_payload["session_id"],
            "X-Nexus-Agent-Id": auth_payload["agent_id"],
            "Connection": "close",
        },
    )
    try:
        with urlopen(request, timeout=2):
            raise AssertionError("expected domain query override to be rejected")
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 400
            assert payload["error_code"] == "NX-VAL-001"
        finally:
            exc.close()
