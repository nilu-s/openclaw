"""Framework-free HTTP route functions for the Nexusctl API.

The module intentionally keeps transport concerns here and delegates all domain
mutations to app services that are also used by the CLI.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from nexusctl.app.acceptance_service import AcceptanceService
from nexusctl.app.feature_request_service import FeatureRequestService
from nexusctl.app.goal_service import GoalService
from nexusctl.app.patch_service import PatchService
from nexusctl.app.check_service import PolicyCheckService
from nexusctl.app.reconciliation_service import GitHubReconciliationService
from nexusctl.app.review_service import ReviewService
from nexusctl.app.schedule_service import ScheduleService
from nexusctl.app.work_service import WorkService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.domain.errors import AuthenticationError, NexusctlError, ValidationError
from nexusctl.interfaces.http.auth import authenticate_subject, optional_json_bool
from nexusctl.interfaces.http.schemas import JsonResponse, optional_string, parse_json_body, require_string
from nexusctl.storage.sqlite.migrations import apply_migrations, seed_from_blueprint


def handle_github_webhook(
    connection: sqlite3.Connection,
    *,
    project_root: str | Path,
    headers: Mapping[str, str],
    body: bytes,
    secret: str | None = None,
) -> JsonResponse:
    """Verify and persist a GitHub webhook request.

    The route does not accept agent tokens because GitHub authenticates the
    delivery with HMAC. Reconciliation is still performed by a Nexusctl-authorized
    command or caller.
    """

    try:
        _ensure_ready(connection, Path(project_root))
        matrix = CapabilityMatrix.from_project_root(Path(project_root))
        service = GitHubReconciliationService(connection, PolicyEngine(matrix), Path(project_root))
        payload = service.receive_webhook(headers=headers, body=body, secret=secret)
        connection.commit()
        return JsonResponse(status=202, body=payload, headers={"content-type": "application/json"})
    except NexusctlError as exc:
        connection.rollback()
        return _error_response(exc)


def handle_api_request(
    connection: sqlite3.Connection,
    *,
    project_root: str | Path,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes = b"",
    webhook_secret: str | None = None,
) -> JsonResponse:
    """Dispatch one HTTP API request using Python stdlib primitives."""

    root = Path(project_root)
    parsed = urlparse(path)
    route_path = parsed.path.rstrip("/") or "/"
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
    method = method.upper()
    try:
        _ensure_ready(connection, root)
        if method == "GET" and route_path == "/healthz":
            return JsonResponse(200, {"ok": True, "service": "nexusctl-api", "api_version": 1})
        if method == "POST" and route_path == "/webhooks/github":
            return handle_github_webhook(
                connection,
                project_root=root,
                headers=headers,
                body=body,
                secret=webhook_secret,
            )

        matrix = CapabilityMatrix.from_project_root(root)
        policy = PolicyEngine(matrix)
        subject = authenticate_subject(connection, headers)
        payload = parse_json_body(body)

        if method == "GET" and route_path == "/auth/me":
            capabilities = sorted(subject.capabilities)
            return _ok({"agent": _subject_json(subject), "capabilities": capabilities})

        if route_path == "/goals" and method == "GET":
            return _ok({"goals": GoalService(connection, policy).list_goals(subject, domain=query.get("domain"))})
        if route_path.startswith("/goals/") and method == "GET":
            goal_id = route_path.split("/", 2)[2]
            return _ok({"goal": GoalService(connection, policy).show(subject, goal_id)})

        fr_service = FeatureRequestService(connection, policy)
        if route_path == "/feature-requests" and method == "GET":
            return _ok({"feature_requests": fr_service.list(subject)})
        if route_path == "/feature-requests" and method == "POST":
            result = fr_service.create(
                subject,
                target_domain=require_string(payload, "target_domain"),
                goal_id=require_string(payload, "goal_id"),
                title=require_string(payload, "title"),
            )
            connection.commit()
            return _created({"feature_request": result})
        if route_path.startswith("/feature-requests/") and method == "GET":
            request_id = route_path.split("/", 2)[2]
            return _ok({"feature_request": fr_service.show(subject, request_id)})
        if route_path.startswith("/feature-requests/") and route_path.endswith("/route") and method == "POST":
            request_id = route_path.split("/")[2]
            result = fr_service.route(subject, request_id, target_domain=require_string(payload, "target_domain"))
            connection.commit()
            return _ok({"feature_request": result})
        if route_path.startswith("/feature-requests/") and route_path.endswith("/transition") and method == "POST":
            request_id = route_path.split("/")[2]
            result = fr_service.transition(subject, request_id, require_string(payload, "status"))
            connection.commit()
            return _ok({"feature_request": result})

        work_service = WorkService(connection, policy)
        if route_path.startswith("/work/") and route_path.endswith("/start") and method == "POST":
            work_id = route_path.split("/")[2]
            result = PatchService(connection, policy, root).start_work(subject, work_id)
            connection.commit()
            return _ok({"work_start": result})
        if route_path.startswith("/work/") and method == "GET":
            work_id = route_path.split("/", 2)[2]
            return _ok({"work": work_service.show(subject, work_id)})
        if route_path == "/work/plan" and method == "POST":
            result = work_service.plan(subject, require_string(payload, "feature_request_id"))
            connection.commit()
            return _created({"work": result})
        if route_path == "/work/assign" and method == "POST":
            result = work_service.assign(
                subject,
                require_string(payload, "feature_request_id"),
                builder=require_string(payload, "builder"),
                reviewer=require_string(payload, "reviewer"),
            )
            connection.commit()
            return _ok({"work": result})

        if route_path == "/policy/check" and method == "POST":
            result = PolicyCheckService(connection, policy, root).check(subject, require_string(payload, "patch_id"))
            return _ok({"policy_check": result})

        review_service = ReviewService(connection, policy, root)
        if route_path == "/reviews" and method == "GET":
            return _ok(review_service.queue(subject))
        if route_path == "/reviews" and method == "POST":
            result = review_service.submit(
                subject,
                require_string(payload, "id"),
                verdict=require_string(payload, "verdict"),
                notes=optional_string(payload, "notes"),
            )
            connection.commit()
            return _created({"review": result})

        acceptance_service = AcceptanceService(connection, policy, root)
        if route_path.startswith("/acceptance/") and method == "GET":
            request_id = route_path.split("/", 2)[2]
            return _ok({"acceptance": acceptance_service.status(subject, request_id)})
        if route_path == "/acceptance" and method == "POST":
            result = acceptance_service.submit(
                subject,
                require_string(payload, "id"),
                verdict=require_string(payload, "verdict"),
                notes=optional_string(payload, "notes"),
            )
            connection.commit()
            return _created({"acceptance": result})

        schedule_service = ScheduleService(root, connection=connection, policy=policy)
        if route_path == "/schedules" and method == "GET":
            return _ok(schedule_service.list(subject))
        if route_path == "/schedules/validate" and method == "GET":
            return _ok(schedule_service.validate(subject))
        if route_path.startswith("/schedules/") and route_path.endswith("/run") and method == "POST":
            schedule_id = route_path.split("/")[2]
            result = schedule_service.run(subject, schedule_id, dry_run=optional_json_bool(payload.get("dry_run"), field="dry_run", default=False))
            connection.commit()
            return _created(result)

        return JsonResponse(404, {"ok": False, "error": "not found"})
    except AuthenticationError as exc:
        connection.rollback()
        return _error_response(exc, status=401)
    except NexusctlError as exc:
        connection.rollback()
        return _error_response(exc)


def _subject_json(subject: Any) -> dict[str, Any]:
    return {
        "agent_id": subject.agent_id,
        "domain": subject.domain,
        "role": subject.role,
        "normal_agent": subject.normal_agent,
    }


def _ensure_ready(connection: sqlite3.Connection, project_root: Path) -> None:
    apply_migrations(connection)
    if _safe_count(connection, "agents") == 0:
        seed_from_blueprint(connection, project_root)
        connection.commit()


def _ok(payload: dict[str, Any]) -> JsonResponse:
    return JsonResponse(200, {"ok": True, **payload}, {"content-type": "application/json"})


def _created(payload: dict[str, Any]) -> JsonResponse:
    return JsonResponse(201, {"ok": True, **payload}, {"content-type": "application/json"})


def _error_response(exc: NexusctlError, *, status: int | None = None) -> JsonResponse:
    code = status if status is not None else (400 if isinstance(exc, ValidationError) else 403)
    return JsonResponse(status=code, body={"ok": False, "error": str(exc), "rule_id": getattr(exc, "rule_id", None)})


def _safe_count(connection: sqlite3.Connection, table_name: str) -> int:
    try:
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"] if hasattr(row, "keys") else row[0])
    except sqlite3.Error:
        return 0
