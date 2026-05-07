"""Minimal stdlib HTTP server for Nexusctl blueprint workflow8 API ingress."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
from typing import Any

from nexusctl.interfaces.http.routes import handle_api_request
from nexusctl.domain.errors import ValidationError
from nexusctl.interfaces.http.operational import HTTPServerSettings, SessionStore, validate_server_binding
from nexusctl.interfaces.http.schemas import JsonResponse
from nexusctl.storage.sqlite.connection import connect_database


class NexusctlAPIHandler(BaseHTTPRequestHandler):
    """Serve the Nexusctl API without framework dependencies."""

    db_path: Path = Path("nexus.db")
    project_root: Path = Path(".")
    webhook_secret: str | None = None
    max_body_bytes: int = 1_048_576
    session_store: SessionStore = SessionStore()

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        self._dispatch("POST")

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - quiet test/server output
        return

    def _dispatch(self, method: str) -> None:
        try:
            length = int(self.headers.get("content-length", "0") or 0)
        except ValueError:
            self._send(400, {"ok": False, "error": "invalid Content-Length"})
            return
        if length > self.max_body_bytes:
            self._send(413, {"ok": False, "error": f"request body exceeds {self.max_body_bytes} bytes"})
            return
        body = self.rfile.read(length) if length else b""
        incoming_session_id = self.headers.get("x-nexusctl-session")
        if incoming_session_id:
            self.session_store.touch(incoming_session_id)
        connection = connect_database(self.db_path)
        try:
            response = handle_api_request(
                connection,
                project_root=self.project_root,
                method=method,
                path=self.path,
                headers={key: value for key, value in self.headers.items()},
                body=body,
                webhook_secret=self.webhook_secret,
            )
            headers = dict(response.headers or {})
            if response.status < 500 and "x-nexusctl-session" not in {key.lower() for key in headers}:
                headers["x-nexusctl-session"] = self.session_store.issue(transport="http")
            self._send(response.status, response.body, headers=headers)
        finally:
            connection.close()

    def _send(self, status: int, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> None:
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if not headers or "content-type" not in {key.lower() for key in headers}:
            self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)



def make_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    *,
    db_path: str | Path = "nexus.db",
    project_root: str | Path = ".",
    webhook_secret: str | None = None,
    max_body_bytes: int | None = None,
    tls_enabled: bool = False,
    allow_insecure_remote_bind: bool = False,
) -> HTTPServer:
    validate_server_binding(host, tls_enabled=tls_enabled, allow_insecure_remote=allow_insecure_remote_bind)
    handler = type("ConfiguredNexusctlAPIHandler", (NexusctlAPIHandler,), {})
    handler.db_path = Path(db_path)
    handler.project_root = Path(project_root)
    handler.webhook_secret = webhook_secret
    handler.max_body_bytes = int(max_body_bytes if max_body_bytes is not None else HTTPServerSettings().max_body_bytes)
    handler.session_store = SessionStore()
    return HTTPServer((host, int(port)), handler)


def main() -> int:
    """Run the stdlib HTTP API used by the Docker Compose runtime."""
    settings = HTTPServerSettings.from_environment()
    db_path = os.environ.get("NEXUSCTL_DB", "nexus.db")
    project_root = os.environ.get("NEXUSCTL_PROJECT_ROOT", ".")
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET") or None
    try:
        server = make_server(
            settings.host,
            settings.port,
            db_path=db_path,
            project_root=project_root,
            webhook_secret=secret,
            max_body_bytes=settings.max_body_bytes,
            tls_enabled=settings.tls_enabled,
            allow_insecure_remote_bind=settings.allow_insecure_remote_bind,
        )
    except ValidationError as exc:
        print(f"nexusctl-api configuration error: {exc}")
        return 2
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
