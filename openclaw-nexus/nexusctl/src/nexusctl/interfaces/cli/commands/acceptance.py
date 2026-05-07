"""Business acceptance and safety-veto CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nexusctl.app.acceptance_service import AcceptanceService
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, emit_payload
from nexusctl.interfaces.cli.runtime import resolve_token
from nexusctl.interfaces.http.client import NexusctlAPIClient


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    acceptance_parser = subparsers.add_parser("acceptance", help="business acceptance and safety-veto commands")
    acceptance_subparsers = acceptance_parser.add_subparsers(dest="acceptance_command")

    acceptance_submit = acceptance_subparsers.add_parser(
        "submit",
        help="submit source-domain acceptance for a FeatureRequest",
    )
    add_auth_runtime_args(acceptance_submit)
    acceptance_submit.add_argument("id", help="feature request id or patch proposal id")
    acceptance_submit.add_argument(
        "--verdict",
        required=True,
        choices=["accepted", "rejected", "vetoed"],
        help="acceptance verdict; vetoed requires safety.veto",
    )
    acceptance_submit.add_argument("--notes", default="", help="acceptance or veto notes")

    acceptance_status = acceptance_subparsers.add_parser(
        "status",
        help="show acceptance status for a FeatureRequest",
    )
    add_auth_runtime_args(acceptance_status)
    acceptance_status.add_argument("id", help="feature request id or patch proposal id")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "acceptance_command", None)
    if command == "submit":
        return _cmd_submit(args)
    if command == "status":
        return _cmd_status(args)
    return 2


def _cmd_submit(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(
            args,
            _api_client(args).submit_acceptance(args.id, verdict=args.verdict, notes=args.notes),
        )
    return authenticated_service(
        args,
        _service,
        lambda session, service: {
            "ok": True,
            "agent_id": session.subject.agent_id,
            "domain": session.subject.domain,
            **service.submit(session.subject, args.id, verdict=args.verdict, notes=args.notes),
        },
        commit=True,
    )


def _cmd_status(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).acceptance_status(args.id))
    return authenticated_service(
        args,
        _service,
        lambda session, service: service.status(session.subject, args.id),
    )


def _service(connection: Any, policy: PolicyEngine, project_root: Path) -> AcceptanceService:
    return AcceptanceService(connection, policy, project_root)


def _api_client(args: argparse.Namespace) -> NexusctlAPIClient:
    return NexusctlAPIClient(args.api_url, token=resolve_token(args), timeout=getattr(args, "api_timeout", None))


def _emit_remote(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    return emit_payload(args, {**payload, "transport": "http"})
