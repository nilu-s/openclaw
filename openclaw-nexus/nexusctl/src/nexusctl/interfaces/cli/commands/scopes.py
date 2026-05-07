"""Scope lease CLI commands."""

from __future__ import annotations

import argparse
from typing import Any

from nexusctl.app.scope_service import ScopeService
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    scopes_parser = subparsers.add_parser("scopes", help="scope lease commands")
    scopes_subparsers = scopes_parser.add_subparsers(dest="scopes_command")

    scopes_lease = scopes_subparsers.add_parser("lease", help="grant a bounded scope lease")
    add_auth_runtime_args(scopes_lease)
    scopes_lease.add_argument("--agent", required=True, help="agent receiving the lease")
    scopes_lease.add_argument("--request", required=True, help="FeatureRequest id whose work item receives the lease")
    scopes_lease.add_argument("--paths", action="append", required=True, help="repository-relative path glob; repeat or comma-separate")
    scopes_lease.add_argument("--ttl", required=True, help="lease TTL, e.g. 30m, 2h, 1d")

    scopes_revoke = scopes_subparsers.add_parser("revoke", help="revoke a scope lease")
    add_auth_runtime_args(scopes_revoke)
    scopes_revoke.add_argument("lease_id", help="scope lease id")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "scopes_command", None)
    if command == "lease":
        return _cmd_lease(args)
    if command == "revoke":
        return _cmd_revoke(args)
    return 2


def _cmd_lease(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(
            session,
            service.lease(
                session.subject,
                agent_id=args.agent,
                feature_request_id=args.request,
                paths=_expand_path_args(args.paths),
                ttl=args.ttl,
            ),
        ),
        commit=True,
    )


def _cmd_revoke(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(session, service.revoke(session.subject, args.lease_id)),
        commit=True,
    )


def _service(connection: Any, policy: Any, project_root: Any) -> ScopeService:
    return ScopeService(connection, policy)


def _payload(session: Any, lease: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "agent_id": session.subject.agent_id,
        "domain": session.subject.domain,
        "domain_source": "auth_token",
        "scope_lease": lease,
    }


def _expand_path_args(values: list[str]) -> list[str]:
    expanded: list[str] = []
    for value in values:
        expanded.extend(part.strip() for part in value.split(",") if part.strip())
    return expanded
