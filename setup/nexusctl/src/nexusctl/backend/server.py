from __future__ import annotations

import ipaddress
import json
import os
import socket
import ssl
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from nexusctl.backend.storage import Storage
from nexusctl.errors import NexusError
from nexusctl.backend.integrations.github_webhooks import verify_webhook_signature


@dataclass
class BackendConfig:
    host: str
    port: int
    db_path: Path
    tls_cert_path: Path | None = None
    tls_key_path: Path | None = None
    allow_insecure_remote: bool = False


@dataclass
class RunningServer:
    base_url: str
    _server: ThreadingHTTPServer
    _thread: threading.Thread

    def stop(self, *, timeout_seconds: float = 2.0) -> None:
        """Stop the test/development server without hiding leaked threads.

        ThreadingHTTPServer.shutdown() is normally quick, but a stuck handler or
        interpreter edge case can otherwise make pytest hang after all assertions
        have passed. Run shutdown itself behind a bounded join, always close the
        listening socket, and fail loudly if either shutdown or serve_forever does
        not terminate in time. Handler threads are daemonized by start_server and
        must not block process exit.
        """
        shutdown_error: list[BaseException] = []

        def _shutdown() -> None:
            try:
                self._server.shutdown()
            except BaseException as exc:  # pragma: no cover - defensive teardown path
                shutdown_error.append(exc)

        shutdown_thread = threading.Thread(target=_shutdown, name="nexusctl-server-shutdown", daemon=True)
        shutdown_thread.start()
        try:
            shutdown_thread.join(timeout=timeout_seconds)
            if shutdown_thread.is_alive():
                raise RuntimeError("nexusctl test server shutdown did not return")
            if shutdown_error:
                raise RuntimeError("nexusctl test server shutdown failed") from shutdown_error[0]

            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                raise RuntimeError("nexusctl test server did not stop cleanly")
        finally:
            self._server.server_close()


_MAX_JSON_BODY_BYTES = 64 * 1024


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        resolved: list[object] = []
        for item in infos:
            addr = item[4][0]
            try:
                resolved.append(ipaddress.ip_address(addr))
            except ValueError:
                continue
        return bool(resolved) and all(address.is_loopback for address in resolved)


def start_server(config: BackendConfig) -> RunningServer:
    if not _is_loopback_host(config.host):
        has_tls = bool(config.tls_cert_path and config.tls_key_path)
        if not has_tls and not config.allow_insecure_remote:
            raise NexusError(
                "NX-VAL-001",
                "refusing non-loopback bind without TLS; provide TLS cert+key or --allow-insecure-remote",
            )
    if bool(config.tls_cert_path) ^ bool(config.tls_key_path):
        raise NexusError("NX-VAL-001", "both TLS cert and TLS key must be provided together")

    storage = Storage(config.db_path)
    handler = _make_handler(storage)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    server.daemon_threads = True
    server.block_on_close = False
    scheme = "http"
    if config.tls_cert_path and config.tls_key_path:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(config.tls_cert_path), keyfile=str(config.tls_key_path))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return RunningServer(base_url=f"{scheme}://{config.host}:{server.server_port}", _server=server, _thread=thread)


