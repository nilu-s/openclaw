"""Small stdlib HTTP client for Nexusctl CLI/API parity.

HTTP client work deliberately keeps the client framework-free and narrow: it provides
stable authentication headers, timeout handling, JSON parsing, health checks,
and the first remote command surface used by the CLI (`me`).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from nexusctl.domain.errors import AuthenticationError, NexusctlError, ValidationError
from nexusctl.interfaces.http.operational import HTTPClientSettings, validate_client_url


class APIClientError(NexusctlError):
    """Raised when the remote Nexusctl API cannot complete a request."""


@dataclass(frozen=True, slots=True)
class APIResponse:
    """Parsed JSON response returned by the Nexusctl API client."""

    status: int
    body: dict[str, Any]
    headers: Mapping[str, str]


class NexusctlAPIClient:
    """Minimal JSON-over-HTTP client used by remote-capable CLI commands."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float | None = None,
        read_retries: int | None = None,
        allow_insecure_remote: bool | None = None,
    ) -> None:
        settings = HTTPClientSettings.from_environment()
        clean_url = base_url.strip()
        if not clean_url:
            raise ValidationError("api url must not be empty")
        if not clean_url.endswith("/"):
            clean_url += "/"
        insecure_allowed = settings.allow_insecure_remote if allow_insecure_remote is None else allow_insecure_remote
        validate_client_url(clean_url, allow_insecure_remote=insecure_allowed)
        self.base_url = clean_url
        self.token = token
        self.timeout = float(settings.timeout_seconds if timeout is None else timeout)
        if self.timeout <= 0:
            raise ValidationError("api timeout must be greater than zero")
        self.read_retries = int(settings.read_retries if read_retries is None else read_retries)
        if self.read_retries < 0:
            raise ValidationError("api read retries must be at least zero")

    def health(self) -> dict[str, Any]:
        """Return the API health payload."""

        return self.request("GET", "healthz").body

    def auth_me(self) -> dict[str, Any]:
        """Return the authenticated remote subject and capabilities."""

        return self.request("GET", "auth/me", authenticated=True).body

    def feature_requests(self) -> dict[str, Any]:
        return self.request("GET", "feature-requests", authenticated=True).body

    def create_feature_request(self, *, target_domain: str, goal_id: str, title: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "feature-requests",
            authenticated=True,
            payload={"target_domain": target_domain, "goal_id": goal_id, "title": title},
        ).body

    def show_feature_request(self, request_id: str) -> dict[str, Any]:
        return self.request("GET", f"feature-requests/{request_id}", authenticated=True).body

    def route_feature_request(self, request_id: str, *, target_domain: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"feature-requests/{request_id}/route",
            authenticated=True,
            payload={"target_domain": target_domain},
        ).body

    def plan_work(self, feature_request_id: str) -> dict[str, Any]:
        return self.request("POST", "work/plan", authenticated=True, payload={"feature_request_id": feature_request_id}).body

    def assign_work(self, feature_request_id: str, *, builder: str, reviewer: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "work/assign",
            authenticated=True,
            payload={"feature_request_id": feature_request_id, "builder": builder, "reviewer": reviewer},
        ).body

    def show_work(self, work_id: str) -> dict[str, Any]:
        return self.request("GET", f"work/{work_id}", authenticated=True).body

    def start_work(self, work_id: str) -> dict[str, Any]:
        return self.request("POST", f"work/{work_id}/start", authenticated=True).body

    def policy_check(self, patch_id: str) -> dict[str, Any]:
        return self.request("POST", "policy/check", authenticated=True, payload={"patch_id": patch_id}).body

    def review_queue(self) -> dict[str, Any]:
        return self.request("GET", "reviews", authenticated=True).body

    def submit_review(self, item_id: str, *, verdict: str, notes: str = "") -> dict[str, Any]:
        return self.request("POST", "reviews", authenticated=True, payload={"id": item_id, "verdict": verdict, "notes": notes}).body

    def submit_acceptance(self, item_id: str, *, verdict: str, notes: str = "") -> dict[str, Any]:
        return self.request("POST", "acceptance", authenticated=True, payload={"id": item_id, "verdict": verdict, "notes": notes}).body

    def acceptance_status(self, item_id: str) -> dict[str, Any]:
        return self.request("GET", f"acceptance/{item_id}", authenticated=True).body

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        authenticated: bool = False,
    ) -> APIResponse:
        """Send one JSON request and parse the JSON response body."""

        headers = {"accept": "application/json"}
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(dict(payload), sort_keys=True).encode("utf-8")
            headers["content-type"] = "application/json"
        if authenticated:
            if not self.token:
                raise AuthenticationError("missing API token; pass --token or set NEXUSCTL_TOKEN")
            headers["authorization"] = f"Bearer {self.token}"

        request_method = method.upper()
        attempts = 1 + (self.read_retries if request_method == "GET" else 0)
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = Request(urljoin(self.base_url, path.lstrip("/")), data=data, headers=headers, method=request_method)
            try:
                with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - URL is user-configured CLI API endpoint.
                    body = self._decode_json(response.read())
                    return APIResponse(status=response.status, body=body, headers=dict(response.headers.items()))
            except HTTPError as exc:
                body = self._decode_json(exc.read())
                message = self._error_message(body) or f"HTTP {exc.code} from Nexusctl API"
                raise APIClientError(message) from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
        raise APIClientError(f"could not reach Nexusctl API at {self.base_url}: {last_error}")

    @staticmethod
    def _decode_json(raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIClientError(f"Nexusctl API returned invalid JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise APIClientError("Nexusctl API returned a non-object JSON payload")
        return body

    @staticmethod
    def _error_message(body: Mapping[str, Any]) -> str | None:
        error = body.get("error")
        if isinstance(error, str):
            return error
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str):
                return message
        return None
