from __future__ import annotations

import argparse
import os
import re
import sys
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
    auth.add_argument("--domain")
    auth.add_argument("--output", choices=["table", "json"], default="table")

    capabilities = subparsers.add_parser("capabilities")
    cap_subparsers = capabilities.add_subparsers(dest="cap_command", required=True)

    cap_list = cap_subparsers.add_parser("list")
    cap_list.add_argument("--domain")
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
        raise NexusError("NX-VAL-001", "unknown command")
    except NexusError as exc:
        err.write(f"{exc.code}: {exc.message}\n")
        return int(exc.exit_code or 10)


def _run_auth(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, env: Mapping[str, str], out: TextIO) -> int:
    token = args.agent_token or env.get("NEXUS_AGENT_TOKEN")
    if not token:
        raise NexusError("NX-VAL-002", "missing agent token (--agent-token or NEXUS_AGENT_TOKEN)")
    auth_response = api.auth(agent_token=token, domain=args.domain)
    sessions.save_auth_response(auth_response)
    _emit_auth(out=out, output=args.output, payload=auth_response)
    return EXIT_SUCCESS


def _run_capabilities(args: argparse.Namespace, *, api: ApiClient, sessions: SessionStore, out: TextIO) -> int:
    if args.cap_command == "list":
        session = sessions.load_active()
        payload = api.list_capabilities(session=session, domain=args.domain, status=args.status)
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
