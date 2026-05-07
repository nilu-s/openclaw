"""Shared helpers for extracted Nexusctl CLI command modules."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, TypeVar

from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.interfaces.cli.output import print_json
from nexusctl.interfaces.cli.runtime import CommandRuntime

T = TypeVar("T")


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    """Add local runtime options common to Nexusctl commands."""

    parser.add_argument("--db", default="nexus.db", help="SQLite database path")
    parser.add_argument("--project-root", default=".", help="project root containing nexus/*.yml")


def add_api_args(parser: argparse.ArgumentParser) -> None:
    """Add optional remote API options for commands that support HTTP mode."""

    parser.add_argument("--api-url", help="Nexusctl API base URL; when set, run this command against HTTP")
    parser.add_argument("--api-timeout", type=float, default=None, help="remote API timeout in seconds; defaults to NEXUSCTL_API_TIMEOUT_SECONDS or 5")


def add_auth_runtime_args(parser: argparse.ArgumentParser) -> None:
    """Add runtime, token, JSON and optional remote API options."""

    add_runtime_args(parser)
    parser.add_argument("--token", help="agent token; defaults to NEXUSCTL_TOKEN")
    add_api_args(parser)
    parser.add_argument("--json", action="store_true")


def emit_payload(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    """Emit a command payload using the stable JSON or human CLI format."""

    if getattr(args, "json", False):
        print_json(payload)
    else:
        print_human(payload)
    return 0


def authenticated_service(
    args: argparse.Namespace,
    factory: Callable[[Any, PolicyEngine, Path], T],
    callback: Callable[[Any, T], dict[str, Any]],
    *,
    commit: bool = False,
) -> int:
    """Run an authenticated command inside the shared CommandRuntime Unit of Work."""

    with CommandRuntime(args) as runtime:
        session = runtime.require_session()
        service = runtime.service(factory)
        payload = callback(session, service)
        runtime.mark_success(commit=commit)
    return emit_payload(args, payload)


def identity_payload(session: Any) -> dict[str, Any]:
    return {"ok": True, "identity": session.to_json()}


def subject_payload(session: Any, **values: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "agent_id": session.subject.agent_id,
        "domain": session.subject.domain,
        **values,
    }


def goal_collection_payload(
    args: argparse.Namespace,
    session: Any,
    *,
    goals: list[dict[str, Any]],
) -> dict[str, Any]:
    requested_domain = getattr(args, "domain", None)
    return subject_payload(
        session,
        requested_domain=requested_domain,
        visible_domain=requested_domain or session.subject.domain,
        domain_source="auth_token" if requested_domain is None else "policy_allowed_override",
        goals=goals,
    )


def print_human(payload: dict[str, Any]) -> None:
    """Human-readable rendering for the target CLI."""

    if "identity" in payload:
        identity = payload["identity"]
        print(f"{identity.get('agent_id')} ({identity.get('domain')}/{identity.get('role')})")
        return
    if "capabilities" in payload:
        print("\n".join(payload["capabilities"]))
        return
    if "domains" in payload:
        for domain in payload["domains"]:
            print(f"{domain['id']}: {domain['status']} {domain['name']}")
        return
    if "domain_record" in payload:
        domain = payload["domain_record"]
        print(f"{domain['id']}: {domain['status']} {domain['name']}")
        return
    if "runtime_tools" in payload:
        for tool in payload["runtime_tools"]:
            print(f"{tool['id']}: {tool['domain']} {tool['side_effect']} capability={tool['capability']}")
        return
    if "runtime_tool" in payload:
        tool = payload["runtime_tool"]
        print(f"{tool['id']}: {tool['domain']} {tool['side_effect']} capability={tool['capability']}")
        return
    if "runtime_tool_check" in payload:
        check = payload["runtime_tool_check"]
        print(f"{check['tool_id']}: {check['decision']} for {check['agent_id']} ({', '.join(check['reasons'])})")
        return
    if "merge" in payload:
        merge = payload["merge"]
        print(f"{merge['patch_id']}: merged PR #{merge['pull_number']} sha={merge['merge_sha']}")
        return
    if "review_queue" in payload:
        for item in payload["review_queue"]:
            print(f"{item['patch_id']}: {item['patch_status']} reviewer={item.get('reviewer_agent_id')} pr={(item.get('github_pr') or {}).get('pull_number')}")
        return
    if "review" in payload:
        review = payload["review"]
        print(f"{review['id']}: {review['verdict']} patch={review['patch_id']}")
        return
    if "acceptance" in payload:
        acceptance = payload["acceptance"]
        print(f"{acceptance['id']}: {acceptance['status']} feature_request={acceptance['feature_request_id']}")
        return
    if "acceptance_status" in payload:
        status = payload["acceptance_status"]
        print(f"{status['feature_request_id']}: {status['effective_status']}")
        return
    if "github_pr" in payload:
        pr = payload["github_pr"]
        print(f"created PR {pr['repository']}#{pr['pull_number']} branch={pr['branch']}")
        return
    if "github_checks" in payload:
        policy = payload["policy_check"]
        print(f"synced {len(payload['github_checks'])} GitHub checks for {payload['patch_id']} status={policy['overall_status']}")
        return
    if "policy_check" in payload:
        policy = payload["policy_check"]
        print(f"{policy['patch_id']}: {policy['overall_status']} merge_allowed={policy['merge_allowed']}")
        return
    if "work_start" in payload:
        start = payload["work_start"]
        print(f"{start['work_item_id']}: {start['status']} branch={start['worktree']['branch']}")
        return
    if "patch" in payload:
        patch = payload["patch"]
        print(f"{patch['id']}: {patch['status']} {len(patch.get('changed_paths', []))} changed path(s)")
        return
    if "work" in payload:
        work = payload["work"]
        print(f"{work['id']}: {work['status']} {work['feature_request_id']} builder={work.get('builder')} reviewer={work.get('reviewer')}")
        return
    if "scope_lease" in payload:
        lease = payload["scope_lease"]
        print(f"{lease['id']}: {lease['status']} agent={lease['agent_id']} expires_at={lease.get('expires_at')}")
        return
    if "processed_count" in payload and "processed" in payload:
        print(f"reconciled {payload['processed_count']} GitHub webhook event(s), alerts={len(payload.get('alerts', []))}")
        return
    if "verified" in payload:
        print("GitHub webhook signature verified" if payload["verified"] else "GitHub webhook signature invalid")
        return
    if "backup" in payload:
        backup = payload["backup"]
        print(f"backup created: {backup['backup_path']} ({backup['size_bytes']} bytes, {backup['checked_events']} events checked)")
        return
    if "restore_check" in payload:
        check = payload["restore_check"]
        print(f"backup ok: {check['backup_path']} ({check['checked_events']} events checked, schema {check['schema_version']}/{check['latest_schema_version']})")
        return
    if "restore" in payload:
        restore = payload["restore"]
        print(f"restored: {restore['restored_db']} from {restore['backup_path']} ({restore['checked_events']} events checked)")
        return
    if "restore_drill" in payload:
        drill = payload["restore_drill"]
        print(
            f"restore drill: {drill['doctor_status']} restored={drill['restored_db']} "
            f"backup={drill['backup_path']} failed_checks={len(drill.get('failed_checks', []))}"
        )
        return
    if "status_codes" in payload and "generated_artifact_count" in payload:
        print(f"doctor: {payload['status_code']} - {payload['summary']}")
        print(f"generated artifacts: {payload['status_codes']['generated_artifacts']} ({payload['drift_count']} drift / {payload['generated_artifact_count']} checked)")
        print(f"github projection: {payload['status_codes']['github_projection']} ({len(payload.get('github_projection', {}).get('drift', []))} drift)")
        webhook_contract = payload.get("github_webhook_contract", {})
        if webhook_contract:
            print(f"github webhook contract: {payload['status_codes'].get('github_webhook_contract')} ({len(webhook_contract.get('fixture_backed_events', []))} fixture-backed event classes)")
        print(f"alerts: {payload['status_codes']['alerts']} ({payload.get('open_alert_count', 0)} open, {payload.get('critical_alert_count', 0)} critical)")
        event_integrity = payload.get("event_integrity", {})
        if event_integrity:
            print(f"event integrity: {event_integrity.get('status_code')} ({event_integrity.get('checked_events', 0)} checked)")
        database = payload.get("database", {})
        if database:
            print(f"database: {database.get('status_code')} (schema {database.get('schema_version')}/{database.get('latest_schema_version')})")
        for warning in payload.get("operational_warnings", [])[:10]:
            print(f"operation: {warning['severity']} {warning['status_code']} - {warning['summary']}")
        chains = payload.get("audit_chains", [])
        if chains:
            print("audit chains:")
            for chain in chains[:10]:
                steps = " -> ".join(step["step"] for step in chain.get("steps", []) if step.get("present"))
                print(f"- {chain.get('feature_request_id')}: {steps or 'no linked steps'}")
        for item in payload.get("drift", [])[:10]:
            print(f"drift: {item.get('path')} - {item.get('action')}")
        for alert in payload.get("alerts", [])[:10]:
            print(f"alert: {alert['severity']} {alert['kind']} - {alert['summary']}")
        return
    if "github_app" in payload:
        status = payload["github_app"]
        print(f"GitHub App mode={status.get('mode')} mock={status.get('mock_mode')} configured={status.get('configured')}")
        return
    if "github_issue" in payload:
        issue = payload["github_issue"]
        print(f"synced feature request {payload['feature_request_id']} to {issue['repository']}#{issue['issue_number']}")
        return
    if "repositories" in payload:
        print("synced repositories: " + ", ".join(repo["full_name"] for repo in payload["repositories"]))
        return
    if "labels" in payload:
        print(f"synced {len(payload['labels'])} labels for {payload['repository']}")
        return
    if "feature_requests" in payload:
        for request in payload["feature_requests"]:
            print(f"{request['id']}: {request['status']} {request['source_domain']}->{request['target_domain']} {request['title']}")
        return
    if "feature_request" in payload:
        request = payload["feature_request"]
        print(f"{request['id']}: {request['status']} {request['source_domain']}->{request['target_domain']} {request['title']}")
        return
    if "goals" in payload:
        for goal in payload["goals"]:
            evaluation = goal.get("evaluation_status") or (goal.get("latest_evaluation") or {}).get("status", "unknown")
            print(f"{goal['id']}: {evaluation} ({goal['domain']})")
        return
    if "goal" in payload:
        goal = payload["goal"]
        evaluation = (goal.get("latest_evaluation") or {}).get("status", "unknown")
        print(f"{goal['id']}: {evaluation} ({goal['domain']})")
        return
    if "measurement" in payload:
        measurement = payload["measurement"]
        print(f"measured {measurement['goal_id']} at {measurement['measured_at']}")
        return
    if "evaluation" in payload:
        evaluation = payload["evaluation"]
        print(f"{evaluation['goal_id']}: {evaluation['status']} - {evaluation['summary']}")
        return
    if "evidence" in payload:
        evidence = payload["evidence"]
        print(f"added evidence {evidence['id']} for {evidence['goal_id']}")
        return
    print(payload)
