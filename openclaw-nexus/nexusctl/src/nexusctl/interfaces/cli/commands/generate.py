"""OpenClaw runtime generation CLI commands."""

from __future__ import annotations

import argparse

from nexusctl.app.generation_service import GenerationService
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service, subject_payload


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    generate_parser = subparsers.add_parser("generate", help="generate OpenClaw runtime artifacts from nexus/*.yml")
    generate_subparsers = generate_parser.add_subparsers(dest="generate_command")
    generate_openclaw = generate_subparsers.add_parser("openclaw", help="generate generated/openclaw/openclaw.json")
    add_auth_runtime_args(generate_openclaw)
    generate_agents = generate_subparsers.add_parser("agents", help="generate per-agent OpenClaw markdown files")
    add_auth_runtime_args(generate_agents)
    generate_skills = generate_subparsers.add_parser("skills", help="generate skill files, allowlists, and tool policies")
    add_auth_runtime_args(generate_skills)
    generate_all = generate_subparsers.add_parser("all", help="generate all OpenClaw runtime artifacts")
    add_auth_runtime_args(generate_all)


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "generate_command", None)
    if command == "openclaw":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.generate_openclaw(session.subject)), commit=True)
    if command == "agents":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.generate_agents(session.subject)), commit=True)
    if command == "skills":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.generate_skills(session.subject)), commit=True)
    if command == "all":
        return authenticated_service(args, _service, lambda session, service: subject_payload(session, **service.generate_all(session.subject)), commit=True)
    return 2


def _service(connection, policy, project_root) -> GenerationService:
    return GenerationService(project_root, connection=connection, policy=policy)