def _make_handler(storage: Storage):
    class Handler(BaseHTTPRequestHandler):
        # Keep HTTP/1.0 semantics for the simple embedded server and explicitly
        # close every response. This prevents urllib clients from leaving idle
        # keep-alive sockets around in integration tests.
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover
            return

        def do_POST(self) -> None:  # noqa: N802
            try:
                raw_body, payload = self._read_json_with_raw()
                path = urlparse(self.path).path

                if path == "/v1/nexus/auth":
                    token = payload.get("agent_token")
                    if not token:
                        raise NexusError("NX-VAL-002", "missing agent_token")
                    if "domain" in payload:
                        raise NexusError("NX-VAL-001", "domain override is not allowed")
                    self._send_json(200, storage.authenticate(agent_token=token))
                    return

                if path == "/v1/nexus/goals":
                    session = self._require_session()
                    required = ["goal_id", "title", "objective", "risk_class", "priority"]
                    if any(not isinstance(payload.get(key), str) for key in required):
                        raise NexusError("NX-VAL-001", "invalid goal payload")
                    result = storage.create_goal(
                        actor=session,
                        goal_id=payload["goal_id"],
                        system_id=payload.get("system_id"),
                        title=payload["title"],
                        objective=payload["objective"],
                        success_metrics=payload.get("success_metrics"),
                        constraints=payload.get("constraints"),
                        risk_class=payload["risk_class"],
                        priority=payload["priority"],
                        owner_agent_id=payload.get("owner_agent_id"),
                        status=payload.get("status", "proposed"),
                        parent_goal_id=payload.get("parent_goal_id"),
                    )
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/goals/") and path.endswith("/status"):
                    session = self._require_session()
                    goal_id = path.split("/")[4]
                    to_status = payload.get("to")
                    reason = payload.get("reason")
                    if not isinstance(to_status, str) or not isinstance(reason, str):
                        raise NexusError("NX-VAL-001", "invalid goal status payload")
                    result = storage.update_goal_status(actor=session, goal_id=goal_id, to_status=to_status, reason=reason)
                    self._send_json(200, result)
                    return


                if path == "/v1/nexus/scopes/leases":
                    session = self._require_session()
                    agent_id = payload.get("agent_id")
                    scope = payload.get("scope")
                    reason = payload.get("reason")
                    ttl = payload.get("ttl_minutes", 120)
                    if not isinstance(agent_id, str) or not isinstance(scope, str) or not isinstance(reason, str) or not isinstance(ttl, int):
                        raise NexusError("NX-VAL-001", "invalid scope lease payload")
                    self._send_json(200, storage.create_scope_lease(
                        actor=session, agent_id=agent_id, scope=scope, system_id=payload.get("system_id", "*"),
                        resource_pattern=payload.get("resource_pattern", "*"), request_id=payload.get("request_id"),
                        reason=reason, ttl_minutes=ttl, approved_by=payload.get("approved_by"),
                    ))
                    return

                if path.startswith("/v1/nexus/scopes/leases/") and path.endswith("/revoke"):
                    session = self._require_session()
                    lease_id = path.split("/")[5]
                    reason = payload.get("reason")
                    if not isinstance(reason, str):
                        raise NexusError("NX-VAL-001", "invalid revoke payload")
                    self._send_json(200, storage.revoke_scope_lease(actor=session, lease_id=lease_id, reason=reason))
                    return

                if path == "/v1/nexus/db/backup":
                    session = self._require_session()
                    backup_path = payload.get("backup_path")
                    if backup_path is not None and not isinstance(backup_path, str):
                        raise NexusError("NX-VAL-001", "invalid backup path")
                    self._send_json(200, storage.backup_database(actor=session, backup_path=backup_path))
                    return

                if path == "/v1/nexus/db/restore-check":
                    session = self._require_session()
                    backup_path = payload.get("backup_path")
                    if not isinstance(backup_path, str):
                        raise NexusError("NX-VAL-001", "invalid backup path")
                    self._send_json(200, storage.restore_database_check(actor=session, backup_path=backup_path))
                    return

                if path.startswith("/v1/nexus/runtime-tools/") and path.endswith("/guardrail"):
                    session = self._require_session()
                    tool_id = path.split("/")[4]
                    self._send_json(200, storage.evaluate_tool_guardrail(
                        actor=session, tool_id=tool_id, request_id=payload.get("request_id"),
                        side_effect_level=payload.get("side_effect_level"), human_approved=bool(payload.get("human_approved", False)),
                    ))
                    return

                if path.startswith("/v1/nexus/capabilities/") and path.endswith("/status"):
                    capability_id = path.split("/")[4]
                    session = self._require_session()
                    to_status = payload.get("to")
                    reason = payload.get("reason")
                    if not isinstance(to_status, str) or not isinstance(reason, str):
                        raise NexusError("NX-VAL-001", "invalid status payload")
                    result = storage.set_status(actor=session, capability_id=capability_id, to_status=to_status, reason=reason)
                    self._send_json(200, result)
                    return

                if path == "/v1/nexus/requests":
                    session = self._require_session()
                    objective = payload.get("objective")
                    missing_capability = payload.get("missing_capability")
                    business_impact = payload.get("business_impact")
                    expected_behavior = payload.get("expected_behavior")
                    acceptance_criteria = payload.get("acceptance_criteria")
                    risk_class = payload.get("risk_class")
                    priority = payload.get("priority")
                    goal_ref = payload.get("goal_ref")
                    if (
                        not isinstance(objective, str)
                        or not isinstance(missing_capability, str)
                        or not isinstance(business_impact, str)
                        or not isinstance(expected_behavior, str)
                        or not isinstance(acceptance_criteria, list)
                        or not isinstance(risk_class, str)
                        or not isinstance(priority, str)
                        or not isinstance(goal_ref, str)
                    ):
                        raise NexusError("NX-VAL-001", "invalid request payload")
                    result = storage.create_request(
                        actor=session,
                        objective=objective,
                        missing_capability=missing_capability,
                        business_impact=business_impact,
                        expected_behavior=expected_behavior,
                        acceptance_criteria=acceptance_criteria,
                        risk_class=risk_class,
                        priority=priority,
                        goal_ref=goal_ref,
                    )
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/github/issues/") and path.endswith("/sync"):
                    session = self._require_session()
                    request_id = path.split("/")[5]
                    self._send_json(200, storage.sync_github_issue(actor=session, request_id=request_id))
                    return

                if path.startswith("/v1/nexus/github/issues/"):
                    session = self._require_session()
                    request_id = path.split("/")[5]
                    labels = payload.get("labels") or []
                    assignees = payload.get("assignees") or []
                    if not isinstance(labels, list) or not isinstance(assignees, list):
                        raise NexusError("NX-VAL-001", "invalid GitHub issue payload")
                    self._send_json(200, storage.create_github_issue(
                        actor=session,
                        request_id=request_id,
                        title=payload.get("title"),
                        labels=[str(item) for item in labels],
                        assignees=[str(item) for item in assignees],
                        dry_run=bool(payload.get("dry_run", False)),
                    ))
                    return

                if path.startswith("/v1/nexus/github/pull-requests/") and path.endswith("/link"):
                    session = self._require_session()
                    request_id = path.split("/")[5]
                    url = payload.get("url")
                    if not isinstance(url, str):
                        raise NexusError("NX-VAL-001", "invalid GitHub PR link payload")
                    self._send_json(200, storage.link_github_pr(actor=session, request_id=request_id, url=url))
                    return

                if path.startswith("/v1/nexus/github/pull-requests/") and path.endswith("/sync"):
                    session = self._require_session()
                    request_id = path.split("/")[5]
                    self._send_json(200, storage.sync_github_pr(actor=session, request_id=request_id))
                    return

                if path.startswith("/v1/nexus/github/sync/"):
                    session = self._require_session()
                    request_id = path.split("/")[5]
                    self._send_json(200, storage.sync_github(actor=session, request_id=request_id))
                    return

                if path == "/v1/nexus/github/repositories/sync":
                    session = self._require_session()
                    self._send_json(200, storage.sync_github_repositories(actor=session))
                    return

                if path == "/v1/nexus/agents/rotate-token":
                    session = self._require_session()
                    agent_id = payload.get("agent_id")
                    new_token = payload.get("new_token")
                    if not isinstance(agent_id, str) or (new_token is not None and not isinstance(new_token, str)):
                        raise NexusError("NX-VAL-001", "invalid rotate-token payload")
                    self._send_json(200, storage.rotate_agent_token(actor=session, target_agent_id=agent_id, new_token=new_token))
                    return

                if path == "/v1/nexus/github/webhooks/process":
                    session = self._require_session()
                    limit = payload.get("limit", 25)
                    if not isinstance(limit, int):
                        raise NexusError("NX-VAL-001", "invalid webhook processing limit")
                    self._send_json(200, storage.process_queued_github_events(actor=session, limit=limit))
                    return

                if path == "/v1/github/webhooks":
                    secret = os.environ.get("NEXUS_GITHUB_WEBHOOK_SECRET", "")
                    verify_webhook_signature(secret=secret, body=raw_body, signature_header=self.headers.get("X-Hub-Signature-256"))
                    delivery_id = self.headers.get("X-GitHub-Delivery") or ""
                    event_type = self.headers.get("X-GitHub-Event") or ""
                    if not delivery_id or not event_type:
                        raise NexusError("NX-GH-VALIDATION", "missing GitHub webhook headers")
                    self._send_json(202, storage.record_github_event(delivery_id=delivery_id, event_type=event_type, payload=payload))
                    return

                if path.startswith("/v1/nexus/requests/") and path.endswith("/transition"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    to_status = payload.get("to")
                    reason = payload.get("reason")
                    if not isinstance(to_status, str) or not isinstance(reason, str):
                        raise NexusError("NX-VAL-001", "invalid request transition payload")
                    result = storage.transition_request(actor=session, request_id=request_id, to_status=to_status, reason=reason)
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/work/") and path.endswith("/plan"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    repo_id = payload.get("repo_id")
                    if not isinstance(repo_id, str):
                        raise NexusError("NX-VAL-001", "invalid work plan payload")
                    result = storage.plan_work(
                        actor=session,
                        request_id=request_id,
                        repo_id=repo_id,
                        branch=payload.get("branch"),
                        assigned_agent_id=payload.get("assigned_agent_id"),
                        reviewer_agent_id=payload.get("reviewer_agent_id"),
                        sanitized_summary=payload.get("sanitized_summary"),
                    )
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/work/") and path.endswith("/implementation-context"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    implementation_context = payload.get("implementation_context")
                    if not isinstance(implementation_context, dict):
                        raise NexusError("NX-VAL-001", "invalid implementation context payload")
                    self._send_json(200, storage.set_implementation_context(actor=session, request_id=request_id, implementation_context=implementation_context))
                    return

                if path.startswith("/v1/nexus/work/") and path.endswith("/approve-plan"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    self._send_json(200, storage.approve_work_plan(actor=session, request_id=request_id))
                    return

                if path.startswith("/v1/nexus/work/") and path.endswith("/assign"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    agent_id = payload.get("agent_id")
                    if not isinstance(agent_id, str):
                        raise NexusError("NX-VAL-001", "invalid work assign payload")
                    self._send_json(200, storage.assign_work(actor=session, request_id=request_id, agent_id=agent_id))
                    return

                if path.startswith("/v1/nexus/work/") and path.endswith("/transition"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    to_status = payload.get("to")
                    reason = payload.get("reason")
                    if not isinstance(to_status, str) or not isinstance(reason, str):
                        raise NexusError("NX-VAL-001", "invalid work transition payload")
                    approved_by = payload.get("approved_by")
                    if approved_by is not None and not isinstance(approved_by, str):
                        raise NexusError("NX-VAL-001", "invalid manual override approver")
                    self._send_json(200, storage.transition_work(actor=session, request_id=request_id, to_status=to_status, reason=reason, override=bool(payload.get("override", False)), approved_by=approved_by))
                    return

                if path.startswith("/v1/nexus/work/") and path.endswith("/evidence"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    kind = payload.get("kind")
                    summary = payload.get("summary")
                    ref = payload.get("ref")
                    if not isinstance(kind, str) or not isinstance(summary, str) or (ref is not None and not isinstance(ref, str)):
                        raise NexusError("NX-VAL-001", "invalid work evidence payload")
                    self._send_json(200, storage.submit_work_evidence(actor=session, request_id=request_id, kind=kind, ref=ref, summary=summary))
                    return

                if path.startswith("/v1/nexus/reviews/"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    verdict = payload.get("verdict")
                    summary = payload.get("summary")
                    if not isinstance(verdict, str) or not isinstance(summary, str):
                        raise NexusError("NX-VAL-001", "invalid review payload")
                    self._send_json(200, storage.submit_review(actor=session, request_id=request_id, verdict=verdict, summary=summary))
                    return

                raise NexusError("NX-NOTFOUND-001", "route not found")
            except NexusError as exc:
                self._send_error_json(exc)
            except Exception:
                self._send_error_json(NexusError("NX-INFRA-002", "unexpected backend error"))

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/healthz":
                    self._send_json(200, {"ok": True, "service": "nexusctl-server"})
                    return

                if path == "/v1/nexus/context":
                    session = self._require_session()
                    self._send_json(200, storage.get_context(actor=session, request_limit=20))
                    return

                if path == "/v1/nexus/systems":
                    session = self._require_session()
                    status = (query.get("status") or ["all"])[0]
                    self._send_json(200, storage.list_systems(actor=session, status_filter=status))
                    return

                if path.startswith("/v1/nexus/systems/"):
                    session = self._require_session()
                    system_id = path.split("/")[4]
                    self._send_json(200, storage.show_system(actor=session, system_id=system_id))
                    return

                if path == "/v1/nexus/goals":
                    session = self._require_session()
                    status = (query.get("status") or ["all"])[0]
                    system_id = (query.get("system_id") or [None])[0]
                    limit = self._parse_int_query(query, "limit", 100)
                    self._send_json(200, storage.list_goals(actor=session, system_id=system_id, status_filter=status, limit=limit))
                    return

                if path.startswith("/v1/nexus/goals/"):
                    session = self._require_session()
                    goal_id = path.split("/")[4]
                    self._send_json(200, storage.show_goal(actor=session, goal_id=goal_id))
                    return

                if path == "/v1/nexus/scopes":
                    session = self._require_session()
                    agent_id = (query.get("agent_id") or [None])[0]
                    self._send_json(200, storage.list_scopes(actor=session, target_agent_id=agent_id))
                    return


                if path == "/v1/nexus/scopes/leases":
                    session = self._require_session()
                    agent_id = (query.get("agent_id") or [None])[0]
                    active_only = (query.get("active") or ["1"])[0] != "0"
                    self._send_json(200, storage.list_scope_leases(actor=session, agent_id=agent_id, active_only=active_only))
                    return

                if path == "/v1/nexus/events":
                    session = self._require_session()
                    target_type = (query.get("target_type") or [None])[0]
                    target_id = (query.get("target_id") or [None])[0]
                    limit = self._parse_int_query(query, "limit", 100)
                    self._send_json(200, storage.list_event_log(actor=session, target_type=target_type, target_id=target_id, limit=limit))
                    return

                if path == "/v1/nexus/scopes/effective":
                    session = self._require_session()
                    self._send_json(200, storage.effective_scopes(actor=session))
                    return

                if path == "/v1/nexus/runtime-tools":
                    session = self._require_session()
                    status = (query.get("status") or ["all"])[0]
                    system_id = (query.get("system_id") or [None])[0]
                    self._send_json(200, storage.list_runtime_tools(actor=session, system_id=system_id, status_filter=status))
                    return

                if path.startswith("/v1/nexus/runtime-tools/"):
                    session = self._require_session()
                    tool_id = path.split("/", 4)[4]
                    self._send_json(200, storage.show_runtime_tool(actor=session, tool_id=tool_id))
                    return

                if path == "/v1/nexus/capabilities":
                    session = self._require_session()
                    status = (query.get("status") or ["all"])[0]
                    system_id = (query.get("system_id") or [None])[0]
                    if "domain" in query:
                        raise NexusError("NX-VAL-001", "domain filter is not allowed")
                    result = storage.list_capabilities(actor=session, status_filter=status, system_id=system_id)
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/capabilities/"):
                    session = self._require_session()
                    capability_id = path.split("/")[4]
                    result = storage.show_capability(capability_id, actor=session)
                    self._send_json(200, result)
                    return

                if path == "/v1/nexus/requests":
                    session = self._require_session()
                    status = (query.get("status") or ["submitted"])[0]
                    limit = self._parse_int_query(query, "limit", 100)
                    result = storage.list_requests(actor=session, status_filter=status, limit=limit)
                    self._send_json(200, result)
                    return


                if path.startswith("/v1/nexus/requests/"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    result = storage.show_request(actor=session, request_id=request_id)
                    self._send_json(200, result)
                    return


                if path.startswith("/v1/nexus/github/status/"):
                    session = self._require_session()
                    request_id = path.split("/")[5]
                    self._send_json(200, storage.github_status(actor=session, request_id=request_id))
                    return

                if path == "/v1/nexus/github/alerts":
                    session = self._require_session()
                    unresolved = query.get("unresolved", ["1"])[0] != "0"
                    limit = int(query.get("limit", ["50"])[0])
                    self._send_json(200, storage.list_github_alerts(actor=session, unresolved_only=unresolved, limit=limit))
                    return

                if path == "/v1/nexus/github/repositories":
                    session = self._require_session()
                    self._send_json(200, storage.list_github_repositories(actor=session))
                    return

                if path == "/v1/nexus/repos":
                    session = self._require_session()
                    assigned = (query.get("assigned") or ["0"])[0].lower() in {"1", "true", "yes", "on"}
                    self._send_json(200, storage.list_repositories(actor=session, assigned_only=assigned))
                    return

                if path.startswith("/v1/nexus/repos/"):
                    session = self._require_session()
                    repo_id = path.split("/")[4]
                    self._send_json(200, storage.show_repository(actor=session, repo_id=repo_id))
                    return

                if path == "/v1/nexus/work":
                    session = self._require_session()
                    status = (query.get("status") or ["all"])[0]
                    limit = self._parse_int_query(query, "limit", 100)
                    self._send_json(200, storage.list_work(actor=session, status_filter=status, limit=limit))
                    return

                if path.startswith("/v1/nexus/work/"):
                    session = self._require_session()
                    request_id = path.split("/")[4]
                    self._send_json(200, storage.show_work(actor=session, request_id=request_id))
                    return

                if path == "/v1/nexus/reviews":
                    session = self._require_session()
                    status = (query.get("status") or ["in-review"])[0]
                    limit = self._parse_int_query(query, "limit", 100)
                    self._send_json(200, storage.list_reviews(actor=session, status_filter=status, limit=limit))
                    return

                raise NexusError("NX-NOTFOUND-001", "route not found")
            except NexusError as exc:
                self._send_error_json(exc)
            except Exception:
                self._send_error_json(NexusError("NX-INFRA-002", "unexpected backend error"))

        @staticmethod
        def _parse_int_query(query: dict[str, list[str]], name: str, default: int) -> int:
            raw = (query.get(name) or [str(default)])[0]
            try:
                return int(raw)
            except ValueError:
                raise NexusError("NX-VAL-001", f"invalid {name}")

        def _require_session(self):
            session_id = self.headers.get("X-Nexus-Session-Id")
            if not session_id:
                raise NexusError("NX-PRECONDITION-001", "missing session header")
            session = storage.validate_session(session_id)
            supplied_agent_id = self.headers.get("X-Nexus-Agent-Id")
            if supplied_agent_id and supplied_agent_id != session.agent_id:
                raise NexusError("NX-PERM-001", "agent header does not match active session")
            return session

        def _read_json_with_raw(self) -> tuple[bytes, dict[str, Any]]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise NexusError("NX-VAL-001", "invalid content length")
            if length <= 0:
                return b"", {}
            if length > _MAX_JSON_BODY_BYTES:
                # Do not drain large request bodies in tests or in the embedded
                # server. Mark the connection for close and reject immediately so
                # a slow or oversized client cannot pin a handler thread.
                self.close_connection = True
                raise NexusError("NX-VAL-001", "request payload too large")
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise NexusError("NX-VAL-001", "invalid json payload")
            if not isinstance(payload, dict):
                raise NexusError("NX-VAL-001", "json payload must be an object")
            return raw, payload

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.close_connection = True
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            try:
                self.wfile.flush()
            except OSError:  # pragma: no cover - client disconnected during error response
                pass

        def _send_error_json(self, error: NexusError) -> None:
            status_code = _http_status_for_error(error.code)
            self._send_json(status_code, {"error_code": error.code, "message": error.message})

    return Handler


def _http_status_for_error(code: str) -> int:
    if code.startswith("NX-VAL-"):
        return 400
    if code.startswith("NX-NOTFOUND-"):
        return 404
    if code.startswith("NX-PERM-"):
        return 403
    if code.startswith("NX-PRECONDITION-"):
        return 412
    return 500
