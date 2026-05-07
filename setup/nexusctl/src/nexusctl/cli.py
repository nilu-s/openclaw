from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Mapping, TextIO

from nexusctl.api import ApiClient
from nexusctl.errors import EXIT_SUCCESS, NexusError
from nexusctl.output import write_json, write_key_values, write_table
from nexusctl.session import SessionStore

CAPABILITY_ID_PATTERN = re.compile(r"^[A-Z]+-[0-9]{3,}$")
LIFECYCLE_ALIASES = {
    "intake": "submitted",
    "planned": "needs-planning",
    "build-ready": "ready-to-build",
    "building": "in-build",
    "review": "in-review",
    "approve": "approved",
    "complete": "done",
    "close": "closed",
}

REQUEST_STATUS_CHOICES = [
    "all",
    "draft",
    "submitted",
    "gate-rejected",
    "accepted",
    "needs-planning",
    "ready-to-build",
    "in-build",
    "in-review",
    "approved",
    "review-failed",
    "state-update-needed",
    "done",
    "adoption-pending",
    "closed",
    "cancelled",
]


class NexusArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover
        raise NexusError("NX-VAL-001", message)


def build_parser() -> argparse.ArgumentParser:
    parser = NexusArgumentParser(prog="nexusctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth")
    auth.add_argument("--agent-token")
    auth.add_argument("--output", choices=["table", "json"], default="table")

    rotate_token = subparsers.add_parser("rotate-token")
    rotate_token.add_argument("--agent-id", required=True, dest="agent_id")
    rotate_token.add_argument("--new-token", default=None, dest="new_token")
    rotate_token.add_argument("--output", choices=["table", "json"], default="table")

    context = subparsers.add_parser("context")
    context.add_argument("--output", choices=["table", "json"], default="table")

    systems = subparsers.add_parser("systems")
    systems_subparsers = systems.add_subparsers(dest="systems_command", required=True)

    systems_list = systems_subparsers.add_parser("list")
    systems_list.add_argument("--status", choices=["all", "planned", "active", "paused", "retired"], default="all")
    systems_list.add_argument("--output", choices=["table", "json"], default="table")

    systems_show = systems_subparsers.add_parser("show")
    systems_show.add_argument("system_id")
    systems_show.add_argument("--output", choices=["table", "json"], default="table")

    goals = subparsers.add_parser("goals")
    goals_subparsers = goals.add_subparsers(dest="goals_command", required=True)

    goals_list = goals_subparsers.add_parser("list")
    goals_list.add_argument("--system-id", default=None, dest="system_id")
    goals_list.add_argument("--status", choices=["all", "proposed", "active", "blocked", "achieved", "deprecated"], default="all")
    goals_list.add_argument("--limit", type=int, default=100)
    goals_list.add_argument("--output", choices=["table", "json"], default="table")

    goals_show = goals_subparsers.add_parser("show")
    goals_show.add_argument("goal_id")
    goals_show.add_argument("--output", choices=["table", "json"], default="table")

    goals_create = goals_subparsers.add_parser("create")
    goals_create.add_argument("--goal-id", required=True, dest="goal_id")
    goals_create.add_argument("--system-id", default=None, dest="system_id")
    goals_create.add_argument("--title", required=True)
    goals_create.add_argument("--objective", required=True)
    goals_create.add_argument("--success-metric", action="append", default=[], dest="success_metrics")
    goals_create.add_argument("--constraint", action="append", default=[], dest="constraints")
    goals_create.add_argument("--risk-class", choices=["low", "medium", "high", "critical"], required=True, dest="risk_class")
    goals_create.add_argument("--priority", choices=["P0", "P1", "P2", "P3"], required=True)
    goals_create.add_argument("--owner-agent-id", default=None, dest="owner_agent_id")
    goals_create.add_argument("--status", choices=["proposed", "active", "blocked", "achieved", "deprecated"], default="proposed")
    goals_create.add_argument("--parent-goal-id", default=None, dest="parent_goal_id")
    goals_create.add_argument("--output", choices=["table", "json"], default="table")

    goals_status = goals_subparsers.add_parser("update-status")
    goals_status.add_argument("goal_id")
    goals_status.add_argument("--to", required=True, choices=["proposed", "active", "blocked", "achieved", "deprecated"], dest="to_status")
    goals_status.add_argument("--reason", required=True)
    goals_status.add_argument("--output", choices=["table", "json"], default="table")

    scopes = subparsers.add_parser("scopes")
    scopes_subparsers = scopes.add_subparsers(dest="scopes_command", required=True)
    scopes_list = scopes_subparsers.add_parser("list")
    scopes_list.add_argument("--agent-id", default=None, dest="agent_id")
    scopes_list.add_argument("--output", choices=["table", "json"], default="table")
    scopes_effective = scopes_subparsers.add_parser("effective")
    scopes_effective.add_argument("--output", choices=["table", "json"], default="table")
    scopes_lease = scopes_subparsers.add_parser("lease")
    scopes_lease.add_argument("--agent-id", required=True, dest="agent_id")
    scopes_lease.add_argument("--scope", required=True)
    scopes_lease.add_argument("--system-id", default="*", dest="system_id")
    scopes_lease.add_argument("--resource", default="*", dest="resource_pattern")
    scopes_lease.add_argument("--request-id", default=None, dest="request_id")
    scopes_lease.add_argument("--reason", required=True)
    scopes_lease.add_argument("--ttl-minutes", type=int, default=120, dest="ttl_minutes")
    scopes_lease.add_argument("--approved-by", default=None, dest="approved_by")
    scopes_lease.add_argument("--output", choices=["table", "json"], default="table")
    scopes_leases = scopes_subparsers.add_parser("leases")
    scopes_leases.add_argument("--agent-id", default=None, dest="agent_id")
    scopes_leases.add_argument("--all", action="store_true", dest="include_inactive")
    scopes_leases.add_argument("--output", choices=["table", "json"], default="table")
    scopes_revoke = scopes_subparsers.add_parser("revoke-lease")
    scopes_revoke.add_argument("lease_id")
    scopes_revoke.add_argument("--reason", required=True)
    scopes_revoke.add_argument("--output", choices=["table", "json"], default="table")

    events = subparsers.add_parser("events")
    events.add_argument("--target-type", default=None, dest="target_type")
    events.add_argument("--target-id", default=None, dest="target_id")
    events.add_argument("--limit", type=int, default=100)
    events.add_argument("--output", choices=["table", "json"], default="table")

    db = subparsers.add_parser("db")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_backup = db_sub.add_parser("backup")
    db_backup.add_argument("--path", default=None, dest="backup_path")
    db_backup.add_argument("--output", choices=["table", "json"], default="table")
    db_check = db_sub.add_parser("restore-check")
    db_check.add_argument("backup_path")
    db_check.add_argument("--output", choices=["table", "json"], default="table")

    runtime_tools = subparsers.add_parser("runtime-tools")
    rt_subparsers = runtime_tools.add_subparsers(dest="runtime_tools_command", required=True)
    rt_list = rt_subparsers.add_parser("list")
    rt_list.add_argument("--system-id", default=None, dest="system_id")
    rt_list.add_argument("--status", choices=["all", "planned", "in_progress", "available", "blocked", "deprecated"], default="all")
    rt_list.add_argument("--output", choices=["table", "json"], default="table")
    rt_show = rt_subparsers.add_parser("show")
    rt_show.add_argument("tool_id")
    rt_show.add_argument("--output", choices=["table", "json"], default="table")
    rt_check = rt_subparsers.add_parser("check")
    rt_check.add_argument("tool_id")
    rt_check.add_argument("--request-id", default=None, dest="request_id")
    rt_check.add_argument("--side-effect-level", default=None, dest="side_effect_level")
    rt_check.add_argument("--human-approved", action="store_true", dest="human_approved")
    rt_check.add_argument("--output", choices=["table", "json"], default="table")

    capabilities = subparsers.add_parser("capabilities")
    cap_subparsers = capabilities.add_subparsers(dest="cap_command", required=True)

    cap_list = cap_subparsers.add_parser("list")
    cap_list.add_argument("--status", choices=["all", "planned", "in_progress", "available", "blocked", "deprecated"], default="all")
    cap_list.add_argument("--system-id", default=None, dest="system_id")
    cap_list.add_argument("--output", choices=["table", "json"], default="table")

    cap_show = cap_subparsers.add_parser("show")
    cap_show.add_argument("capability_id")
    cap_show.add_argument("--output", choices=["table", "json"], default="table")

    cap_set = cap_subparsers.add_parser("set-status")
    cap_set.add_argument("capability_id")
    cap_set.add_argument("--to", choices=["planned", "available"], required=True, dest="to_status")
    cap_set.add_argument("--reason", required=True)
    cap_set.add_argument("--output", choices=["table", "json"], default="table")

    request = subparsers.add_parser("request")
    request_subparsers = request.add_subparsers(dest="request_command", required=True)

    request_create = request_subparsers.add_parser("create")
    request_create.add_argument("--objective", required=True)
    request_create.add_argument("--missing-capability", required=True, dest="missing_capability")
    request_create.add_argument("--business-impact", required=True, dest="business_impact")
    request_create.add_argument("--expected-behavior", required=True, dest="expected_behavior")
    request_create.add_argument("--acceptance-criteria", action="append", required=True, dest="acceptance_criteria")
    request_create.add_argument("--risk-class", choices=["low", "medium", "high", "critical"], required=True, dest="risk_class")
    request_create.add_argument("--priority", choices=["P0", "P1", "P2", "P3"], required=True)
    request_create.add_argument("--goal-ref", required=True, dest="goal_ref")
    request_create.add_argument("--output", choices=["table", "json"], default="table")

    request_list = request_subparsers.add_parser("list")
    request_list.add_argument("--status", choices=REQUEST_STATUS_CHOICES, default="submitted")
    request_list.add_argument("--limit", type=int, default=100)
    request_list.add_argument("--output", choices=["table", "json"], default="table")

    request_show = request_subparsers.add_parser("show")
    request_show.add_argument("request_id")
    request_show.add_argument("--output", choices=["table", "json"], default="table")

    request_transition = request_subparsers.add_parser("transition")
    request_transition.add_argument("request_id")
    request_transition.add_argument("--to", required=True, choices=REQUEST_STATUS_CHOICES[1:] + sorted(LIFECYCLE_ALIASES), dest="to_status")
    request_transition.add_argument("--reason", required=True)
    request_transition.add_argument("--output", choices=["table", "json"], default="table")

    repos = subparsers.add_parser("repos")
    repos_subparsers = repos.add_subparsers(dest="repos_command", required=True)
    repos_assigned = repos_subparsers.add_parser("assigned")
    repos_assigned.add_argument("--output", choices=["table", "json"], default="table")
    repos_list = repos_subparsers.add_parser("list")
    repos_list.add_argument("--output", choices=["table", "json"], default="table")
    repos_show = repos_subparsers.add_parser("show")
    repos_show.add_argument("repo_id")
    repos_show.add_argument("--output", choices=["table", "json"], default="table")

    work = subparsers.add_parser("work")
    work_subparsers = work.add_subparsers(dest="work_command", required=True)
    work_list = work_subparsers.add_parser("list")
    work_list.add_argument("--status", choices=REQUEST_STATUS_CHOICES, default="all")
    work_list.add_argument("--limit", type=int, default=100)
    work_list.add_argument("--output", choices=["table", "json"], default="table")
    work_show = work_subparsers.add_parser("show")
    work_show.add_argument("request_id")
    work_show.add_argument("--output", choices=["table", "json"], default="table")
    work_plan = work_subparsers.add_parser("plan")
    work_plan.add_argument("request_id")
    work_plan.add_argument("--repo", required=True, dest="repo_id")
    work_plan.add_argument("--branch", default=None)
    work_plan.add_argument("--assign", default=None, dest="assigned_agent_id")
    work_plan.add_argument("--reviewer", default=None, dest="reviewer_agent_id")
    work_plan.add_argument("--sanitized-summary", default=None, dest="sanitized_summary")
    work_plan.add_argument("--output", choices=["table", "json"], default="table")
    work_impl = work_subparsers.add_parser("set-implementation-context")
    work_impl.add_argument("request_id")
    work_impl.add_argument("--context-file", default=None, dest="context_file")
    work_impl.add_argument("--component", default=None)
    work_impl.add_argument("--entrypoint", action="append", default=[], dest="entrypoints")
    work_impl.add_argument("--likely-file", action="append", default=[], dest="likely_files")
    work_impl.add_argument("--do-not-touch", action="append", default=[], dest="do_not_touch")
    work_impl.add_argument("--interface", action="append", default=[], dest="interfaces")
    work_impl.add_argument("--acceptance-criteria", action="append", default=[], dest="acceptance_criteria")
    work_impl.add_argument("--test-command", action="append", default=[], dest="test_commands")
    work_impl.add_argument("--notes", default=None)
    work_impl.add_argument("--output", choices=["table", "json"], default="table")
    work_approve = work_subparsers.add_parser("approve-plan")
    work_approve.add_argument("request_id")
    work_approve.add_argument("--output", choices=["table", "json"], default="table")
    work_assign = work_subparsers.add_parser("assign")
    work_assign.add_argument("request_id")
    work_assign.add_argument("--agent", required=True, dest="agent_id")
    work_assign.add_argument("--output", choices=["table", "json"], default="table")
    work_transition = work_subparsers.add_parser("transition")
    work_transition.add_argument("request_id")
    work_transition.add_argument("--to", required=True, choices=REQUEST_STATUS_CHOICES[1:] + sorted(LIFECYCLE_ALIASES), dest="to_status")
    work_transition.add_argument("--reason", required=True)
    work_transition.add_argument("--override", action="store_true")
    work_transition.add_argument("--approved-by", default=None, dest="approved_by", help="second sw-techlead/nexus approver required for manual override")
    work_transition.add_argument("--output", choices=["table", "json"], default="table")
    work_ev = work_subparsers.add_parser("submit-evidence")
    work_ev.add_argument("request_id")
    work_ev.add_argument("--kind", required=True)
    work_ev.add_argument("--ref", default=None)
    work_ev.add_argument("--summary", required=True)
    work_ev.add_argument("--output", choices=["table", "json"], default="table")

    github = subparsers.add_parser("github")
    github_subparsers = github.add_subparsers(dest="github_command", required=True)
    gh_issue = github_subparsers.add_parser("issue")
    gh_issue_sub = gh_issue.add_subparsers(dest="github_issue_command", required=True)
    gh_issue_create = gh_issue_sub.add_parser("create")
    gh_issue_create.add_argument("request_id")
    gh_issue_create.add_argument("--title", default=None)
    gh_issue_create.add_argument("--label", action="append", default=[], dest="labels")
    gh_issue_create.add_argument("--assignee", action="append", default=[], dest="assignees")
    gh_issue_create.add_argument("--dry-run", action="store_true", dest="dry_run")
    gh_issue_create.add_argument("--output", choices=["table", "json"], default="table")
    gh_issue_sync = gh_issue_sub.add_parser("sync")
    gh_issue_sync.add_argument("request_id")
    gh_issue_sync.add_argument("--output", choices=["table", "json"], default="table")

    gh_pr = github_subparsers.add_parser("pr")
    gh_pr_sub = gh_pr.add_subparsers(dest="github_pr_command", required=True)
    gh_pr_link = gh_pr_sub.add_parser("link")
    gh_pr_link.add_argument("request_id")
    gh_pr_link.add_argument("--url", required=True)
    gh_pr_link.add_argument("--output", choices=["table", "json"], default="table")
    gh_pr_sync = gh_pr_sub.add_parser("sync")
    gh_pr_sync.add_argument("request_id")
    gh_pr_sync.add_argument("--output", choices=["table", "json"], default="table")

    gh_status = github_subparsers.add_parser("status")
    gh_status.add_argument("request_id")
    gh_status.add_argument("--output", choices=["table", "json"], default="table")
    gh_alerts = github_subparsers.add_parser("alerts")
    gh_alerts.add_argument("--all", action="store_true", dest="include_resolved")
    gh_alerts.add_argument("--limit", type=int, default=50)
    gh_alerts.add_argument("--output", choices=["table", "json"], default="table")
    gh_sync = github_subparsers.add_parser("sync")
    gh_sync.add_argument("request_id")
    gh_sync.add_argument("--output", choices=["table", "json"], default="table")
    gh_repos = github_subparsers.add_parser("repos")
    gh_repos_sub = gh_repos.add_subparsers(dest="github_repos_command", required=True)
    gh_repos_list = gh_repos_sub.add_parser("list")
    gh_repos_list.add_argument("--output", choices=["table", "json"], default="table")
    gh_repos_sync = gh_repos_sub.add_parser("sync")
    gh_repos_sync.add_argument("--output", choices=["table", "json"], default="table")

    reviews = subparsers.add_parser("reviews")
    reviews_subparsers = reviews.add_subparsers(dest="reviews_command", required=True)
    reviews_list = reviews_subparsers.add_parser("list")
    reviews_list.add_argument("--status", choices=REQUEST_STATUS_CHOICES, default="in-review")
    reviews_list.add_argument("--limit", type=int, default=100)
    reviews_list.add_argument("--output", choices=["table", "json"], default="table")
    reviews_submit = reviews_subparsers.add_parser("submit")
    reviews_submit.add_argument("request_id")
    reviews_submit.add_argument("--verdict", required=True, choices=["approved", "changes-requested", "rejected"])
    reviews_submit.add_argument("--summary", required=True)
    reviews_submit.add_argument("--output", choices=["table", "json"], default="table")

    return parser


