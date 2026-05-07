"""Authenticated identity CLI commands."""

from __future__ import annotations

import argparse

from nexusctl.interfaces.cli.commands.common import add_api_args, add_runtime_args, emit_payload, identity_payload, subject_payload
from nexusctl.interfaces.cli.runtime import CommandRuntime, resolve_token
from nexusctl.interfaces.http.client import NexusctlAPIClient


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    me_parser = subparsers.add_parser("me", help="show authenticated agent identity")
    add_runtime_args(me_parser)
    me_parser.add_argument("--token", help="agent token; defaults to NEXUSCTL_TOKEN")
    add_api_args(me_parser)
    me_parser.add_argument("--json", action="store_true")
    me_subparsers = me_parser.add_subparsers(dest="me_command")
    capabilities_parser = me_subparsers.add_parser("capabilities", help="show authenticated capabilities")
    add_runtime_args(capabilities_parser)
    capabilities_parser.add_argument("--token", help="agent token; defaults to NEXUSCTL_TOKEN")
    add_api_args(capabilities_parser)
    capabilities_parser.add_argument("--json", action="store_true")


def handle(args: argparse.Namespace) -> int:
    if getattr(args, "api_url", None):
        return _handle_remote(args)

    with CommandRuntime(args) as runtime:
        session = runtime.require_session()
        if getattr(args, "me_command", None) == "capabilities":
            payload = subject_payload(session, capabilities=sorted(session.subject.capabilities))
        else:
            payload = identity_payload(session)
        runtime.mark_success(commit=False)
    return emit_payload(args, payload)


def _handle_remote(args: argparse.Namespace) -> int:
    client = NexusctlAPIClient(args.api_url, token=resolve_token(args), timeout=args.api_timeout)
    response = client.auth_me()
    agent = response["agent"]
    capabilities = sorted(response.get("capabilities", []))
    if getattr(args, "me_command", None) == "capabilities":
        payload = {
            "ok": True,
            "agent_id": agent["agent_id"],
            "domain": agent["domain"],
            "capabilities": capabilities,
            "transport": "http",
        }
    else:
        payload = {
            "ok": True,
            "identity": {**agent, "capabilities": capabilities, "domain_source": "auth_token"},
            "transport": "http",
        }
    return emit_payload(args, payload)
