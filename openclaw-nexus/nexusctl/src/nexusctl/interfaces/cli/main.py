"""Nexusctl CLI entry point through GitHub projection workflow.

GitHub projection workflow adds GitHub-App projection commands. GitHub remains a mockable
projection surface; Nexusctl remains lifecycle authority and agents never receive
GitHub write tokens.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Callable

from nexusctl.app.goal_service import GoalService, parse_metric_values
from nexusctl.app.generation_service import GenerationService
from nexusctl.app.merge_service import MergeService
from nexusctl.app.check_service import PolicyCheckService
from nexusctl.app.runtime_tool_service import RuntimeToolService
from nexusctl.app.schedule_service import ScheduleService
from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.domain.errors import NexusctlError, PolicyDeniedError, ValidationError
from nexusctl.interfaces.cli.output import error_payload, print_json
from nexusctl.interfaces.cli.commands import (
    acceptance as acceptance_commands,
    db as db_commands,
    doctor as doctor_commands,
    feature_requests as feature_requests_commands,
    github as github_commands,
    domains as domains_commands,
    generate as generate_commands,
    goals as goals_commands,
    me as me_commands,
    schedules as schedules_commands,
    scopes as scopes_commands,
    work as work_commands,
    patches as patches_commands,
    reviews as reviews_commands,
)
from nexusctl.interfaces.cli.commands.common import (
    add_auth_runtime_args,
    add_runtime_args,
    print_human,
)
from nexusctl.interfaces.http.client import NexusctlAPIClient
from nexusctl.interfaces.cli.runtime import (
    CommandRuntime,
    count_rows,
    initialize_database,
    open_ready_database,
    resolve_token,
    safe_count_rows,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexusctl")
    subparsers = parser.add_subparsers(dest="command")

    db_commands.register(subparsers)

    auth_parser = subparsers.add_parser("auth", help="agent token commands")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")
    login_parser = auth_subparsers.add_parser("login", help="issue a local-test token for an agent")
    _add_runtime_args(login_parser)
    login_parser.add_argument("--agent", required=True, help="agent id to authenticate locally")
    login_parser.add_argument("--json", action="store_true")

    rotate_parser = auth_subparsers.add_parser("rotate-token", help="rotate an agent token")
    _add_runtime_args(rotate_parser)
    rotate_parser.add_argument("agent", help="agent id whose token should be rotated")
    rotate_parser.add_argument("--token", help="actor token; defaults to NEXUSCTL_TOKEN")
    rotate_parser.add_argument("--json", action="store_true")

    me_commands.register(subparsers)
    domains_commands.register(subparsers)
    goals_commands.register(subparsers)

    feature_requests_commands.register(subparsers)

    github_commands.register(subparsers)

    policy_parser = subparsers.add_parser("policy", help="policy gate commands")
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command")
    policy_check = policy_subparsers.add_parser("check", help="evaluate merge policy gates for a patch proposal")
    _add_auth_runtime_args(policy_check)
    policy_check.add_argument("patch_id", help="patch proposal id")

    merge_parser = subparsers.add_parser("merge", help="merge an approved FeatureRequest or PR after merge gates pass")
    _add_auth_runtime_args(merge_parser)
    merge_parser.add_argument("id", help="feature request id, patch proposal id, PR link id, or PR number")

    acceptance_commands.register(subparsers)
    work_commands.register(subparsers)
    patches_commands.register(subparsers)
    reviews_commands.register(subparsers)
    scopes_commands.register(subparsers)

    generate_commands.register(subparsers)
    schedules_commands.register(subparsers)


    runtime_tools_parser = subparsers.add_parser("runtime-tools", help="runtime tool registry and guardrail checks")
    runtime_tools_subparsers = runtime_tools_parser.add_subparsers(dest="runtime_tools_command")
    runtime_tools_list = runtime_tools_subparsers.add_parser("list", help="list registered runtime tools")
    _add_runtime_args(runtime_tools_list)
    runtime_tools_list.add_argument("--json", action="store_true")
    runtime_tools_show = runtime_tools_subparsers.add_parser("show", help="show one registered runtime tool")
    _add_runtime_args(runtime_tools_show)
    runtime_tools_show.add_argument("id", help="runtime tool id")
    runtime_tools_show.add_argument("--json", action="store_true")
    runtime_tools_check = runtime_tools_subparsers.add_parser("check", help="check guardrails for invoking one runtime tool")
    _add_runtime_args(runtime_tools_check)
    runtime_tools_check.add_argument("id", help="runtime tool id")
    runtime_tools_check.add_argument("--agent", default="operator", help="agent id to evaluate; defaults to operator")
    runtime_tools_check.add_argument("--json", action="store_true")

    doctor_commands.register(subparsers)



    evidence_parser = subparsers.add_parser("evidence", help="goal evidence commands")
    evidence_subparsers = evidence_parser.add_subparsers(dest="evidence_command")
    add_parser = evidence_subparsers.add_parser("add", help="attach an evidence file to a goal")
    _add_runtime_args(add_parser)
    add_parser.add_argument("--token", help="agent token; defaults to NEXUSCTL_TOKEN")
    add_parser.add_argument("--goal", required=True, help="goal id")
    add_parser.add_argument("--file", required=True, help="path to evidence file")
    add_parser.add_argument("--summary", default="", help="short evidence summary")
    add_parser.add_argument("--json", action="store_true")

    return parser


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    add_runtime_args(parser)


def _add_auth_runtime_args(parser: argparse.ArgumentParser) -> None:
    add_auth_runtime_args(parser)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "db" and args.db_command == "init":
            return _cmd_db_init(args)
        if args.command == "db":
            return db_commands.handle(args)
        if args.command == "auth" and args.auth_command == "login":
            return _cmd_auth_login(args)
        if args.command == "auth" and args.auth_command == "rotate-token":
            return _cmd_auth_rotate_token(args)
        if args.command == "me":
            return me_commands.handle(args)
        if args.command == "domains":
            return domains_commands.handle(args)
        if args.command == "goals":
            return goals_commands.handle(args)
        if args.command == "feature-request":
            return feature_requests_commands.handle(args)
        if args.command == "github":
            return github_commands.handle(args)
        if args.command == "policy" and args.policy_command == "check":
            return _cmd_policy_check(args)
        if args.command == "merge":
            return _cmd_merge(args)
        if args.command == "acceptance":
            return acceptance_commands.handle(args)
        if args.command == "work":
            return work_commands.handle(args)
        if args.command == "patch":
            return patches_commands.handle(args)
        if args.command == "review":
            return reviews_commands.handle(args)
        if args.command == "scopes":
            return scopes_commands.handle(args)
        if args.command == "generate":
            return generate_commands.handle(args)

        if args.command == "schedules":
            return schedules_commands.handle(args)
        if args.command == "runtime-tools" and args.runtime_tools_command == "list":
            return _cmd_runtime_tools_list(args)
        if args.command == "runtime-tools" and args.runtime_tools_command == "show":
            return _cmd_runtime_tools_show(args)
        if args.command == "runtime-tools" and args.runtime_tools_command == "check":
            return _cmd_runtime_tools_check(args)
        if args.command == "doctor":
            return doctor_commands.handle(args)
        if args.command == "evidence" and args.evidence_command == "add":
            return _cmd_evidence_add(args)
    except NexusctlError as exc:
        return _error(args, exc)

    parser.print_help()
    return 2


def _cmd_db_init(args: argparse.Namespace) -> int:
    payload = initialize_database(args)
    if args.json:
        _print_json(payload)
    else:
        print(
            f"Initialized {payload['db']} with {payload['tables']} MVP tables "
            "and FeatureRequest support."
        )
    return 0


def _cmd_auth_login(args: argparse.Namespace) -> int:
    connection = _open_ready_database(args)
    try:
        credential, session = AgentTokenRegistry(connection).issue_local_login(args.agent)
        connection.commit()
        payload = {"ok": True, "credential": credential.to_json(), "session": session.to_json()}
    finally:
        connection.close()
    if args.json:
        _print_json(payload)
    else:
        print(f"Logged in {args.agent}. Export NEXUSCTL_TOKEN={credential.token}")
    return 0


def _cmd_auth_rotate_token(args: argparse.Namespace) -> int:
    connection = _open_ready_database(args)
    try:
        registry = AgentTokenRegistry(connection)
        actor_session = registry.authenticate(_resolve_token(args))
        credential = registry.rotate_token(args.agent, actor=actor_session.subject)
        connection.commit()
        payload = {
            "ok": True,
            "rotated_agent": args.agent,
            "actor": actor_session.subject.agent_id,
            "credential": credential.to_json(),
        }
    finally:
        connection.close()
    if args.json:
        _print_json(payload)
    else:
        print(f"Rotated token for {args.agent}. New token: {credential.token}")
    return 0


def _cmd_me(args: argparse.Namespace) -> int:
    connection = _open_ready_database(args)
    try:
        session = AgentTokenRegistry(connection).authenticate(_resolve_token(args))
        connection.commit()
    finally:
        connection.close()

    if args.me_command == "capabilities":
        payload = {
            "ok": True,
            "agent_id": session.subject.agent_id,
            "domain": session.subject.domain,
            "capabilities": sorted(session.subject.capabilities),
        }
    else:
        payload = {"ok": True, "identity": session.to_json()}

    if getattr(args, "json", False):
        _print_json(payload)
    else:
        if args.me_command == "capabilities":
            print("\n".join(payload["capabilities"]))
        else:
            print(f"{session.subject.agent_id} ({session.subject.domain}/{session.subject.role})")
    return 0


def _cmd_goals_list(args: argparse.Namespace) -> int:
    return _with_goal_service(args, lambda session, service: _emit_goals_list(args, session, service))


def _cmd_goals_status(args: argparse.Namespace) -> int:
    return _with_goal_service(args, lambda session, service: _emit_goals_status(args, session, service))


def _cmd_goals_show(args: argparse.Namespace) -> int:
    return _with_goal_service(args, lambda session, service: _emit_goals_show(args, session, service))


def _cmd_goals_measure(args: argparse.Namespace) -> int:
    return _with_goal_service(args, lambda session, service: _emit_goals_measure(args, session, service), commit=True)


def _cmd_goals_evaluate(args: argparse.Namespace) -> int:
    return _with_goal_service(args, lambda session, service: _emit_goals_evaluate(args, session, service), commit=True)


def _cmd_evidence_add(args: argparse.Namespace) -> int:
    return _with_goal_service(args, lambda session, service: _emit_evidence_add(args, session, service), commit=True)


def _cmd_policy_check(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _emit_remote(args, _api_client(args).policy_check(args.patch_id))
    return _with_policy_check_service(
        args,
        lambda session, service: {"ok": True, "agent_id": session.subject.agent_id, "domain": session.subject.domain, "policy_check": service.check(session.subject, args.patch_id)},
    )


def _cmd_merge(args: argparse.Namespace) -> int:
    return _with_merge_service(
        args,
        lambda session, service: {
            "agent_id": session.subject.agent_id,
            "domain": session.subject.domain,
            **service.merge(session.subject, args.id),
        },
        commit=True,
    )


def _cmd_generate_openclaw(args: argparse.Namespace) -> int:
    return _with_generation_service(args, lambda session, service: service.generate_openclaw(session.subject), commit=True)


def _cmd_generate_agents(args: argparse.Namespace) -> int:
    return _with_generation_service(args, lambda session, service: service.generate_agents(session.subject), commit=True)


def _cmd_generate_skills(args: argparse.Namespace) -> int:
    return _with_generation_service(args, lambda session, service: service.generate_skills(session.subject), commit=True)


def _cmd_generate_all(args: argparse.Namespace) -> int:
    return _with_generation_service(args, lambda session, service: service.generate_all(session.subject), commit=True)



def _runtime_tool_service(args: argparse.Namespace) -> RuntimeToolService:
    matrix = CapabilityMatrix.from_project_root(Path(args.project_root))
    return RuntimeToolService(Path(args.project_root), matrix)


def _cmd_runtime_tools_list(args: argparse.Namespace) -> int:
    payload = {"ok": True, "runtime_tools": _runtime_tool_service(args).list_tools()}
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_human(payload)
    return 0


def _cmd_runtime_tools_show(args: argparse.Namespace) -> int:
    payload = {"ok": True, "runtime_tool": _runtime_tool_service(args).show_tool(args.id)}
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_human(payload)
    return 0


def _cmd_runtime_tools_check(args: argparse.Namespace) -> int:
    matrix = CapabilityMatrix.from_project_root(Path(args.project_root))
    service = RuntimeToolService(Path(args.project_root), matrix)
    subject = matrix.subject_for_agent(args.agent)
    payload = {"ok": True, "runtime_tool_check": service.check_tool(subject, args.id)}
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_human(payload)
    return 0


def _cmd_schedules_list(args: argparse.Namespace) -> int:
    return _with_schedule_service(args, lambda session, service: {"agent_id": session.subject.agent_id, "domain": session.subject.domain, **service.list(session.subject)})


def _cmd_schedules_validate(args: argparse.Namespace) -> int:
    return _with_schedule_service(args, lambda session, service: {"agent_id": session.subject.agent_id, "domain": session.subject.domain, **service.validate(session.subject)})


def _cmd_schedules_render_openclaw(args: argparse.Namespace) -> int:
    return _with_schedule_service(args, lambda session, service: {"agent_id": session.subject.agent_id, "domain": session.subject.domain, **service.render_openclaw(session.subject)}, commit=True)


def _cmd_schedules_reconcile_openclaw(args: argparse.Namespace) -> int:
    return _with_schedule_service(args, lambda session, service: {"agent_id": session.subject.agent_id, "domain": session.subject.domain, **service.reconcile_openclaw(session.subject)})


def _cmd_schedules_run(args: argparse.Namespace) -> int:
    return _with_schedule_service(args, lambda session, service: {"agent_id": session.subject.agent_id, "domain": session.subject.domain, **service.run(session.subject, args.schedule, dry_run=args.dry_run)}, commit=True)

def _cmd_doctor(args: argparse.Namespace) -> int:
    payload = GenerationService(Path(args.project_root)).doctor()
    if args.json:
        _print_json(payload)
    else:
        _print_human(payload)
    return 0 if payload.get("ok") else 1


def _api_client(args: argparse.Namespace) -> NexusctlAPIClient:
    return NexusctlAPIClient(args.api_url, token=_resolve_token(args), timeout=getattr(args, "api_timeout", None))


def _emit_remote(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    payload = {**payload, "transport": "http"}
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_human(payload)
    return 0


def _run_command_with_runtime(
    args: argparse.Namespace,
    service_builder: Callable[[CommandRuntime], Any],
    callback: Callable[[Any, Any], dict[str, Any]],
    *,
    commit: bool = False,
) -> int:
    """Run a CLI command through the shared CommandRuntime Unit of Work."""

    with CommandRuntime(args) as runtime:
        session = runtime.require_session()
        payload = callback(session, service_builder(runtime))
        runtime.mark_success(commit=commit)
    if getattr(args, "json", False):
        _print_json(payload)
    else:
        _print_human(payload)
    return 0


def _with_goal_service(args: argparse.Namespace, callback: Callable[[Any, GoalService], dict[str, Any]], *, commit: bool = False) -> int:
    return _run_command_with_runtime(args, lambda runtime: runtime.goal_service(), callback, commit=commit)


def _with_policy_check_service(
    args: argparse.Namespace,
    callback: Callable[[Any, PolicyCheckService], dict[str, Any]],
    *,
    commit: bool = False,
) -> int:
    return _run_command_with_runtime(args, lambda runtime: runtime.policy_check_service(), callback, commit=commit)


def _with_merge_service(
    args: argparse.Namespace,
    callback: Callable[[Any, MergeService], dict[str, Any]],
    *,
    commit: bool = False,
) -> int:
    return _run_command_with_runtime(args, lambda runtime: runtime.merge_service(), callback, commit=commit)


def _with_schedule_service(
    args: argparse.Namespace,
    callback: Callable[[Any, ScheduleService], dict[str, Any]],
    *,
    commit: bool = False,
) -> int:
    return _run_command_with_runtime(args, lambda runtime: runtime.schedule_service(), callback, commit=commit)


def _with_generation_service(
    args: argparse.Namespace,
    callback: Callable[[Any, GenerationService], dict[str, Any]],
    *,
    commit: bool = False,
) -> int:
    def _callback(session: Any, service: GenerationService) -> dict[str, Any]:
        return {
            "agent_id": session.subject.agent_id,
            "domain": session.subject.domain,
            **callback(session, service),
        }

    return _run_command_with_runtime(args, lambda runtime: runtime.generation_service(), _callback, commit=commit)

def _emit_goals_list(args: argparse.Namespace, session: Any, service: GoalService) -> dict[str, Any]:
    goals = service.list_goals(session.subject, domain=getattr(args, "domain", None))
    return _goal_command_payload(args, session, goals=goals)


def _emit_goals_status(args: argparse.Namespace, session: Any, service: GoalService) -> dict[str, Any]:
    goals = service.status(session.subject, domain=getattr(args, "domain", None))
    return _goal_command_payload(args, session, goals=goals)


def _emit_goals_show(args: argparse.Namespace, session: Any, service: GoalService) -> dict[str, Any]:
    goal = service.show(session.subject, args.goal)
    return {"ok": True, "agent_id": session.subject.agent_id, "domain": session.subject.domain, "goal": goal}


def _emit_goals_measure(args: argparse.Namespace, session: Any, service: GoalService) -> dict[str, Any]:
    measurement = service.measure(
        session.subject,
        args.goal,
        evidence_id=args.evidence,
        values=parse_metric_values(args.value),
    )
    return {"ok": True, "agent_id": session.subject.agent_id, "domain": session.subject.domain, "measurement": measurement}


def _emit_goals_evaluate(args: argparse.Namespace, session: Any, service: GoalService) -> dict[str, Any]:
    evaluation = service.evaluate(session.subject, args.goal)
    return {"ok": True, "agent_id": session.subject.agent_id, "domain": session.subject.domain, "evaluation": evaluation}


def _emit_evidence_add(args: argparse.Namespace, session: Any, service: GoalService) -> dict[str, Any]:
    evidence = service.add_evidence(session.subject, goal_id=args.goal, file_path=args.file, summary=args.summary)
    return {"ok": True, "agent_id": session.subject.agent_id, "domain": session.subject.domain, "evidence": evidence}



def _goal_command_payload(args: argparse.Namespace, session: Any, *, goals: list[dict[str, Any]]) -> dict[str, Any]:
    requested_domain = getattr(args, "domain", None)
    return {
        "ok": True,
        "agent_id": session.subject.agent_id,
        "domain": session.subject.domain,
        "requested_domain": requested_domain,
        "visible_domain": requested_domain or session.subject.domain,
        "domain_source": "auth_token" if requested_domain is None else "policy_allowed_override",
        "goals": goals,
    }


def _open_ready_database(args: argparse.Namespace) -> Any:
    return open_ready_database(args)


def _resolve_token(args: argparse.Namespace) -> str | None:
    return resolve_token(args)


def _count(connection: Any, table_name: str) -> int:
    return count_rows(connection, table_name)


def _safe_count(connection: Any, table_name: str) -> int:
    return safe_count_rows(connection, table_name)


def _print_json(payload: dict[str, Any]) -> None:
    print_json(payload)


def _print_human(payload: dict[str, Any]) -> None:
    print_human(payload)


def _error(args: argparse.Namespace, exc: Exception) -> int:
    if getattr(args, "json", False):
        _print_json(error_payload(exc))
    else:
        print(f"error: {exc}", file=sys.stderr)
    if isinstance(exc, PolicyDeniedError):
        return 3
    if isinstance(exc, ValidationError):
        return 4
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
