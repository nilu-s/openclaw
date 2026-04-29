from __future__ import annotations

import ipaddress
import json
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

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
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
    scheme = "http"
    if config.tls_cert_path and config.tls_key_path:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(config.tls_cert_path), keyfile=str(config.tls_key_path))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return RunningServer(
        base_url=f"{scheme}://{config.host}:{server.server_port}",
        _server=server,
        _thread=thread,
    )


def _make_handler(storage: Storage):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover
            return

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._read_json()
                path = urlparse(self.path).path
                if path == "/v1/nexus/auth":
                    token = payload.get("agent_token")
                    if not token:
                        raise NexusError("NX-VAL-002", "missing agent_token")
                    if "domain" in payload:
                        raise NexusError("NX-VAL-001", "domain override is not allowed")
                    result = storage.authenticate(agent_token=token)
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/capabilities/") and path.endswith("/status"):
                    capability_id = path.split("/")[4]
                    session = self._require_session()
                    to_status = payload.get("to")
                    reason = payload.get("reason")
                    if not isinstance(to_status, str) or not isinstance(reason, str):
                        raise NexusError("NX-VAL-001", "invalid status payload")
                    result = storage.set_status(
                        actor=session,
                        capability_id=capability_id,
                        to_status=to_status,
                        reason=reason,
                    )
                    self._send_json(200, result)
                    return

                if path == "/v1/nexus/handoffs":
                    session = self._require_session()
                    objective = payload.get("objective")
                    missing_capability = payload.get("missing_capability")
                    business_impact = payload.get("business_impact")
                    expected_behavior = payload.get("expected_behavior")
                    acceptance_criteria = payload.get("acceptance_criteria")
                    risk_class = payload.get("risk_class")
                    priority = payload.get("priority")
                    trading_goals_ref = payload.get("trading_goals_ref")
                    if (
                        not isinstance(objective, str)
                        or not isinstance(missing_capability, str)
                        or not isinstance(business_impact, str)
                        or not isinstance(expected_behavior, str)
                        or not isinstance(acceptance_criteria, list)
                        or not isinstance(risk_class, str)
                        or not isinstance(priority, str)
                        or not isinstance(trading_goals_ref, str)
                    ):
                        raise NexusError("NX-VAL-001", "invalid handoff payload")
                    result = storage.submit_handoff(
                        actor=session,
                        objective=objective,
                        missing_capability=missing_capability,
                        business_impact=business_impact,
                        expected_behavior=expected_behavior,
                        acceptance_criteria=acceptance_criteria,
                        risk_class=risk_class,
                        priority=priority,
                        trading_goals_ref=trading_goals_ref,
                    )
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/handoffs/") and path.endswith("/issue"):
                    session = self._require_session()
                    handoff_id = path.split("/")[4]
                    issue_ref = payload.get("issue_ref")
                    issue_number = payload.get("issue_number")
                    issue_url = payload.get("issue_url")
                    if not isinstance(issue_ref, str):
                        raise NexusError("NX-VAL-001", "invalid handoff issue payload")
                    if issue_number is not None and not isinstance(issue_number, int):
                        raise NexusError("NX-VAL-001", "invalid handoff issue payload")
                    if issue_url is not None and not isinstance(issue_url, str):
                        raise NexusError("NX-VAL-001", "invalid handoff issue payload")
                    result = storage.set_handoff_issue(
                        actor=session,
                        handoff_id=handoff_id,
                        issue_ref=issue_ref,
                        issue_number=issue_number,
                        issue_url=issue_url,
                    )
                    self._send_json(200, result)
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
                if path == "/healthz":
                    self._send_json(200, {"ok": True, "service": "nexusctl-server"})
                    return

                if path == "/v1/nexus/capabilities":
                    self._require_session()
                    query = parse_qs(parsed.query)
                    status = (query.get("status") or ["all"])[0]
                    if "domain" in query:
                        raise NexusError("NX-VAL-001", "domain filter is not allowed")
                    if status not in {"all", "planned", "available"}:
                        raise NexusError("NX-VAL-001", "invalid status filter")
                    result = storage.list_capabilities(status_filter=status)
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/capabilities/"):
                    self._require_session()
                    capability_id = path.split("/")[4]
                    result = storage.show_capability(capability_id)
                    self._send_json(200, result)
                    return

                if path == "/v1/nexus/handoffs":
                    self._require_session()
                    query = parse_qs(parsed.query)
                    status = (query.get("status") or ["submitted"])[0]
                    limit_raw = (query.get("limit") or ["100"])[0]
                    try:
                        limit = int(limit_raw)
                    except ValueError:
                        raise NexusError("NX-VAL-001", "invalid handoff limit")
                    result = storage.list_handoffs(status_filter=status, limit=limit)
                    self._send_json(200, result)
                    return

                raise NexusError("NX-NOTFOUND-001", "route not found")
            except NexusError as exc:
                self._send_error_json(exc)
            except Exception:
                self._send_error_json(NexusError("NX-INFRA-002", "unexpected backend error"))

        def _require_session(self):
            session_id = self.headers.get("X-Nexus-Session-Id")
            if not session_id:
                raise NexusError("NX-PRECONDITION-001", "missing session header")
            session = storage.validate_session(session_id)
            supplied_agent_id = self.headers.get("X-Nexus-Agent-Id")
            if supplied_agent_id and supplied_agent_id != session.agent_id:
                raise NexusError("NX-PERM-001", "agent header does not match active session")
            return session

        def _read_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise NexusError("NX-VAL-001", "invalid content length")
            if length <= 0:
                return {}
            if length > _MAX_JSON_BODY_BYTES:
                # Read and discard to keep HTTP framing stable for clients.
                self.rfile.read(length)
                raise NexusError("NX-VAL-001", "request payload too large")
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise NexusError("NX-VAL-001", "invalid json payload")

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
