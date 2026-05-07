from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.interfaces.http.routes import handle_api_request
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import init_database


ROOT = Path(__file__).resolve().parents[1]


def _db(tmp_path: Path):
    connection = connect_database(tmp_path / "nexus.db")
    init_database(connection, ROOT, seed_blueprint=True)
    return connection


def _token(connection, agent: str) -> str:
    credential, _ = AgentTokenRegistry(connection).issue_local_login(agent)
    connection.commit()
    return credential.token


def _json(**payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def test_http_api_auth_me_uses_token_registry(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        token = _token(connection, "trading-analyst")
        response = handle_api_request(
            connection,
            project_root=ROOT,
            method="GET",
            path="/auth/me",
            headers=_auth(token),
        )
        assert response.status == 200
        assert response.body["agent"]["agent_id"] == "trading-analyst"
        assert response.body["agent"]["domain"] == "trading"
        assert "goal.read" in response.body["capabilities"]
    finally:
        connection.close()


def test_http_api_goals_and_feature_requests_share_app_services(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        strategist_token = _token(connection, "trading-strategist")
        nexus_token = _token(connection, "control-router")

        goals = handle_api_request(
            connection,
            project_root=ROOT,
            method="GET",
            path="/goals",
            headers=_auth(strategist_token),
        )
        assert goals.status == 200
        assert {goal["domain"] for goal in goals.body["goals"]} == {"trading"}

        create = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/feature-requests",
            headers=_auth(strategist_token),
            body=_json(target_domain="software", goal_id="trade_success_quality", title="HTTP API missing endpoint coverage"),
        )
        assert create.status == 201
        request_id = create.body["feature_request"]["id"]
        assert create.body["feature_request"]["source_domain"] == "trading"

        route = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path=f"/feature-requests/{request_id}/route",
            headers=_auth(nexus_token),
            body=_json(target_domain="software"),
        )
        assert route.status == 200
        assert route.body["feature_request"]["status"] == "routed"

        listed = handle_api_request(
            connection,
            project_root=ROOT,
            method="GET",
            path="/feature-requests",
            headers=_auth(strategist_token),
        )
        assert listed.status == 200
        assert request_id in {item["id"] for item in listed.body["feature_requests"]}
    finally:
        connection.close()


def test_http_api_work_reviews_schedules_and_validation_routes_are_stable(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        nexus_token = _token(connection, "control-router")
        techlead_token = _token(connection, "software-techlead")

        schedules = handle_api_request(
            connection,
            project_root=ROOT,
            method="GET",
            path="/schedules",
            headers=_auth(nexus_token),
        )
        assert schedules.status == 200
        assert schedules.body["schedules"]

        reviews = handle_api_request(
            connection,
            project_root=ROOT,
            method="GET",
            path="/reviews",
            headers=_auth(techlead_token),
        )
        assert reviews.status == 200
        assert "review_queue" in reviews.body

        bad = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/feature-requests",
            headers=_auth(nexus_token),
            body=_json(goal_id="trade_success_quality"),
        )
        assert bad.status == 400
        assert "target_domain" in bad.body["error"]
    finally:
        connection.close()


def test_http_api_auth_middleware_denies_missing_token(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        response = handle_api_request(
            connection,
            project_root=ROOT,
            method="GET",
            path="/goals",
            headers={},
        )
        assert response.status == 401
        assert response.body["ok"] is False
    finally:
        connection.close()


def test_http_api_github_webhook_route_is_tokenless_and_signature_checked(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        body = b'{"zen":"api"}'
        secret = "http-api-secret"
        signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        response = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/webhooks/github",
            headers={
                "x-github-event": "ping",
                "x-github-delivery": "http-api-delivery",
                "x-hub-signature-256": signature,
            },
            body=body,
            webhook_secret=secret,
        )
        assert response.status == 202
        assert response.body["webhook"]["delivery_id"] == "http-api-delivery"
        assert response.body["webhook"]["signature_verified"] is True
    finally:
        connection.close()


def test_http_api_github_webhook_rejects_bad_signature_before_payload_processing(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        response = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/webhooks/github",
            headers={
                "x-github-event": "issues",
                "x-github-delivery": "http-api-bad-signature",
                "x-hub-signature-256": "sha256=not-valid",
            },
            body=b'{"broken":',
            webhook_secret="http-api-secret",
        )
        assert response.status == 400
        assert "signature" in response.body["error"]
        assert "JSON" not in response.body["error"]
        assert connection.execute("SELECT COUNT(*) AS count FROM github_webhook_events").fetchone()["count"] == 0
    finally:
        connection.close()


def test_http_api_github_webhook_rejects_missing_signature_and_delivery_without_secret_leak(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        secret = "http-api-super-secret"
        missing_signature = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/webhooks/github",
            headers={"x-github-event": "issues", "x-github-delivery": "http-api-no-signature"},
            body=b'{"repository":{"full_name":"openclaw/openclaw-nexus"}}',
            webhook_secret=secret,
        )
        assert missing_signature.status == 400
        assert "signature" in missing_signature.body["error"]
        assert secret not in json.dumps(missing_signature.body)

        body = b'{"repository":{"full_name":"openclaw/openclaw-nexus"}}'
        signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        missing_delivery = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/webhooks/github",
            headers={"x-github-event": "issues", "x-hub-signature-256": signature},
            body=body,
            webhook_secret=secret,
        )
        assert missing_delivery.status == 400
        assert "Delivery" in missing_delivery.body["error"]
        assert secret not in json.dumps(missing_delivery.body)
        assert connection.execute("SELECT COUNT(*) AS count FROM github_webhook_events").fetchone()["count"] == 0
    finally:
        connection.close()


def test_http_api_github_webhook_unknown_event_is_persisted_as_ignored(tmp_path: Path) -> None:
    connection = _db(tmp_path)
    try:
        body = b'{"repository":{"full_name":"openclaw/openclaw-nexus"}}'
        secret = "http-api-secret"
        signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        response = handle_api_request(
            connection,
            project_root=ROOT,
            method="POST",
            path="/webhooks/github",
            headers={
                "x-github-event": "unknown_event",
                "x-github-delivery": "http-api-unknown-event",
                "x-hub-signature-256": signature,
            },
            body=body,
            webhook_secret=secret,
        )
        assert response.status == 202
        assert response.body["webhook"]["processing_status"] == "ignored"
        row = connection.execute("SELECT processing_status, processed_at FROM github_webhook_events WHERE delivery_id = 'http-api-unknown-event'").fetchone()
        assert row["processing_status"] == "ignored"
        assert row["processed_at"] is not None
    finally:
        connection.close()
