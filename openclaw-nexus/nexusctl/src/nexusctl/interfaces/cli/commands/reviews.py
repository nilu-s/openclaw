"""Technical review CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nexusctl.app.review_service import ReviewService
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, emit_payload
from nexusctl.interfaces.cli.runtime import resolve_token
from nexusctl.interfaces.http.client import NexusctlAPIClient


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    review_parser = subparsers.add_parser("review", help="technical software review commands")
    review_subparsers = review_parser.add_subparsers(dest="review_command")

    review_queue = review_subparsers.add_parser("queue", help="show patch proposals awaiting technical review")
    add_auth_runtime_args(review_queue)

    review_submit = review_subparsers.add_parser("submit", help="submit a technical review verdict for a patch proposal")
    add_auth_runtime_args(review_submit)
    review_submit.add_argument("id", help="patch proposal id or work item id")
    review_submit.add_argument(
        "--verdict",
        required=True,
        choices=["approved", "changes-requested", "rejected"],
        help="technical review verdict",
    )
    review_submit.add_argument("--notes", default="", help="review notes")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "review_command", None)
    if command == "queue":
        return _cmd_queue(args)
    if command == "submit":
        return _cmd_submit(args)
    return 2


def _cmd_queue(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).review_queue())
    return authenticated_service(args, _service, lambda session, service: service.queue(session.subject))


def _cmd_submit(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(
            args,
            _api_client(args).submit_review(args.id, verdict=args.verdict, notes=args.notes),
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


def _service(connection: Any, policy: PolicyEngine, project_root: Path) -> ReviewService:
    return ReviewService(connection, policy, project_root)


def _api_client(args: argparse.Namespace) -> NexusctlAPIClient:
    return NexusctlAPIClient(args.api_url, token=resolve_token(args), timeout=getattr(args, "api_timeout", None))


def _emit_remote(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    return emit_payload(args, {**payload, "transport": "http"})
