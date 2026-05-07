"""Software work planning and assignment CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nexusctl.app.patch_service import PatchService
from nexusctl.app.work_service import WorkService
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, emit_payload
from nexusctl.interfaces.cli.runtime import resolve_token
from nexusctl.interfaces.http.client import NexusctlAPIClient


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    work_parser = subparsers.add_parser("work", help="software work planning and assignment commands")
    work_subparsers = work_parser.add_subparsers(dest="work_command")

    work_plan = work_subparsers.add_parser("plan", help="plan software work for a routed FeatureRequest")
    add_auth_runtime_args(work_plan)
    work_plan.add_argument("feature_request_id", help="FeatureRequest id to plan")

    work_assign = work_subparsers.add_parser("assign", help="assign builder and reviewer for a routed FeatureRequest")
    add_auth_runtime_args(work_assign)
    work_assign.add_argument("feature_request_id", help="FeatureRequest id to assign")
    work_assign.add_argument("--builder", required=True, help="software builder agent id")
    work_assign.add_argument("--reviewer", required=True, help="software reviewer agent id")

    work_show = work_subparsers.add_parser("show", help="show one work item")
    add_auth_runtime_args(work_show)
    work_show.add_argument("id", help="work item id")

    work_start = work_subparsers.add_parser("start", help="start assigned implementation work and get branch/worktree instructions")
    add_auth_runtime_args(work_start)
    work_start.add_argument("id", help="work item id")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "work_command", None)
    if command == "plan":
        return _cmd_plan(args)
    if command == "assign":
        return _cmd_assign(args)
    if command == "show":
        return _cmd_show(args)
    if command == "start":
        return _cmd_start(args)
    return 2


def _cmd_plan(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).plan_work(args.feature_request_id))
    return authenticated_service(
        args,
        _work_service,
        lambda session, service: _work_payload(session, service.plan(session.subject, args.feature_request_id)),
        commit=True,
    )


def _cmd_assign(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).assign_work(args.feature_request_id, builder=args.builder, reviewer=args.reviewer))
    return authenticated_service(
        args,
        _work_service,
        lambda session, service: _work_payload(
            session,
            service.assign(session.subject, args.feature_request_id, builder=args.builder, reviewer=args.reviewer),
        ),
        commit=True,
    )


def _cmd_show(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).show_work(args.id))
    return authenticated_service(
        args,
        _work_service,
        lambda session, service: _work_payload(session, service.show(session.subject, args.id)),
    )


def _cmd_start(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).start_work(args.id))
    return authenticated_service(
        args,
        _patch_service,
        lambda session, service: {
            "ok": True,
            "agent_id": session.subject.agent_id,
            "domain": session.subject.domain,
            "work_start": service.start_work(session.subject, args.id),
        },
        commit=True,
    )


def _api_client(args: argparse.Namespace) -> NexusctlAPIClient:
    return NexusctlAPIClient(args.api_url, token=resolve_token(args), timeout=getattr(args, "api_timeout", None))


def _emit_remote(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    return emit_payload(args, {**payload, "transport": "http"})


def _work_service(connection: Any, policy: PolicyEngine, project_root: Path) -> WorkService:
    return WorkService(connection, policy)


def _patch_service(connection: Any, policy: PolicyEngine, project_root: Path) -> PatchService:
    return PatchService(connection, policy, project_root)


def _work_payload(session: Any, work: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "agent_id": session.subject.agent_id,
        "domain": session.subject.domain,
        "domain_source": "auth_token",
        "work": work,
    }
