"""Goal CLI commands extracted from the monolithic CLI entry point."""

from __future__ import annotations

import argparse

from nexusctl.app.goal_service import GoalService, parse_metric_values
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, goal_collection_payload, subject_payload


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    goals_parser = subparsers.add_parser("goals", help="goal read, measurement, and evaluation commands")
    goals_subparsers = goals_parser.add_subparsers(dest="goals_command")

    list_parser = goals_subparsers.add_parser("list", help="list visible goals for the authenticated domain")
    add_auth_runtime_args(list_parser)
    list_parser.add_argument("--domain", help="domain override; forbidden for normal agents")

    status_parser = goals_subparsers.add_parser("status", help="show visible goal status for authenticated domain")
    add_auth_runtime_args(status_parser)
    status_parser.add_argument("--domain", help="domain override; forbidden for normal agents")

    show_parser = goals_subparsers.add_parser("show", help="show one visible goal")
    add_auth_runtime_args(show_parser)
    show_parser.add_argument("goal", help="goal id")

    measure_parser = goals_subparsers.add_parser("measure", help="record measurements for a goal")
    add_auth_runtime_args(measure_parser)
    measure_parser.add_argument("goal", help="goal id")
    measure_parser.add_argument("--evidence", help="evidence id to measure from; defaults to latest evidence")
    measure_parser.add_argument(
        "--value",
        action="append",
        default=[],
        metavar="METRIC=VALUE",
        help="explicit metric value; may be repeated and overrides evidence values",
    )

    evaluate_parser = goals_subparsers.add_parser("evaluate", help="evaluate a goal from latest measurements")
    add_auth_runtime_args(evaluate_parser)
    evaluate_parser.add_argument("goal", help="goal id")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "goals_command", None)
    if command == "list":
        return authenticated_service(args, _service, lambda session, service: _list(args, session, service))
    if command == "status":
        return authenticated_service(args, _service, lambda session, service: _status(args, session, service))
    if command == "show":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, goal=service.show(session.subject, args.goal)))
    if command == "measure":
        return authenticated_service(args, _service, lambda session, service: _measure(args, session, service), commit=True)
    if command == "evaluate":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, evaluation=service.evaluate(session.subject, args.goal)), commit=True)
    return 2


def _service(connection, policy, project_root) -> GoalService:
    return GoalService(connection, policy)


def _list(args: argparse.Namespace, session, service: GoalService) -> dict:
    goals = service.list_goals(session.subject, domain=getattr(args, "domain", None))
    return goal_collection_payload(args, session, goals=goals)


def _status(args: argparse.Namespace, session, service: GoalService) -> dict:
    goals = service.status(session.subject, domain=getattr(args, "domain", None))
    return goal_collection_payload(args, session, goals=goals)


def _measure(args: argparse.Namespace, session, service: GoalService) -> dict:
    measurement = service.measure(
        session.subject,
        args.goal,
        evidence_id=args.evidence,
        values=parse_metric_values(args.value),
    )
    return subject_payload(session, measurement=measurement)
