from __future__ import annotations

import io
import json
import re
import sqlite3
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nexusctl.backend.server import BackendConfig, start_server
from nexusctl.backend.storage import Storage, initialize_database, seed_mvp_data
from nexusctl.cli import run


def _auth(base_url: str, token: str) -> dict:
    req = Request(
        url=f"{base_url}/v1/nexus/auth",
        method="POST",
        data=json.dumps({"agent_token": token}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urlopen(req, timeout=5) as response:
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


def test_seed_defaults_do_not_accept_demo_tokens(tmp_path):
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path)
    storage = Storage(db_path)
    try:
        storage.authenticate(agent_token="tok_trading", domain=None)
    except Exception:
        return
    raise AssertionError("expected demo token to be rejected in default seed mode")


def test_initialize_database_migrates_legacy_agent_registry_schema(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE agent_registry (
                agent_token TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO agent_registry(agent_token, agent_id, role, project_id, domain, active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            ("tok_legacy", "legacy-agent", "sw-techlead", "legacy-project", "Software"),
        )
        conn.commit()
    finally:
        conn.close()

    initialize_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(agent_registry)").fetchall()}
    finally:
        conn.close()

    assert "agent_token" not in columns
    assert {"agent_token_hash", "agent_token_salt"}.issubset(columns)

    storage = Storage(db_path)
    auth = storage.authenticate(agent_token="tok_legacy", domain=None)
    assert auth["agent_id"] == "legacy-agent"
    assert auth["project_id"] == "legacy-project"


def test_cli_rejects_insecure_remote_http_base_url(cli_env):
    env = dict(cli_env)
    env["NEXUSCTL_API_BASE_URL"] = "http://192.0.2.20:8080"
    rc = run(["auth", "--agent-token", "tok_trading"], env=env)
    assert rc == 2


def test_auth_rejects_domain_override_mismatch(cli_env):
    rc = run(["auth", "--agent-token", "tok_trading", "--domain", "Software", "--output", "json"], env=cli_env)
    assert rc == 4


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
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=5):
            raise AssertionError("expected oversized payload to be rejected")
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        assert exc.code == 400
        assert payload["error_code"] == "NX-VAL-001"


def test_agent_header_must_match_session(backend_server):
    auth_payload = _auth(backend_server.base_url, "tok_trading")
    request = Request(
        url=f"{backend_server.base_url}/v1/nexus/capabilities?status=all",
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Nexus-Session-Id": auth_payload["session_id"],
            "X-Nexus-Agent-Id": "sw-techlead-01",
        },
    )
    try:
        with urlopen(request, timeout=5):
            raise AssertionError("expected mismatched agent header to be rejected")
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        assert exc.code == 403
        assert payload["error_code"] == "NX-PERM-001"
