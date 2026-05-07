"""Generated runtime drift doctor CLI command."""

from __future__ import annotations

import argparse

from nexusctl.app.generation_service import GenerationService
from nexusctl.interfaces.cli.commands.common import add_runtime_args, emit_payload
from nexusctl.interfaces.cli.runtime import open_ready_database


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    doctor_parser = subparsers.add_parser("doctor", help="validate generated OpenClaw runtime checksums")
    add_runtime_args(doctor_parser)
    doctor_parser.add_argument("--json", action="store_true")


def handle(args: argparse.Namespace) -> int:
    connection = open_ready_database(args)
    try:
        payload = GenerationService(args.project_root, connection=connection).doctor()
    finally:
        connection.rollback()
        connection.close()
    emit_payload(args, payload)
    return 0 if payload.get("ok") else 1
