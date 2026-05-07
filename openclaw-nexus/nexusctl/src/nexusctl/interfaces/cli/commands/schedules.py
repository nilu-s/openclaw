"""Nexus-backed OpenClaw schedule CLI commands."""

from __future__ import annotations

import argparse

from nexusctl.app.schedule_service import ScheduleService
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, subject_payload


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    schedules_parser = subparsers.add_parser("schedules", help="render and run Nexus-backed OpenClaw schedules")
    schedules_subparsers = schedules_parser.add_subparsers(dest="schedules_command")
    schedules_list = schedules_subparsers.add_parser("list", help="list schedules from nexus/schedules.yml")
    add_auth_runtime_args(schedules_list)
    schedules_validate = schedules_subparsers.add_parser("validate", help="validate schedule guardrails and standing-order refs")
    add_auth_runtime_args(schedules_validate)
    schedules_render = schedules_subparsers.add_parser("render-openclaw", help="render generated/openclaw/schedules/*.json")
    add_auth_runtime_args(schedules_render)
    schedules_reconcile = schedules_subparsers.add_parser("reconcile-openclaw", help="check generated schedule drift")
    add_auth_runtime_args(schedules_reconcile)
    schedules_run = schedules_subparsers.add_parser("run", help="record a schedule run request")
    add_auth_runtime_args(schedules_run)
    schedules_run.add_argument("schedule", help="schedule id")
    schedules_run.add_argument("--dry-run", action="store_true", help="record and print planned effects only")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "schedules_command", None)
    if command == "list":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.list(session.subject)))
    if command == "validate":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.validate(session.subject)))
    if command == "render-openclaw":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.render_openclaw(session.subject)), commit=True)
    if command == "reconcile-openclaw":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.reconcile_openclaw(session.subject)))
    if command == "run":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.run(session.subject, args.schedule, dry_run=args.dry_run)), commit=True)
    return 2


def _service(connection, policy, project_root) -> ScheduleService:
    return ScheduleService(project_root, connection=connection, policy=policy)
