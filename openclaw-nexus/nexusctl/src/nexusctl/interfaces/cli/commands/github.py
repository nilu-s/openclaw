"""GitHub projection CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nexusctl.app.github_service import GitHubService
from nexusctl.app.patch_service import PatchService
from nexusctl.app.check_service import PolicyCheckService
from nexusctl.app.reconciliation_service import GitHubReconciliationService
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.interfaces.cli.commands.common import add_auth_runtime_args, authenticated_service


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    github_parser = subparsers.add_parser("github", help="GitHub App projection commands")
    github_subparsers = github_parser.add_subparsers(dest="github_command")

    gh_app = github_subparsers.add_parser("app", help="GitHub App status commands")
    gh_app_subparsers = gh_app.add_subparsers(dest="github_app_command")
    gh_app_status = gh_app_subparsers.add_parser("status", help="show GitHub App projection status")
    add_auth_runtime_args(gh_app_status)

    gh_repos = github_subparsers.add_parser("repos", help="GitHub repository projection commands")
    gh_repos_subparsers = gh_repos.add_subparsers(dest="github_repos_command")
    gh_repos_sync = gh_repos_subparsers.add_parser("sync", help="sync repositories from nexus/github.yml")
    add_auth_runtime_args(gh_repos_sync)

    gh_labels = github_subparsers.add_parser("labels", help="GitHub label projection commands")
    gh_labels_subparsers = gh_labels.add_subparsers(dest="github_labels_command")
    gh_labels_sync = gh_labels_subparsers.add_parser("sync", help="sync labels from nexus/github.yml")
    add_auth_runtime_args(gh_labels_sync)

    gh_issue = github_subparsers.add_parser("issue", help="GitHub issue projection commands")
    gh_issue_subparsers = gh_issue.add_subparsers(dest="github_issue_command")
    gh_issue_sync = gh_issue_subparsers.add_parser("sync", help="sync one FeatureRequest to a GitHub issue")
    add_auth_runtime_args(gh_issue_sync)
    gh_issue_sync.add_argument("feature_request_id", help="feature request id to project as an issue")

    gh_pr = github_subparsers.add_parser("pr", help="GitHub pull request projection commands")
    gh_pr_subparsers = gh_pr.add_subparsers(dest="github_pr_command")
    gh_pr_create = gh_pr_subparsers.add_parser("create", help="create or update a PR for a patch proposal")
    add_auth_runtime_args(gh_pr_create)
    gh_pr_create.add_argument("patch_id", help="patch proposal id")

    gh_checks = github_subparsers.add_parser("checks", help="GitHub Check Run projection commands")
    gh_checks_subparsers = gh_checks.add_subparsers(dest="github_checks_command")
    gh_checks_sync = gh_checks_subparsers.add_parser("sync", help="sync Nexus policy gates to GitHub Checks")
    add_auth_runtime_args(gh_checks_sync)
    gh_checks_sync.add_argument("patch_id", help="patch proposal id")

    gh_reconcile = github_subparsers.add_parser("reconcile", help="process pending GitHub webhook events and repair projection drift")
    add_auth_runtime_args(gh_reconcile)
    gh_reconcile.add_argument("--limit", type=int, default=100, help="maximum pending webhook events to process")

    gh_webhook = github_subparsers.add_parser("webhook", help="GitHub webhook utilities")
    gh_webhook_subparsers = gh_webhook.add_subparsers(dest="github_webhook_command")
    gh_webhook_verify = gh_webhook_subparsers.add_parser("verify", help="verify a GitHub webhook HMAC signature")
    add_auth_runtime_args(gh_webhook_verify)
    gh_webhook_verify.add_argument("--payload", default="{}", help="raw JSON payload; ignored when --payload-file is set")
    gh_webhook_verify.add_argument("--payload-file", help="file containing the raw JSON payload")
    gh_webhook_verify.add_argument("--signature", required=True, help="X-Hub-Signature-256 value")
    gh_webhook_verify.add_argument("--secret", help="webhook secret; defaults to GITHUB_WEBHOOK_SECRET")


def handle(args: argparse.Namespace) -> int:
    command = getattr(args, "github_command", None)
    if command == "app" and getattr(args, "github_app_command", None) == "status":
        return _cmd_app_status(args)
    if command == "repos" and getattr(args, "github_repos_command", None) == "sync":
        return _cmd_repos_sync(args)
    if command == "labels" and getattr(args, "github_labels_command", None) == "sync":
        return _cmd_labels_sync(args)
    if command == "issue" and getattr(args, "github_issue_command", None) == "sync":
        return _cmd_issue_sync(args)
    if command == "pr" and getattr(args, "github_pr_command", None) == "create":
        return _cmd_pr_create(args)
    if command == "checks" and getattr(args, "github_checks_command", None) == "sync":
        return _cmd_checks_sync(args)
    if command == "reconcile":
        return _cmd_reconcile(args)
    if command == "webhook" and getattr(args, "github_webhook_command", None) == "verify":
        return _cmd_webhook_verify(args)
    return 2


def _cmd_app_status(args: argparse.Namespace) -> int:
    return authenticated_service(args, _github_service, lambda session, service: service.app_status(session.subject))


def _cmd_repos_sync(args: argparse.Namespace) -> int:
    return authenticated_service(args, _github_service, lambda session, service: service.sync_repositories(session.subject), commit=True)


def _cmd_labels_sync(args: argparse.Namespace) -> int:
    return authenticated_service(args, _github_service, lambda session, service: service.sync_labels(session.subject), commit=True)


def _cmd_issue_sync(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _github_service,
        lambda session, service: service.sync_feature_request_issue(session.subject, args.feature_request_id),
        commit=True,
    )


def _cmd_pr_create(args: argparse.Namespace) -> int:
    return authenticated_service(args, _patch_service, lambda session, service: service.create_pr(session.subject, args.patch_id), commit=True)


def _cmd_checks_sync(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _policy_check_service,
        lambda session, service: service.sync_github_checks(session.subject, args.patch_id),
        commit=True,
    )


def _cmd_reconcile(args: argparse.Namespace) -> int:
    return authenticated_service(
        args,
        _reconciliation_service,
        lambda session, service: service.reconcile(session.subject, limit=args.limit),
        commit=True,
    )


def _cmd_webhook_verify(args: argparse.Namespace) -> int:
    body = Path(args.payload_file).read_bytes() if args.payload_file else args.payload.encode("utf-8")
    return authenticated_service(
        args,
        _reconciliation_service,
        lambda session, service: service.verify_webhook(
            session.subject,
            body=body,
            signature=args.signature,
            secret=args.secret,
        ),
    )


def _github_service(connection: Any, policy: PolicyEngine, project_root: Path) -> GitHubService:
    return GitHubService(connection, policy, project_root)


def _patch_service(connection: Any, policy: PolicyEngine, project_root: Path) -> PatchService:
    return PatchService(connection, policy, project_root)


def _policy_check_service(connection: Any, policy: PolicyEngine, project_root: Path) -> PolicyCheckService:
    return PolicyCheckService(connection, policy, project_root)


def _reconciliation_service(connection: Any, policy: PolicyEngine, project_root: Path) -> GitHubReconciliationService:
    return GitHubReconciliationService(connection, policy, project_root)
