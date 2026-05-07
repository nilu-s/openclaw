"""Domain inspection CLI commands."""

from __future__ import annotations

import argparse

from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.domain.models import Domain
from nexusctl.interfaces.cli.commands.common import add_runtime_args, emit_payload


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    domains_parser = subparsers.add_parser("domains", help="domain inspection commands")
    domains_subparsers = domains_parser.add_subparsers(dest="domains_command")
    list_parser = domains_subparsers.add_parser("list", help="list configured Nexus domains")
    add_runtime_args(list_parser)
    list_parser.add_argument("--json", action="store_true")
    show_parser = domains_subparsers.add_parser("show", help="show one configured Nexus domain")
    add_runtime_args(show_parser)
    show_parser.add_argument("id", help="domain id")
    show_parser.add_argument("--json", action="store_true")


def handle(args: argparse.Namespace) -> int:
    matrix = CapabilityMatrix.from_project_root(args.project_root)
    if getattr(args, "domains_command", None) == "show":
        matrix.assert_domain(args.id)
        return emit_payload(args, {"ok": True, "domain_record": _domain_to_json(matrix.domains[args.id])})
    domains = [_domain_to_json(domain) for _, domain in sorted(matrix.domains.items())]
    return emit_payload(args, {"ok": True, "domains": domains})


def _domain_to_json(domain: Domain) -> dict[str, str]:
    return {
        "id": domain.id,
        "name": domain.name,
        "status": domain.status.value,
        "description": domain.description,
        "source_of_truth": domain.source_of_truth,
        "default_visibility": domain.default_visibility,
    }
