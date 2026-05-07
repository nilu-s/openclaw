from __future__ import annotations

import pytest

import hmac
import hashlib
import json
import sqlite3

from nexusctl.backend.integrations.github_webhooks import verify_webhook_signature
from nexusctl.backend.storage import SessionContext, Storage, initialize_database, seed_mvp_data



pytestmark = pytest.mark.unit
TOKENS = {
    "nexus-01": "tok_nexus",
    "trading-strategist-01": "tok_trading",
    "sw-architect-01": "tok_architect",
    "sw-techlead-01": "tok_techlead",
}


def actor(agent_id: str, role: str, default_system_id: str = "software-domain", domain: str = "Software") -> SessionContext:
    return SessionContext(session_id=f"S-{agent_id}", agent_id=agent_id, role=role, default_system_id=default_system_id, domain=domain)


def _create_accepted_request(storage: Storage, suffix: str = "") -> str:
    created = storage.create_request(
        actor=actor("trading-strategist-01", "trading-strategist", "trading-system", "Trading"),
        objective=f"Implement deterministic risk limit checker {suffix}".strip(),
        missing_capability="Risk limit checker is missing",
        business_impact="Reduces exposure during volatile periods",
        expected_behavior="Orders are blocked when threshold is breached",
        acceptance_criteria=["Given a breached threshold, new orders are rejected."],
        risk_class="high",
        priority="P1",
        goal_ref="trading-goal://risk/limit-hard-stop",
    )
    request_id = created["request_id"]
    storage.transition_request(
        actor=actor("nexus-01", "nexus", "nexus", "Nexus"),
        request_id=request_id,
        to_status="accepted",
        reason="Accepted for software planning.",
    )
    return request_id


def test_direct_request_transition_cannot_bypass_software_work_gates(tmp_path):
    db_path = tmp_path / "nexus.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TOKENS)
    storage = Storage(db_path)
    request_id = _create_accepted_request(storage)

    try:
        storage.transition_request(
            actor=actor("nexus-01", "nexus", "nexus", "Nexus"),
            request_id=request_id,
            to_status="needs-planning",
            reason="Attempt direct transition into work-managed state.",
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "NX-PRECONDITION-001"
    else:
        raise AssertionError("direct request transition should not enter work-managed software states")


def test_webhook_signature_uses_raw_body_bytes_not_canonical_json():
    secret = "webhook-secret"
    raw_body = b'{"zen":"Keep it logically awesome.",   "hook_id":123}'
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    verify_webhook_signature(secret=secret, body=raw_body, signature_header=signature)

    canonical = json.dumps(json.loads(raw_body.decode("utf-8")), sort_keys=True).encode("utf-8")
    try:
        verify_webhook_signature(secret=secret, body=canonical, signature_header=signature)
    except Exception as exc:
        assert getattr(exc, "code", None) == "NX-GH-AUTH"
    else:
        raise AssertionError("canonicalized JSON must not validate against a raw-body signature")


def test_resource_pattern_limits_request_specific_work_scope(tmp_path):
    db_path = tmp_path / "nexus.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TOKENS)
    storage = Storage(db_path)
    allowed_request_id = _create_accepted_request(storage, "allowed")
    denied_request_id = _create_accepted_request(storage, "denied")

    scoped_actor = actor("scoped-agent-01", "custom-worker")
    conn = sqlite3.connect(db_path)
    try:
        for grant_id, scope in (("grant-1", "work.plan"), ("grant-2", "work.read")):
            conn.execute(
                """
                INSERT INTO agent_scope_grants(grant_id, agent_id, role, system_id, scope, resource_pattern, granted_by, created_at)
                VALUES (?, ?, NULL, 'software-domain', ?, ?, 'test', '2026-01-01T00:00:00Z')
                """,
                (grant_id, scoped_actor.agent_id, scope, allowed_request_id),
            )
        conn.commit()
    finally:
        conn.close()

    storage.plan_work(actor=scoped_actor, request_id=allowed_request_id, repo_id="trading-engine")
    try:
        storage.plan_work(actor=scoped_actor, request_id=denied_request_id, repo_id="trading-engine")
    except Exception as exc:
        assert getattr(exc, "code", None) == "NX-PERM-001"
    else:
        raise AssertionError("resource_pattern should block work.plan outside the granted request")
