"""Patch proposal CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nexusctl.app.patch_service import PatchService
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    patch_parser = subparsers.add_parser("patch", help="patch proposal commands")
    patch_subparsers = patch_parser.add_subparsers(dest="patch_command")

    patch_submit = patch_subparsers.add_parser("submit", help="submit a scoped patch proposal from a local worktree")
    add_auth_runtime_args(patch_submit)
    patch_submit.add_argument("work_or_request_id", help="work item id or feature request id")
    patch_submit.add_argument("--from-worktree", required=True, help="candidate worktree path")

    patch_show = patch_subparsers.add_parser("show", help="show a patch proposal")
    add_auth_runtime_args(patch_show)
    patch_show.add_argument("id", help="patch proposal id")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "patch_command", None)
    if command == "submit":
        return _cmd_submit(args)
    if command == "show":
        return _cmd_show(args)
    return 2


def _cmd_submit(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(
            session,
            service.submit(session.subject, args.work_or_request_id, from_worktree=args.from_worktree),
        ),
        commit=True,
    )


def _cmd_show(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _service,
        lambda session, service: _payload(session, service.show(session.subject, args.id)),
    )


def _service(connection: Any, policy: PolicyEngine, project_root: Path) -> PatchService:
    return PatchService(connection, policy, project_root)


def _payload(session: Any, patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "agent_id": session.subject.agent_id,
        "domain": session.subject.domain,
        "domain_source": "auth_token",
        "patch": patch,
    }