def run(
    argv: list[str],
    *,
    env: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    env = dict(env or os.environ)
    out = out or sys.stdout
    err = err or sys.stderr

    parser = build_parser()

    try:
        api = ApiClient.from_env(env)
        sessions = SessionStore(env)
        args = parser.parse_args(argv)
        if args.command == "auth":
            return _run_auth(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "rotate-token":
            return _run_rotate_token(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "context":
            return _run_context(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "systems":
            return _run_systems(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "goals":
            return _run_goals(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "scopes":
            return _run_scopes(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "events":
            return _run_events(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "db":
            return _run_db(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "runtime-tools":
            return _run_runtime_tools(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "capabilities":
            return _run_capabilities(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "request":
            return _run_request(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "repos":
            return _run_repos(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "work":
            return _run_work(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "github":
            return _run_github(args, api=api, sessions=sessions, env=env, out=out)
        if args.command == "reviews":
            return _run_reviews(args, api=api, sessions=sessions, env=env, out=out)
        raise NexusError("NX-VAL-001", "unknown command")
    except NexusError as exc:
        err.write(f"{exc.code}: {exc.message}\n")
        return int(exc.exit_code or 10)


def _run_auth(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    token = args.agent_token or env.get("NEXUS_AGENT_TOKEN") or _resolve_seed_token(env)
    if not token:
        raise NexusError("NX-VAL-002", "missing agent token (--agent-token or NEXUS_AGENT_TOKEN)")
    auth_response = api.auth(agent_token=token)
    sessions.save_auth_response(auth_response)
    _emit_auth(out=out, output=args.output, payload=auth_response)
    return EXIT_SUCCESS


def _normalize_lifecycle_status(value: str) -> str:
    return LIFECYCLE_ALIASES.get(value, value)


def _run_rotate_token(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    payload = api.rotate_agent_token(session=session, agent_id=args.agent_id, new_token=args.new_token)
    _emit_simple_result(out=out, output=args.output, payload=payload)
    return EXIT_SUCCESS


def _run_context(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    payload = api.get_context(session=session)
    _emit_context(out=out, output=args.output, payload=payload)
    return EXIT_SUCCESS


def _run_systems(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.systems_command == "list":
        payload = api.list_systems(session=session, status=args.status)
        _emit_systems_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.systems_command == "show":
        payload = api.show_system(session=session, system_id=args.system_id)
        _emit_system_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown systems command")


def _run_goals(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.goals_command == "list":
        payload = api.list_goals(session=session, system_id=args.system_id, status=args.status, limit=args.limit)
        _emit_goals_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.goals_command == "show":
        payload = api.show_goal(session=session, goal_id=args.goal_id)
        _emit_goal_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.goals_command == "create":
        payload = api.create_goal(
            session=session,
            goal_id=_require_text(args.goal_id, field="goal-id"),
            system_id=_require_text(args.system_id, field="system-id") if args.system_id else None,
            title=_require_text(args.title, field="title"),
            objective=_require_text(args.objective, field="objective"),
            success_metrics=[_require_text(item, field="success-metric") for item in args.success_metrics],
            constraints=[_require_text(item, field="constraint") for item in args.constraints],
            risk_class=args.risk_class,
            priority=args.priority,
            owner_agent_id=_require_text(args.owner_agent_id, field="owner-agent-id") if args.owner_agent_id else None,
            status=args.status,
            parent_goal_id=args.parent_goal_id,
        )
        _emit_goal_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.goals_command == "update-status":
        payload = api.update_goal_status(
            session=session,
            goal_id=args.goal_id,
            to=args.to_status,
            reason=_require_text(args.reason, field="reason"),
        )
        _emit_goal_status(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown goals command")


def _run_scopes(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.scopes_command == "list":
        payload = api.list_scopes(session=session, agent_id=args.agent_id)
        _emit_scopes(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.scopes_command == "effective":
        payload = api.effective_scopes(session=session)
        _emit_scopes(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.scopes_command == "lease":
        payload = api.create_scope_lease(session=session, agent_id=args.agent_id, scope=args.scope, system_id=args.system_id, resource_pattern=args.resource_pattern, request_id=args.request_id, reason=args.reason, ttl_minutes=args.ttl_minutes, approved_by=args.approved_by)
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.scopes_command == "leases":
        payload = api.list_scope_leases(session=session, agent_id=args.agent_id, active_only=not args.include_inactive)
        _emit_scope_leases(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.scopes_command == "revoke-lease":
        payload = api.revoke_scope_lease(session=session, lease_id=args.lease_id, reason=args.reason)
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown scopes command")


def _run_events(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    payload = api.event_log(session=session, target_type=args.target_type, target_id=args.target_id, limit=args.limit)
    _emit_events(out=out, output=args.output, payload=payload)
    return EXIT_SUCCESS


def _run_db(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.db_command == "backup":
        payload = api.db_backup(session=session, backup_path=args.backup_path)
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.db_command == "restore-check":
        payload = api.db_restore_check(session=session, backup_path=args.backup_path)
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown db command")


def _run_runtime_tools(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.runtime_tools_command == "list":
        payload = api.list_runtime_tools(session=session, system_id=args.system_id, status=args.status)
        _emit_runtime_tools_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.runtime_tools_command == "show":
        payload = api.show_runtime_tool(session=session, tool_id=args.tool_id)
        _emit_runtime_tool_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.runtime_tools_command == "check":
        payload = api.runtime_tool_check(session=session, tool_id=args.tool_id, request_id=args.request_id, side_effect_level=args.side_effect_level, human_approved=args.human_approved)
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown runtime-tools command")


def _run_capabilities(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    if args.cap_command == "list":
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        payload = api.list_capabilities(session=session, status=args.status, system_id=args.system_id)
        _emit_capability_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.cap_command == "show":
        _validate_capability_id(args.capability_id)
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        payload = api.show_capability(session=session, capability_id=args.capability_id)
        _emit_capability_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.cap_command == "set-status":
        _validate_capability_id(args.capability_id)
        reason = args.reason.strip()
        if len(reason) < 10 or len(reason) > 500:
            raise NexusError("NX-VAL-001", "--reason must be between 10 and 500 chars")
        if args.to_status != "available":
            raise NexusError("NX-PRECONDITION-003", "MVP only allows transition to available")
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        if session.role != "sw-techlead":
            raise NexusError("NX-PERM-001", "only sw-techlead may execute set-status")
        payload = api.set_status(session=session, capability_id=args.capability_id, to=args.to_status, reason=reason)
        _emit_set_status(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    raise NexusError("NX-VAL-001", "unknown capabilities command")


def _run_request(
    args: argparse.Namespace,
    *,
    api: ApiClient,
    sessions: SessionStore,
    env: Mapping[str, str],
    out: TextIO,
) -> int:
    if args.request_command == "list":
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        payload = api.list_requests(session=session, status=args.status, limit=args.limit)
        _emit_request_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.request_command == "show":
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        payload = api.show_request(session=session, request_id=args.request_id)
        _emit_request_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.request_command == "create":
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        if session.role not in {"trading-strategist", "trading-sentinel"}:
            raise NexusError("NX-PERM-001", "only trading-strategist or trading-sentinel may create request")

        objective = _require_text(args.objective, field="objective")
        missing_capability = _require_text(args.missing_capability, field="missing-capability")
        business_impact = _require_text(args.business_impact, field="business-impact")
        expected_behavior = _require_text(args.expected_behavior, field="expected-behavior")
        goal_ref = _require_text(args.goal_ref, field="goal-ref")
        criteria = [_require_text(item, field="acceptance-criteria") for item in args.acceptance_criteria]

        payload = api.create_request(
            session=session,
            objective=objective,
            missing_capability=missing_capability,
            business_impact=business_impact,
            expected_behavior=expected_behavior,
            acceptance_criteria=criteria,
            risk_class=args.risk_class,
            priority=args.priority,
            goal_ref=goal_ref,
        )
        _emit_request_create(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.request_command == "transition":
        session = _load_session_for_command(api=api, sessions=sessions, env=env)
        if session.role not in {"nexus", "trading-strategist"}:
            raise NexusError("NX-PERM-001", "only nexus or trading-strategist may transition requests")
        reason = _require_text(args.reason, field="reason")
        payload = api.transition_request(
            session=session,
            request_id=args.request_id,
            to=_normalize_lifecycle_status(args.to_status),
            reason=reason,
        )
        _emit_request_transition(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    raise NexusError("NX-VAL-001", "unknown request command")



def _validate_capability_id(value: str) -> None:
    if not CAPABILITY_ID_PATTERN.match(value):
        raise NexusError("NX-VAL-001", "invalid capability id, expected format F-001")


def _load_session_for_command(*, api: ApiClient, sessions: SessionStore, env: Mapping[str, str]):
    token = env.get("NEXUS_AGENT_TOKEN") or _resolve_seed_token(env)
    if token:
        auth_response = api.auth(agent_token=token)
        return sessions.save_auth_response(auth_response)
    try:
        return sessions.load_active()
    except NexusError as exc:
        if exc.code not in {"NX-PRECONDITION-001", "NX-PRECONDITION-002"}:
            raise
        raise


def _emit_context(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    agent = payload.get("agent", {})
    actions = ", ".join(payload.get("allowed_actions", []))
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("agent_id", str(agent.get("agent_id", ""))),
            ("role", str(agent.get("role", ""))),
            ("default_system_id", str(agent.get("default_system_id", agent.get("default_system_id", "")))),
            ("domain", str(agent.get("domain", ""))),
            ("allowed_actions", actions),
        ],
    )
    section_emitters = [
        ("systems", lambda value: _emit_systems_list(out=out, output="table", payload={"systems": value})),
        ("goals", lambda value: _emit_goals_list(out=out, output="table", payload={"goals": value})),
        ("capabilities", lambda value: _emit_capability_list(out=out, output="table", payload={"capabilities": value})),
        ("runtime_tools", lambda value: _emit_runtime_tools_list(out=out, output="table", payload={"runtime_tools": value})),
        ("requests", lambda value: _emit_request_list(out=out, output="table", payload={"requests": value})),
        ("work", lambda value: _emit_work_list(out=out, output="table", payload={"work": value})),
        ("assigned_work", lambda value: _emit_work_list(out=out, output="table", payload={"work": value})),
        ("assigned_reviews", lambda value: _emit_reviews_list(out=out, output="table", payload={"reviews": value})),
        ("repositories", lambda value: _emit_repos(out=out, output="table", payload={"repositories": value})),
        ("assigned_repositories", lambda value: _emit_repos(out=out, output="table", payload={"repositories": value})),
        ("reviews", lambda value: _emit_reviews_list(out=out, output="table", payload={"reviews": value})),
    ]
    for key, emitter in section_emitters:
        if key in payload:
            out.write(f"\n{key}\n")
            emitter(payload.get(key, []))


def _run_repos(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.repos_command == "assigned":
        payload = api.list_repos(session=session, assigned=True)
        _emit_repos(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.repos_command == "list":
        payload = api.list_repos(session=session, assigned=False)
        _emit_repos(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.repos_command == "show":
        payload = api.show_repo(session=session, repo_id=args.repo_id)
        _emit_repo_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown repos command")


def _run_work(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.work_command == "list":
        payload = api.list_work(session=session, status=args.status, limit=args.limit)
        _emit_work_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "show":
        payload = api.show_work(session=session, request_id=args.request_id)
        _emit_work_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "plan":
        payload = api.plan_work(session=session, request_id=args.request_id, repo_id=args.repo_id, branch=args.branch, assigned_agent_id=args.assigned_agent_id, reviewer_agent_id=args.reviewer_agent_id, sanitized_summary=args.sanitized_summary)
        _emit_work_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "set-implementation-context":
        implementation_context = _build_implementation_context_from_args(args)
        payload = api.set_implementation_context(session=session, request_id=args.request_id, implementation_context=implementation_context)
        _emit_work_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "approve-plan":
        payload = api.approve_work_plan(session=session, request_id=args.request_id)
        _emit_work_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "assign":
        payload = api.assign_work(session=session, request_id=args.request_id, agent_id=args.agent_id)
        _emit_work_show(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "transition":
        payload = api.transition_work(session=session, request_id=args.request_id, to=_normalize_lifecycle_status(args.to_status), reason=_require_text(args.reason, field="reason"), override=bool(args.override), approved_by=args.approved_by)
        _emit_request_transition(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.work_command == "submit-evidence":
        payload = api.submit_work_evidence(session=session, request_id=args.request_id, kind=args.kind, ref=args.ref, summary=args.summary)
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown work command")


def _run_github(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.github_command == "issue":
        if args.github_issue_command == "create":
            payload = api.github_issue_create(session=session, request_id=args.request_id, title=args.title, labels=args.labels, assignees=args.assignees, dry_run=args.dry_run)
            _emit_github_result(out=out, output=args.output, payload=payload)
            return EXIT_SUCCESS
        if args.github_issue_command == "sync":
            payload = api.github_issue_sync(session=session, request_id=args.request_id)
            _emit_github_result(out=out, output=args.output, payload=payload)
            return EXIT_SUCCESS
    if args.github_command == "pr":
        if args.github_pr_command == "link":
            payload = api.github_pr_link(session=session, request_id=args.request_id, url=_require_text(args.url, field="url"))
            _emit_github_result(out=out, output=args.output, payload=payload)
            return EXIT_SUCCESS
        if args.github_pr_command == "sync":
            payload = api.github_pr_sync(session=session, request_id=args.request_id)
            _emit_github_result(out=out, output=args.output, payload=payload)
            return EXIT_SUCCESS
    if args.github_command == "status":
        payload = api.github_status(session=session, request_id=args.request_id)
        _emit_github_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.github_command == "alerts":
        payload = api.github_alerts(session=session, unresolved_only=not args.include_resolved, limit=args.limit)
        _emit_github_alerts(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.github_command == "sync":
        payload = api.github_sync(session=session, request_id=args.request_id)
        _emit_github_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.github_command == "repos":
        if session.role not in {"sw-techlead", "nexus"}:
            raise NexusError("NX-PERM-001", "only sw-techlead or nexus may access global GitHub repositories")
        if args.github_repos_command == "list":
            payload = api.github_repos_list(session=session)
            _emit_github_result(out=out, output=args.output, payload=payload)
            return EXIT_SUCCESS
        if args.github_repos_command == "sync":
            payload = api.github_repos_sync(session=session)
            _emit_github_result(out=out, output=args.output, payload=payload)
            return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown github command")


def _run_reviews(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    session = _load_session_for_command(api=api, sessions=sessions, env=env)
    if args.reviews_command == "list":
        payload = api.list_reviews(session=session, status=args.status, limit=args.limit)
        _emit_reviews_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    if args.reviews_command == "submit":
        payload = api.submit_review(session=session, request_id=args.request_id, verdict=args.verdict, summary=_require_text(args.summary, field="summary"))
        _emit_simple_result(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS
    raise NexusError("NX-VAL-001", "unknown reviews command")


def _build_implementation_context_from_args(args: argparse.Namespace) -> dict:
    context: dict = {}
    if args.context_file:
        try:
            context = json.loads(Path(args.context_file).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise NexusError("NX-VAL-001", f"invalid implementation context json: {exc}")
        except OSError as exc:
            raise NexusError("NX-VAL-001", f"could not read implementation context file: {exc}")
        if not isinstance(context, dict):
            raise NexusError("NX-VAL-001", "implementation context file must contain a JSON object")
    if args.component:
        context["component"] = args.component
    if args.entrypoints:
        context["entrypoints"] = args.entrypoints
    if args.likely_files:
        context["likely_files"] = args.likely_files
    if args.do_not_touch:
        context["do_not_touch"] = args.do_not_touch
    if args.interfaces:
        context["interfaces"] = [{"name": item, "signature": item} for item in args.interfaces]
    if args.acceptance_criteria:
        context["acceptance_criteria"] = args.acceptance_criteria
    if args.test_commands:
        context["test_commands"] = args.test_commands
    if args.notes:
        context["notes"] = args.notes
    if not context:
        raise NexusError("NX-VAL-001", "missing implementation context data")
    return context


def _emit_github_alerts(*, out: TextIO, output: str, payload: dict) -> None:
    alerts = payload.get("alerts", [])
    if output == "json":
        write_json(out, payload)
        return
    rows = [[item.get("alert_id", ""), item.get("severity", ""), item.get("kind", ""), item.get("request_id", ""), item.get("message", ""), item.get("created_at", "")] for item in alerts]
    write_table(out, ["alert_id", "severity", "kind", "request_id", "message", "created_at"], rows)


def _emit_auth(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok"))),
            ("auth_id", str(payload.get("auth_id", ""))),
            ("session_id", str(payload.get("session_id", ""))),
            ("agent_id", str(payload.get("agent_id", ""))),
            ("role", str(payload.get("role", ""))),
            ("default_system_id", str(payload.get("default_system_id", ""))),
            ("domain", str(payload.get("domain", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )
    out.write("\n")
    _emit_capability_list(out=out, output="table", payload={"capabilities": payload.get("capabilities", [])})


def _emit_capability_list(*, out: TextIO, output: str, payload: dict) -> None:
    capabilities = payload.get("capabilities", payload if isinstance(payload, list) else [])
    if output == "json":
        if isinstance(payload, dict):
            write_json(out, payload)
        else:
            write_json(out, {"capabilities": capabilities})
        return
    rows = [[c.get("capability_id", ""), c.get("title", ""), c.get("status", "")] for c in capabilities]
    write_table(out, ["capability_id", "title", "status"], rows)


def _emit_capability_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("capability_id", str(payload.get("capability_id", ""))),
            ("title", str(payload.get("title", ""))),
            ("status", str(payload.get("status", ""))),
            ("subfunctions", ", ".join(payload.get("subfunctions", []))),
            ("requirements", ", ".join(payload.get("requirements", []))),
        ],
    )


def _emit_set_status(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("event_id", str(payload.get("event_id", ""))),
            ("capability_id", str(payload.get("capability_id", ""))),
            ("old_status", str(payload.get("old_status", ""))),
            ("new_status", str(payload.get("new_status", ""))),
            ("reason", str(payload.get("reason", ""))),
            ("agent_id", str(payload.get("agent_id", ""))),
            ("default_system_id", str(payload.get("default_system_id", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


def _emit_request_create(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    criteria = payload.get("acceptance_criteria", [])
    criteria_display = " | ".join(str(item) for item in criteria) if isinstance(criteria, list) else ""
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("request_id", str(payload.get("request_id", ""))),
            ("status", str(payload.get("status", ""))),
            ("objective", str(payload.get("objective", ""))),
            ("missing_capability", str(payload.get("missing_capability", ""))),
            ("business_impact", str(payload.get("business_impact", ""))),
            ("expected_behavior", str(payload.get("expected_behavior", ""))),
            ("acceptance_criteria", criteria_display),
            ("risk_class", str(payload.get("risk_class", ""))),
            ("priority", str(payload.get("priority", ""))),
            ("goal_ref", str(payload.get("goal_ref", ""))),
            ("agent_id", str(payload.get("agent_id", ""))),
            ("default_system_id", str(payload.get("default_system_id", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


def _emit_request_list(*, out: TextIO, output: str, payload: dict) -> None:
    requests = payload.get("requests", payload if isinstance(payload, list) else [])
    if output == "json":
        if isinstance(payload, dict):
            write_json(out, payload)
        else:
            write_json(out, {"requests": requests})
        return
    rows = [[item.get("request_id", ""), item.get("status", ""), item.get("priority", ""), item.get("risk_class", "")] for item in requests]
    write_table(out, ["request_id", "status", "priority", "risk_class"], rows)




def _emit_request_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    criteria = payload.get("acceptance_criteria", [])
    criteria_display = " | ".join(str(item) for item in criteria) if isinstance(criteria, list) else ""
    write_key_values(
        out,
        [
            ("request_id", str(payload.get("request_id", ""))),
            ("status", str(payload.get("status", ""))),
            ("objective", str(payload.get("objective", ""))),
            ("missing_capability", str(payload.get("missing_capability", ""))),
            ("business_impact", str(payload.get("business_impact", ""))),
            ("expected_behavior", str(payload.get("expected_behavior", ""))),
            ("acceptance_criteria", criteria_display),
            ("priority", str(payload.get("priority", ""))),
            ("risk_class", str(payload.get("risk_class", ""))),
            ("goal_ref", str(payload.get("goal_ref", ""))),
            ("updated_at", str(payload.get("updated_at", ""))),
        ],
    )


def _emit_request_transition(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("request_id", str(payload.get("request_id", ""))),
            ("from_status", str(payload.get("from_status", ""))),
            ("to_status", str(payload.get("to_status", ""))),
            ("reason", str(payload.get("reason", ""))),
            ("event_id", str(payload.get("event_id", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


def _emit_repos(*, out: TextIO, output: str, payload: dict) -> None:
    repos = payload.get("repositories", payload if isinstance(payload, list) else [])
    if output == "json":
        write_json(out, payload if isinstance(payload, dict) else {"repositories": repos})
        return
    rows = [[r.get("repo_id", ""), r.get("system_id", ""), r.get("status", ""), r.get("default_branch", ""), r.get("url", "")] for r in repos]
    write_table(out, ["repo_id", "system_id", "status", "branch", "url"], rows)


def _emit_repo_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(out, [("repo_id", str(payload.get("repo_id", ""))), ("name", str(payload.get("name", ""))), ("url", str(payload.get("url", ""))), ("system_id", str(payload.get("system_id", ""))), ("status", str(payload.get("status", ""))), ("default_branch", str(payload.get("default_branch", ""))), ("allowed_agent_roles", ", ".join(str(x) for x in payload.get("allowed_agent_roles", [])))])


def _emit_work_list(*, out: TextIO, output: str, payload: dict) -> None:
    work = payload.get("work", payload if isinstance(payload, list) else [])
    if output == "json":
        write_json(out, payload if isinstance(payload, dict) else {"work": work})
        return
    rows = []
    for w in work:
        pr = ((w.get("github") or {}).get("pull_request") or {})
        rows.append([w.get("request_id", ""), w.get("status", ""), w.get("target_repo_id", ""), w.get("assigned_agent_id", ""), w.get("reviewer_agent_id", ""), w.get("branch", ""), pr.get("url", "")])
    write_table(out, ["request_id", "status", "repo", "builder", "reviewer", "branch", "pr"], rows)


def _emit_work_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    criteria = payload.get("acceptance_criteria", [])
    criteria_display = " | ".join(str(item) for item in criteria) if isinstance(criteria, list) else ""
    write_key_values(out, [
        ("request_id", str(payload.get("request_id", ""))),
        ("status", str(payload.get("status", ""))),
        ("objective", str(payload.get("objective", ""))),
        ("missing_capability", str(payload.get("missing_capability", ""))),
        ("acceptance_criteria", criteria_display),
        ("target_repo_id", str(payload.get("target_repo_id", ""))),
        ("assigned_agent_id", str(payload.get("assigned_agent_id", ""))),
        ("reviewer_agent_id", str(payload.get("reviewer_agent_id", ""))),
        ("branch", str(payload.get("branch", ""))),
        ("github_issue", str(((payload.get("github") or {}).get("issue") or {}).get("url", ""))),
        ("github_pr", str(((payload.get("github") or {}).get("pull_request") or {}).get("url", ""))),
        ("sanitized_summary", str(payload.get("sanitized_summary", ""))),
        ("implementation_context_approved_by", str(payload.get("implementation_context_approved_by", ""))),
        ("implementation_context_approved_at", str(payload.get("implementation_context_approved_at", ""))),
    ])
    if isinstance(payload.get("implementation_context"), dict) and payload["implementation_context"]:
        out.write("\nimplementation_context\n")
        write_json(out, payload["implementation_context"])


def _emit_reviews_list(*, out: TextIO, output: str, payload: dict) -> None:
    reviews = payload.get("reviews", payload if isinstance(payload, list) else [])
    if output == "json":
        write_json(out, payload if isinstance(payload, dict) else {"reviews": reviews})
        return
    rows = [[r.get("request_id", ""), r.get("status", ""), r.get("target_repo_id", ""), (((r.get("github") or {}).get("pull_request") or {}).get("url", "")), r.get("assigned_agent_id", ""), r.get("reviewer_agent_id", "")] for r in reviews]
    write_table(out, ["request_id", "status", "repo", "pr", "builder", "reviewer"], rows)


def _emit_github_result(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    if payload.get("dry_run") and payload.get("body"):
        out.write(str(payload.get("body")))
        return
    github = payload.get("github") or {}
    issue = github.get("issue") or payload.get("issue") or {}
    pr = github.get("pull_request") or {}
    rows = [("ok", str(payload.get("ok", True))), ("request_id", str(payload.get("request_id", "")))]
    if issue:
        rows.extend([("issue", str(issue.get("url", ""))), ("issue_state", str(issue.get("state", "")))])
    if pr:
        rows.extend([("pr", str(pr.get("url", ""))), ("review_state", str(pr.get("review_state", ""))), ("checks_state", str(pr.get("checks_state", ""))), ("policy_state", str(pr.get("policy_state", "")))])
    if payload.get("repositories") is not None:
        write_json(out, payload)
        return
    write_key_values(out, rows)


def _emit_simple_result(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(out, [(str(k), str(v)) for k, v in payload.items() if not isinstance(v, (list, dict))])


def _require_text(value: str, *, field: str) -> str:
    text = value.strip()
    if not text:
        raise NexusError("NX-VAL-001", f"--{field} must not be empty")
    return text


def _resolve_seed_token(env: Mapping[str, str]) -> str | None:
    token_file = Path(env.get("NEXUSCTL_SEED_TOKENS_FILE", "/home/node/.openclaw/nexusctl/seed_tokens.env")).expanduser()
    tokens = _read_seed_tokens(token_file)
    if not tokens:
        return None

    agent_id = _resolve_agent_id(env)
    if not agent_id:
        return None

    candidates = [agent_id]
    if agent_id.endswith("-01"):
        candidates.append(agent_id[:-3])
    else:
        candidates.append(f"{agent_id}-01")
    for candidate in candidates:
        token = tokens.get(candidate)
        if token:
            return token
    return None


def _resolve_agent_id(env: Mapping[str, str]) -> str | None:
    explicit = env.get("NEXUSCTL_AGENT_ID") or env.get("OPENCLAW_AGENT_ID")
    if explicit:
        return explicit.strip() or None

    agent_dir = env.get("NEXUSCTL_AGENT_DIR")
    if not agent_dir:
        return None
    path = Path(agent_dir).expanduser().resolve()
    if path.name == "agent" and path.parent.name:
        return path.parent.name
    return path.name or None


def _read_seed_tokens(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    tokens: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            tokens[key] = value
    return tokens


def _emit_systems_list(*, out: TextIO, output: str, payload: dict) -> None:
    systems = payload.get("systems", payload if isinstance(payload, list) else [])
    if output == "json":
        write_json(out, payload if isinstance(payload, dict) else {"systems": systems})
        return
    rows = [[s.get("system_id", ""), s.get("name", ""), s.get("status", ""), s.get("risk_level", "")] for s in systems]
    write_table(out, ["system_id", "name", "status", "risk"], rows)


def _emit_system_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("system_id", str(payload.get("system_id", ""))),
            ("name", str(payload.get("name", ""))),
            ("purpose", str(payload.get("purpose", ""))),
            ("owner_agent_id", str(payload.get("owner_agent_id", ""))),
            ("status", str(payload.get("status", ""))),
            ("risk_level", str(payload.get("risk_level", ""))),
        ],
    )


def _emit_goals_list(*, out: TextIO, output: str, payload: dict) -> None:
    goals = payload.get("goals", payload if isinstance(payload, list) else [])
    if output == "json":
        write_json(out, payload if isinstance(payload, dict) else {"goals": goals})
        return
    rows = [[g.get("goal_id", ""), g.get("system_id", ""), g.get("title", ""), g.get("status", ""), g.get("priority", "")] for g in goals]
    write_table(out, ["goal_id", "system_id", "title", "status", "priority"], rows)


def _emit_goal_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("goal_id", str(payload.get("goal_id", ""))),
            ("system_id", str(payload.get("system_id", ""))),
            ("title", str(payload.get("title", ""))),
            ("objective", str(payload.get("objective", ""))),
            ("status", str(payload.get("status", ""))),
            ("priority", str(payload.get("priority", ""))),
            ("risk_class", str(payload.get("risk_class", ""))),
            ("owner_agent_id", str(payload.get("owner_agent_id", ""))),
            ("success_metrics", " | ".join(str(item) for item in payload.get("success_metrics", []))),
            ("constraints", " | ".join(str(item) for item in payload.get("constraints", []))),
        ],
    )


def _emit_goal_status(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("event_id", str(payload.get("event_id", ""))),
            ("goal_id", str(payload.get("goal_id", ""))),
            ("from_status", str(payload.get("from_status", ""))),
            ("to_status", str(payload.get("to_status", ""))),
            ("reason", str(payload.get("reason", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


def _emit_scopes(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    scopes = payload.get("scopes", [])
    rows = []
    for item in scopes:
        rows.append([
            str(item.get("agent_id", payload.get("agent_id", "")) or ""),
            str(item.get("role", payload.get("role", "")) or ""),
            str(item.get("system_id", "")),
            str(item.get("scope", "")),
            str(item.get("resource_pattern", "*")),
        ])
    write_table(out, ["agent_id", "role", "system_id", "scope", "resource"], rows)


def _emit_scope_leases(*, out: TextIO, output: str, payload: dict) -> None:
    leases = payload.get("leases", [])
    if output == "json":
        write_json(out, payload)
        return
    rows = [[item.get("lease_id", ""), item.get("agent_id", ""), item.get("system_id", ""), item.get("scope", ""), item.get("resource_pattern", ""), item.get("expires_at", ""), item.get("revoked_at", "")] for item in leases]
    write_table(out, ["lease_id", "agent_id", "system_id", "scope", "resource", "expires_at", "revoked_at"], rows)


def _emit_events(*, out: TextIO, output: str, payload: dict) -> None:
    events = payload.get("events", [])
    if output == "json":
        write_json(out, payload)
        return
    rows = [[item.get("event_id", ""), item.get("event_type", ""), item.get("actor_agent_id", ""), item.get("target_type", ""), item.get("target_id", ""), item.get("created_at", "")] for item in events]
    write_table(out, ["event_id", "event_type", "actor", "target_type", "target_id", "created_at"], rows)


def _emit_runtime_tools_list(*, out: TextIO, output: str, payload: dict) -> None:
    tools = payload.get("runtime_tools", payload if isinstance(payload, list) else [])
    if output == "json":
        write_json(out, payload if isinstance(payload, dict) else {"runtime_tools": tools})
        return
    rows = [
        [
            t.get("tool_id", ""),
            t.get("system_id", ""),
            t.get("status", ""),
            t.get("side_effect_level", ""),
            t.get("required_scope", ""),
        ]
        for t in tools
    ]
    write_table(out, ["tool_id", "system_id", "status", "side_effect", "required_scope"], rows)


def _emit_runtime_tool_show(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("tool_id", str(payload.get("tool_id", ""))),
            ("system_id", str(payload.get("system_id", ""))),
            ("capability_id", str(payload.get("capability_id", ""))),
            ("kind", str(payload.get("kind", ""))),
            ("mode", str(payload.get("mode", ""))),
            ("status", str(payload.get("status", ""))),
            ("side_effect_level", str(payload.get("side_effect_level", ""))),
            ("required_scope", str(payload.get("required_scope", ""))),
            ("requires_human_approval", str(payload.get("requires_human_approval", ""))),
            ("allowed_roles", ", ".join(str(item) for item in payload.get("allowed_roles", []))),
        ],
    )
