from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from nexusctl.errors import NexusError
from nexusctl.models import Session


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return False
        addresses = []
        for info in infos:
            value = info[4][0]
            try:
                addresses.append(ipaddress.ip_address(value))
            except ValueError:
                continue
        return bool(addresses) and all(addr.is_loopback for addr in addresses)


def _float_from_env(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise NexusError("NX-VAL-001", f"{name} must be a number of seconds")
    if value <= 0:
        raise NexusError("NX-VAL-001", f"{name} must be greater than zero")
    return value


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0, auth_timeout_seconds: float = 8.0):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._auth_timeout_seconds = auth_timeout_seconds

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ApiClient":
        base_url = env.get("NEXUSCTL_API_BASE_URL", "http://127.0.0.1:8080")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise NexusError("NX-VAL-001", "NEXUSCTL_API_BASE_URL must start with http:// or https://")
        allow_insecure_remote = _is_truthy(env.get("NEXUSCTL_ALLOW_INSECURE_REMOTE"))
        if parsed.scheme == "http" and not _is_loopback_hostname(parsed.hostname) and not allow_insecure_remote:
            raise NexusError("NX-VAL-001", "insecure http base URL is only allowed for loopback hosts")
        return cls(
            base_url=base_url,
            timeout_seconds=_float_from_env(env, "NEXUSCTL_TIMEOUT_SECONDS", 5.0),
            auth_timeout_seconds=_float_from_env(env, "NEXUSCTL_AUTH_TIMEOUT_SECONDS", 8.0),
        )

    def auth(self, *, agent_token: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent_token": agent_token}
        return self._request("POST", "/v1/nexus/auth", payload=payload, timeout=self._auth_timeout_seconds)

    def rotate_agent_token(self, *, session: Session, agent_id: str, new_token: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent_id": agent_id}
        if new_token:
            payload["new_token"] = new_token
        return self._request("POST", "/v1/nexus/agents/rotate-token", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def list_systems(self, *, session: Session, status: str = "all") -> dict[str, Any]:
        return self._request(
            "GET",
            "/v1/nexus/systems",
            query={"status": status},
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def show_system(self, *, session: Session, system_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/nexus/systems/{system_id}",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def list_goals(self, *, session: Session, system_id: str | None = None, status: str = "all", limit: int = 100) -> dict[str, Any]:
        query = {"status": status, "limit": str(limit)}
        if system_id:
            query["system_id"] = system_id
        return self._request(
            "GET",
            "/v1/nexus/goals",
            query=query,
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def show_goal(self, *, session: Session, goal_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/nexus/goals/{goal_id}",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def create_goal(
        self,
        *,
        session: Session,
        goal_id: str,
        system_id: str | None,
        title: str,
        objective: str,
        success_metrics: list[str],
        constraints: list[str],
        risk_class: str,
        priority: str,
        owner_agent_id: str | None,
        status: str = "proposed",
        parent_goal_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "goal_id": goal_id,
            "title": title,
            "objective": objective,
            "success_metrics": success_metrics,
            "constraints": constraints,
            "risk_class": risk_class,
            "priority": priority,
            "status": status,
        }
        if system_id:
            payload["system_id"] = system_id
        if owner_agent_id:
            payload["owner_agent_id"] = owner_agent_id
        if parent_goal_id:
            payload["parent_goal_id"] = parent_goal_id
        return self._request(
            "POST",
            "/v1/nexus/goals",
            payload=payload,
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=False,
        )

    def update_goal_status(self, *, session: Session, goal_id: str, to: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/nexus/goals/{goal_id}/status",
            payload={"to": to, "reason": reason},
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=False,
        )

    def list_scopes(self, *, session: Session, agent_id: str | None = None) -> dict[str, Any]:
        query = {"agent_id": agent_id} if agent_id else None
        return self._request(
            "GET",
            "/v1/nexus/scopes",
            query=query,
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def effective_scopes(self, *, session: Session) -> dict[str, Any]:
        return self._request(
            "GET",
            "/v1/nexus/scopes/effective",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )


    def create_scope_lease(self, *, session: Session, agent_id: str, scope: str, system_id: str = "*", resource_pattern: str = "*", request_id: str | None = None, reason: str, ttl_minutes: int = 120, approved_by: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent_id": agent_id, "scope": scope, "system_id": system_id, "resource_pattern": resource_pattern, "reason": reason, "ttl_minutes": ttl_minutes}
        if request_id:
            payload["request_id"] = request_id
        if approved_by:
            payload["approved_by"] = approved_by
        return self._request("POST", "/v1/nexus/scopes/leases", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def list_scope_leases(self, *, session: Session, agent_id: str | None = None, active_only: bool = True) -> dict[str, Any]:
        query = {"active": "1" if active_only else "0"}
        if agent_id:
            query["agent_id"] = agent_id
        return self._request("GET", "/v1/nexus/scopes/leases", query=query, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def revoke_scope_lease(self, *, session: Session, lease_id: str, reason: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/scopes/leases/{lease_id}/revoke", payload={"reason": reason}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def event_log(self, *, session: Session, target_type: str | None = None, target_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        query = {"limit": str(limit)}
        if target_type:
            query["target_type"] = target_type
        if target_id:
            query["target_id"] = target_id
        return self._request("GET", "/v1/nexus/events", query=query, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def db_backup(self, *, session: Session, backup_path: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if backup_path:
            payload["backup_path"] = backup_path
        return self._request("POST", "/v1/nexus/db/backup", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def db_restore_check(self, *, session: Session, backup_path: str) -> dict[str, Any]:
        return self._request("POST", "/v1/nexus/db/restore-check", payload={"backup_path": backup_path}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def runtime_tool_check(self, *, session: Session, tool_id: str, request_id: str | None = None, side_effect_level: str | None = None, human_approved: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"human_approved": human_approved}
        if request_id:
            payload["request_id"] = request_id
        if side_effect_level:
            payload["side_effect_level"] = side_effect_level
        return self._request("POST", f"/v1/nexus/runtime-tools/{tool_id}/guardrail", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def list_runtime_tools(self, *, session: Session, system_id: str | None = None, status: str = "all") -> dict[str, Any]:
        query = {"status": status}
        if system_id:
            query["system_id"] = system_id
        return self._request(
            "GET",
            "/v1/nexus/runtime-tools",
            query=query,
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def show_runtime_tool(self, *, session: Session, tool_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/nexus/runtime-tools/{tool_id}",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def list_repos(self, *, session: Session, assigned: bool = False) -> dict[str, Any]:
        query = {"assigned": "1"} if assigned else None
        return self._request("GET", "/v1/nexus/repos", query=query, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def show_repo(self, *, session: Session, repo_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/nexus/repos/{repo_id}", headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def list_work(self, *, session: Session, status: str = "all", limit: int = 100) -> dict[str, Any]:
        return self._request("GET", "/v1/nexus/work", query={"status": status, "limit": str(limit)}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def show_work(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/nexus/work/{request_id}", headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def plan_work(self, *, session: Session, request_id: str, repo_id: str, branch: str | None = None, assigned_agent_id: str | None = None, reviewer_agent_id: str | None = None, sanitized_summary: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"repo_id": repo_id}
        if branch:
            payload["branch"] = branch
        if assigned_agent_id:
            payload["assigned_agent_id"] = assigned_agent_id
        if reviewer_agent_id:
            payload["reviewer_agent_id"] = reviewer_agent_id
        if sanitized_summary:
            payload["sanitized_summary"] = sanitized_summary
        return self._request("POST", f"/v1/nexus/work/{request_id}/plan", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def assign_work(self, *, session: Session, request_id: str, agent_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/work/{request_id}/assign", payload={"agent_id": agent_id}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def transition_work(self, *, session: Session, request_id: str, to: str, reason: str, override: bool = False, approved_by: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"to": to, "reason": reason, "override": override}
        if approved_by:
            payload["approved_by"] = approved_by
        return self._request("POST", f"/v1/nexus/work/{request_id}/transition", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def submit_work_evidence(self, *, session: Session, request_id: str, kind: str, ref: str | None, summary: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": kind, "summary": summary}
        if ref:
            payload["ref"] = ref
        return self._request("POST", f"/v1/nexus/work/{request_id}/evidence", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def set_implementation_context(self, *, session: Session, request_id: str, implementation_context: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/nexus/work/{request_id}/implementation-context",
            payload={"implementation_context": implementation_context},
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=False,
        )

    def approve_work_plan(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/nexus/work/{request_id}/approve-plan",
            payload={},
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=False,
        )

    def github_issue_create(self, *, session: Session, request_id: str, title: str | None = None, labels: list[str] | None = None, assignees: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"dry_run": dry_run, "labels": labels or [], "assignees": assignees or []}
        if title:
            payload["title"] = title
        return self._request("POST", f"/v1/nexus/github/issues/{request_id}", payload=payload, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def github_issue_sync(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/github/issues/{request_id}/sync", payload={}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def github_pr_link(self, *, session: Session, request_id: str, url: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/github/pull-requests/{request_id}/link", payload={"url": url}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def github_pr_sync(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/github/pull-requests/{request_id}/sync", payload={}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def github_sync(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/github/sync/{request_id}", payload={}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def github_status(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/nexus/github/status/{request_id}", headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def github_alerts(self, *, session: Session, unresolved_only: bool = True, limit: int = 50) -> dict[str, Any]:
        return self._request("GET", "/v1/nexus/github/alerts", query={"unresolved": "1" if unresolved_only else "0", "limit": str(limit)}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def github_repos_list(self, *, session: Session) -> dict[str, Any]:
        return self._request("GET", "/v1/nexus/github/repositories", headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def github_repos_sync(self, *, session: Session) -> dict[str, Any]:
        return self._request("POST", "/v1/nexus/github/repositories/sync", payload={}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def list_reviews(self, *, session: Session, status: str = "in-review", limit: int = 100) -> dict[str, Any]:
        return self._request("GET", "/v1/nexus/reviews", query={"status": status, "limit": str(limit)}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=True)

    def submit_review(self, *, session: Session, request_id: str, verdict: str, summary: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/nexus/reviews/{request_id}", payload={"verdict": verdict, "summary": summary}, headers=self._session_headers(session), timeout=self._timeout_seconds, retry_once=False)

    def list_capabilities(self, *, session: Session, status: str, system_id: str | None = None) -> dict[str, Any]:
        query: dict[str, str] = {"status": status}
        if system_id:
            query["system_id"] = system_id
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


    def get_context(self, *, session: Session) -> dict[str, Any]:
        return self._request(
            "GET",
            "/v1/nexus/context",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def create_request(
        self,
        *,
        session: Session,
        objective: str,
        missing_capability: str,
        business_impact: str,
        expected_behavior: str,
        acceptance_criteria: list[str],
        risk_class: str,
        priority: str,
        goal_ref: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/nexus/requests",
            payload={
                "objective": objective,
                "missing_capability": missing_capability,
                "business_impact": business_impact,
                "expected_behavior": expected_behavior,
                "acceptance_criteria": acceptance_criteria,
                "risk_class": risk_class,
                "priority": priority,
                "goal_ref": goal_ref,
            },
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=False,
        )

    def list_requests(self, *, session: Session, status: str = "submitted", limit: int = 100) -> dict[str, Any]:
        query = {"status": status, "limit": str(limit)}
        return self._request(
            "GET",
            "/v1/nexus/requests",
            query=query,
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def show_request(self, *, session: Session, request_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v1/nexus/requests/{request_id}",
            headers=self._session_headers(session),
            timeout=self._timeout_seconds,
            retry_once=True,
        )

    def transition_request(self, *, session: Session, request_id: str, to: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/v1/nexus/requests/{request_id}/transition",
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
        timeout: float,
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
