from __future__ import annotations

import json
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


@dataclass
class RunningServer:
    base_url: str
    _server: ThreadingHTTPServer
    _thread: threading.Thread

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()


def start_server(config: BackendConfig) -> RunningServer:
    storage = Storage(config.db_path)
    handler = _make_handler(storage)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return RunningServer(
        base_url=f"http://{config.host}:{server.server_port}",
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
                    result = storage.authenticate(agent_token=token, domain=payload.get("domain"))
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

                raise NexusError("NX-NOTFOUND-001", "route not found")
            except NexusError as exc:
                self._send_error_json(exc)
            except Exception:
                self._send_error_json(NexusError("NX-INFRA-002", "unexpected backend error"))

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/v1/nexus/capabilities":
                    self._require_session()
                    query = parse_qs(parsed.query)
                    status = (query.get("status") or ["all"])[0]
                    domain = (query.get("domain") or [None])[0]
                    if status not in {"all", "planned", "available"}:
                        raise NexusError("NX-VAL-001", "invalid status filter")
                    result = storage.list_capabilities(status_filter=status, domain=domain)
                    self._send_json(200, result)
                    return

                if path.startswith("/v1/nexus/capabilities/"):
                    self._require_session()
                    capability_id = path.split("/")[4]
                    result = storage.show_capability(capability_id)
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
            return storage.validate_session(session_id)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
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
