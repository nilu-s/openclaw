"""Feature Request CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from nexusctl.app.feature_request_service import FeatureRequestService
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, emit_payload
from nexusctl.interfaces.cli.runtime import resolve_token
from nexusctl.interfaces.http.client import NexusctlAPIClient


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    feature_parser = subparsers.add_parser("feature-request", help="cross-domain feature request commands")
    feature_subparsers = feature_parser.add_subparsers(dest="feature_request_command")

    create_parser = feature_subparsers.add_parser("create", help="create a source-domain request for another domain")
    add_auth_runtime_args(create_parser)
    create_parser.add_argument("--target", required=True, help="target domain that should own the work")
    create_parser.add_argument("--goal", required=True, help="source-domain goal motivating this request")
    create_parser.add_argument("--title", required=True, help="request title")

    list_parser = feature_subparsers.add_parser("list", help="list visible feature requests")
    add_auth_runtime_args(list_parser)

    show_parser = feature_subparsers.add_parser("show", help="show one feature request")
    add_auth_runtime_args(show_parser)
    show_parser.add_argument("id", help="feature request id")

    route_parser = feature_subparsers.add_parser("route", help="route a feature request to a target domain")
    add_auth_runtime_args(route_parser)
    route_parser.add_argument("id", help="feature request id")
    route_parser.add_argument("--target", required=True, help="new target domain")

    transition_parser = feature_subparsers.add_parser("transition", help="transition a feature request lifecycle status")
    add_auth_runtime_args(transition_parser)
    transition_parser.add_argument("id", help="feature request id")
    transition_parser.add_argument("status", help="new status")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "feature_request_command", None)
    if command == "create":
        return _cmd_create(args)
    if command == "list":
        return _cmd_list(args)
    if command == "show":
        return _cmd_show(args)
    if command == "route":
        return _cmd_route(args)
    if command == "transition":
        return _cmd_transition(args)
    return 2


def _cmd_create(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(
            args,
            _api_client(args).create_feature_request(target_domain=args.target, goal_id=args.goal, title=args.title),
        )
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(
            session,
            request=service.create(session.subject, target_domain=args.target, goal_id=args.goal, title=args.title),
        ),
        commit=True,
    )


def _cmd_list(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).feature_requests())
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(session, requests=service.list(session.subject)),
    )


def _cmd_show(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).show_feature_request(args.id))
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(session, request=service.show(session.subject, args.id)),
    )


def _cmd_route(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).route_feature_request(args.id, target_domain=args.target))
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(
            session,
            request=service.route(session.subject, args.id, target_domain=args.target),
        ),
        commit=True,
    )


def _cmd_transition(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(session, request=service.transition(session.subject, args.id, args.status)),
        commit=True,
    )


def _service(connection: Any, policy: Any, project_root: Any) -> FeatureRequestService:
    return FeatureRequestService(connection, policy)


def _api_client(args: argparse.Namespace) -> NexusctlAPIClient:
    return NexusctlAPIClient(args.api_url, token=resolve_token(args), timeout=getattr(args, "api_timeout", None))


def _emit_remote(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    return emit_payload(args, {**payload, "transport": "http"})


def _payload(
    session: Any,
    *,
    request: dict[str, Any] | None = None,
    requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "agent_id": session.subject.agent_id,
        "domain": session.subject.domain,
        "domain_source": "auth_token",
    }
    if request is not None:
        payload["feature_request"] = request
    if requests is not None:
        payload["feature_requests"] = requests
    return payload
