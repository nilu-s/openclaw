from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Mapping, TextIO

from nexusctl.api import ApiClient
from nexusctl.errors import EXIT_SUCCESS, NexusError
from nexusctl.output import write_json, write_key_values, write_table
from nexusctl.session import SessionStore

CAPABILITY_ID_PATTERN = re.compile(r"^F-[0-9]{3,}$")


class NexusArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover
        raise NexusError("NX-VAL-001", message)


def build_parser() -> argparse.ArgumentParser:
    parser = NexusArgumentParser(prog="nexusctl")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth")
    auth.add_argument("--agent-token")
    auth.add_argument("--output", choices=["table", "json"], default="table")

    capabilities = subparsers.add_parser("capabilities")
    cap_subparsers = capabilities.add_subparsers(dest="cap_command", required=True)

    cap_list = cap_subparsers.add_parser("list")
    cap_list.add_argument("--status", choices=["all", "planned", "available"], default="all")
    cap_list.add_argument("--output", choices=["table", "json"], default="table")

    cap_show = cap_subparsers.add_parser("show")
    cap_show.add_argument("capability_id")
    cap_show.add_argument("--output", choices=["table", "json"], default="table")

    cap_set = cap_subparsers.add_parser("set-status")
    cap_set.add_argument("capability_id")
    cap_set.add_argument("--to", choices=["planned", "available"], required=True, dest="to_status")
    cap_set.add_argument("--reason", required=True)
    cap_set.add_argument("--output", choices=["table", "json"], default="table")

    handoff = subparsers.add_parser("handoff")
    handoff_subparsers = handoff.add_subparsers(dest="handoff_command", required=True)

    handoff_submit = handoff_subparsers.add_parser("submit")
    handoff_submit.add_argument("--objective", required=True)
    handoff_submit.add_argument("--missing-capability", required=True, dest="missing_capability")
    handoff_submit.add_argument("--business-impact", required=True, dest="business_impact")
    handoff_submit.add_argument("--expected-behavior", required=True, dest="expected_behavior")
    handoff_submit.add_argument("--acceptance-criteria", action="append", required=True, dest="acceptance_criteria")
    handoff_submit.add_argument("--risk-class", choices=["low", "medium", "high", "critical"], required=True, dest="risk_class")
    handoff_submit.add_argument("--priority", choices=["P0", "P1", "P2", "P3"], required=True)
    handoff_submit.add_argument("--trading-goals-ref", required=True, dest="trading_goals_ref")
    handoff_submit.add_argument("--output", choices=["table", "json"], default="table")

    handoff_list = handoff_subparsers.add_parser("list")
    handoff_list.add_argument("--status", choices=["submitted"], default="submitted")
    handoff_list.add_argument("--limit", type=int, default=100)
    handoff_list.add_argument("--output", choices=["table", "json"], default="table")

    handoff_issue = handoff_subparsers.add_parser("set-issue")
    handoff_issue.add_argument("handoff_id")
    handoff_issue.add_argument("--issue-ref", required=True, dest="issue_ref")
    handoff_issue.add_argument("--issue-number", type=int, default=None, dest="issue_number")
    handoff_issue.add_argument("--issue-url", default=None, dest="issue_url")
    handoff_issue.add_argument("--output", choices=["table", "json"], default="table")

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
        if args.command == "capabilities":
            return _run_capabilities(args, api=api, sessions=sessions, out=out)
        if args.command == "handoff":
            return _run_handoff(args, api=api, sessions=sessions, out=out)
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


