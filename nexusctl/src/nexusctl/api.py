from __future__ import annotations

import json
import socket
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nexusctl.errors import NexusError
from nexusctl.models import Session


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: int = 5, auth_timeout_seconds: int = 8):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._auth_timeout_seconds = auth_timeout_seconds

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ApiClient":
        base_url = env.get("NEXUSCTL_API_BASE_URL", "http://127.0.0.1:8080")
        return cls(base_url=base_url)

    def auth(self, *, agent_token: str, domain: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent_token": agent_token}
        if domain:
            payload["domain"] = domain
        return self._request("POST", "/v1/nexus/auth", payload=payload, timeout=self._auth_timeout_seconds)

    def list_capabilities(self, *, session: Session, domain: str | None, status: str) -> dict[str, Any]:
        query: dict[str, str] = {"status": status, "project_id": session.project_id}
        if domain:
            query["domain"] = domain
        return self._request(
            "GET",
            "/v1/nexus/capabilities",
            query=query,
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def show_capability(self, *, session: Session, capability_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/nexus/capabilities/{capability_id}",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def set_status(self, *, session: Session, capability_id: str, to: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/nexus/capabilities/{capability_id}/status",
            payload={"to": to, "reason": reason},
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=False,
        )

    @staticmethod
    def _session_headers(session: Session) -> dict[str, str]:
        return {
            "X-Nexus-Session-Id": session.session_id,
            "X-Nexus-Agent-Id": session.agent_id,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        timeout: int,
        retry_once: bool = False,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        attempts = 2 if retry_once else 1
        for attempt in range(1, attempts + 1):
            try:
                body = json.dumps(payload).encode("utf-8") if payload is not None else None
                request_headers = {"Accept": "application/json"}
                if payload is not None:
                    request_headers["Content-Type"] = "application/json"
                if headers:
                    request_headers.update(headers)
                request = Request(url=url, data=body, method=method, headers=request_headers)
                with urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                    if not raw:
                        return {}
                    return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                raise self._map_http_error(exc)
            except (URLError, socket.timeout, TimeoutError, OSError):
                if attempt < attempts:
                    continue
                raise NexusError("NX-INFRA-001", "backend not reachable")
        raise NexusError("NX-INFRA-002", "unexpected infrastructure error")

    @staticmethod
    def _map_http_error(exc: HTTPError) -> NexusError:
        payload = {}
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        code = payload.get("error_code")
        message = payload.get("message") or f"http error {exc.code}"
        if code:
            return NexusError(code=code, message=message)
        if exc.code == 404:
            return NexusError("NX-NOTFOUND-001", message)
        if exc.code in {401, 403}:
            return NexusError("NX-PERM-001", message)
        if exc.code in {409, 412}:
            return NexusError("NX-PRECONDITION-003", message)
        if exc.code == 400:
            return NexusError("NX-VAL-001", message)
        if exc.code >= 500:
            return NexusError("NX-INFRA-002", message)
        return NexusError("NX-INFRA-002", message)