def _run_capabilities(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, out: TextIO) -> int:
    if args.cap_command == "list":
        session = sessions.load_active()
        payload = api.list_capabilities(session=session, status=args.status)
        _emit_capability_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.cap_command == "show":
        _validate_capability_id(args.capability_id)
        session = sessions.load_active()
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
        session = sessions.load_active()
        if session.role != "sw-techlead":
            raise NexusError("NX-PERM-001", "only sw-techlead may execute set-status")
        payload = api.set_status(session=session, capability_id=args.capability_id, to=args.to_status, reason=reason)
        _emit_set_status(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    raise NexusError("NX-VAL-001", "unknown capabilities command")


def _run_handoff(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, out: TextIO) -> int:
    if args.handoff_command == "list":
        session = sessions.load_active()
        payload = api.list_handoffs(session=session, status=args.status, limit=args.limit)
        _emit_handoff_list(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.handoff_command == "submit":
        session = sessions.load_active()
        if session.role != "trading-strategist":
            raise NexusError("NX-PERM-001", "only trading-strategist may submit handoff")

        objective = _require_text(args.objective, field="objective")
        missing_capability = _require_text(args.missing_capability, field="missing-capability")
        business_impact = _require_text(args.business_impact, field="business-impact")
        expected_behavior = _require_text(args.expected_behavior, field="expected-behavior")
        trading_goals_ref = _require_text(args.trading_goals_ref, field="trading-goals-ref")
        criteria = [_require_text(item, field="acceptance-criteria") for item in args.acceptance_criteria]

        payload = api.submit_handoff(
            session=session,
            objective=objective,
            missing_capability=missing_capability,
            business_impact=business_impact,
            expected_behavior=expected_behavior,
            acceptance_criteria=criteria,
            risk_class=args.risk_class,
            priority=args.priority,
            trading_goals_ref=trading_goals_ref,
        )
        _emit_handoff_submit(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    if args.handoff_command == "set-issue":
        session = sessions.load_active()
        if session.role != "nexus":
            raise NexusError("NX-PERM-001", "only nexus may set handoff issue linkage")
        issue_ref = _require_text(args.issue_ref, field="issue-ref")
        issue_url = args.issue_url.strip() if isinstance(args.issue_url, str) and args.issue_url else None
        payload = api.set_handoff_issue(
            session=session,
            handoff_id=args.handoff_id,
            issue_ref=issue_ref,
            issue_number=args.issue_number,
            issue_url=issue_url,
        )
        _emit_handoff_issue_set(out=out, output=args.output, payload=payload)
        return EXIT_SUCCESS

    raise NexusError("NX-VAL-001", "unknown handoff command")


def _validate_capability_id(value: str) -> None:
    if not CAPABILITY_ID_PATTERN.match(value):
        raise NexusError("NX-VAL-001", "invalid capability id, expected format F-001")


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
            ("project_id", str(payload.get("project_id", ""))),
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
            ("project_id", str(payload.get("project_id", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


def _emit_handoff_submit(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    criteria = payload.get("acceptance_criteria", [])
    criteria_display = " | ".join(str(item) for item in criteria) if isinstance(criteria, list) else ""
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("handoff_id", str(payload.get("handoff_id", ""))),
            ("status", str(payload.get("status", ""))),
            ("objective", str(payload.get("objective", ""))),
            ("missing_capability", str(payload.get("missing_capability", ""))),
            ("business_impact", str(payload.get("business_impact", ""))),
            ("expected_behavior", str(payload.get("expected_behavior", ""))),
            ("acceptance_criteria", criteria_display),
            ("risk_class", str(payload.get("risk_class", ""))),
            ("priority", str(payload.get("priority", ""))),
            ("trading_goals_ref", str(payload.get("trading_goals_ref", ""))),
            ("issue_ref", str(payload.get("issue_ref", "none"))),
            ("agent_id", str(payload.get("agent_id", ""))),
            ("project_id", str(payload.get("project_id", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


def _emit_handoff_list(*, out: TextIO, output: str, payload: dict) -> None:
    handoffs = payload.get("handoffs", payload if isinstance(payload, list) else [])
    if output == "json":
        if isinstance(payload, dict):
            write_json(out, payload)
        else:
            write_json(out, {"handoffs": handoffs})
        return
    rows = [
        [
            item.get("handoff_id", ""),
            item.get("status", ""),
            item.get("priority", ""),
            item.get("risk_class", ""),
            item.get("issue_ref", "none"),
        ]
        for item in handoffs
    ]
    write_table(out, ["handoff_id", "status", "priority", "risk_class", "issue_ref"], rows)


def _emit_handoff_issue_set(*, out: TextIO, output: str, payload: dict) -> None:
    if output == "json":
        write_json(out, payload)
        return
    write_key_values(
        out,
        [
            ("ok", str(payload.get("ok", True))),
            ("handoff_id", str(payload.get("handoff_id", ""))),
            ("issue_ref", str(payload.get("issue_ref", ""))),
            ("github_issue_number", str(payload.get("github_issue_number", ""))),
            ("github_issue_url", str(payload.get("github_issue_url", ""))),
            ("timestamp", str(payload.get("timestamp", ""))),
        ],
    )


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
