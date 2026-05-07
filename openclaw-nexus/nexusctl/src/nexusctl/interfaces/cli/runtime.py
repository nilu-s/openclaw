"""Shared helpers for the local Nexusctl CLI runtime.

The The historical monolithic CLI grew as a single entry point.  CLI runtime refactoring starts
extracting the reusable runtime concerns that every command module needs:
project-root and database resolution, token lookup, auth subject creation, and
explicit transaction finalization.
"""

from __future__ import annotations

import os
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
import sqlite3
from types import TracebackType
from typing import Any, Callable, Mapping, TypeVar

from nexusctl.authz.capability_matrix import CapabilityMatrix
from nexusctl.authz.policy_engine import PolicyEngine
from nexusctl.authz.token_registry import AgentTokenRegistry
from nexusctl.app.acceptance_service import AcceptanceService
from nexusctl.app.feature_request_service import FeatureRequestService
from nexusctl.app.generation_service import GenerationService
from nexusctl.app.goal_service import GoalService
from nexusctl.app.github_service import GitHubService
from nexusctl.app.merge_service import MergeService
from nexusctl.app.patch_service import PatchService
from nexusctl.app.check_service import PolicyCheckService
from nexusctl.app.reconciliation_service import GitHubReconciliationService
from nexusctl.app.review_service import ReviewService
from nexusctl.app.schedule_service import ScheduleService
from nexusctl.app.scope_service import ScopeService
from nexusctl.app.work_service import WorkService
from nexusctl.storage.sqlite.connection import connect_database
from nexusctl.storage.sqlite.migrations import apply_migrations, init_database, seed_from_blueprint
from nexusctl.storage.sqlite.schema import AUXILIARY_TABLES, MVP_TABLES

T = TypeVar("T")
ServiceFactory = Callable[[sqlite3.Connection, PolicyEngine, Path], T]


def project_root_from_args(args: Namespace) -> Path:
    """Return the project root configured on a parsed CLI namespace."""

    return Path(getattr(args, "project_root", "."))


def db_path_from_args(args: Namespace) -> Path:
    """Return the SQLite database path configured on a parsed CLI namespace."""

    return Path(getattr(args, "db", "nexus.db"))


def resolve_token(args: Namespace, *, environ: Mapping[str, str] | None = None) -> str | None:
    """Resolve the actor token from ``--token`` first and ``NEXUSCTL_TOKEN`` second."""

    environment = os.environ if environ is None else environ
    return getattr(args, "token", None) or environment.get("NEXUSCTL_TOKEN")


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    """Count rows in an internal, constant table name.

    Callers pass table names from code-defined constants only. This mirrors the
    historical CLI helper and intentionally keeps the helper small for CLI runtime refactoring.
    """

    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])


def safe_count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    """Count rows and return zero while a database is still being initialized."""

    try:
        return count_rows(connection, table_name)
    except sqlite3.Error:
        return 0



def initialize_database(args: Namespace) -> dict[str, Any]:
    """Initialize the local SQLite database and return a stable CLI payload.

    This keeps concrete storage bootstrap details inside the CLI composition
    runtime so the public entry point can stay focused on parsing and routing.
    """

    db_path = db_path_from_args(args)
    project_root = project_root_from_args(args)
    connection = connect_database(db_path)
    try:
        init_database(connection, project_root, seed_blueprint=True)
        connection.commit()
        counts = {
            "domains": count_rows(connection, "domains"),
            "agents": count_rows(connection, "agents"),
            "capabilities": count_rows(connection, "capabilities"),
            "goals": count_rows(connection, "goals"),
            "goal_metrics": count_rows(connection, "goal_metrics"),
            "feature_requests": count_rows(connection, "feature_requests"),
            "events": count_rows(connection, "events"),
            "agent_tokens": count_rows(connection, "agent_tokens"),
            "agent_sessions": count_rows(connection, "agent_sessions"),
        }
    finally:
        connection.close()
    return {
        "ok": True,
        "db": str(db_path),
        "tables": len(MVP_TABLES),
        "auxiliary_tables": len(AUXILIARY_TABLES),
        "counts": counts,
    }

def open_ready_database(args: Namespace) -> sqlite3.Connection:
    """Open a migrated and, when necessary, blueprint-seeded SQLite database."""

    connection = connect_database(db_path_from_args(args))
    project_root = project_root_from_args(args)
    apply_migrations(connection)
    if safe_count_rows(connection, "agents") == 0:
        seed_from_blueprint(connection, project_root)
    return connection


def finalize_transaction(connection: sqlite3.Connection, *, commit: bool) -> None:
    """Finish the command transaction explicitly."""

    if commit:
        connection.commit()
    else:
        connection.rollback()


@dataclass(slots=True)
class CommandRuntime:
    """Authenticated CLI runtime with one explicit Unit-of-Work boundary.

    The runtime owns one SQLite connection inside a ``with`` block. Leaving the
    block commits only when :meth:`mark_success` was called; otherwise it rolls
    back. Exceptions always roll back before the connection is closed.
    """

    args: Namespace
    connection: sqlite3.Connection | None = field(default=None, init=False)
    session: Any | None = field(default=None, init=False)
    _commit_requested: bool = field(default=False, init=False)
    _policy_engine: PolicyEngine | None = field(default=None, init=False)

    def __enter__(self) -> "CommandRuntime":
        self.connection = self.open_ready_database()
        self.session = self.authenticate(self.connection)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self.connection is None:
            return False
        try:
            finalize_transaction(self.connection, commit=exc_type is None and self._commit_requested)
        finally:
            self.connection.close()
            self.connection = None
            self.session = None
            self._commit_requested = False
            self._policy_engine = None
        return False

    @property
    def project_root(self) -> Path:
        return project_root_from_args(self.args)

    @property
    def db_path(self) -> Path:
        return db_path_from_args(self.args)

    def token(self) -> str | None:
        return resolve_token(self.args)

    def open_ready_database(self) -> sqlite3.Connection:
        return open_ready_database(self.args)

    def authenticate(self, connection: sqlite3.Connection):
        return AgentTokenRegistry(connection).authenticate(self.token())

    def capability_matrix(self) -> CapabilityMatrix:
        return CapabilityMatrix.from_project_root(self.project_root)

    def policy_engine(self) -> PolicyEngine:
        if self._policy_engine is None:
            self._policy_engine = PolicyEngine(self.capability_matrix())
        return self._policy_engine

    def require_connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("CommandRuntime must be entered before accessing the connection")
        return self.connection

    def require_session(self):
        if self.session is None:
            raise RuntimeError("CommandRuntime must be entered before accessing the session")
        return self.session

    def mark_success(self, *, commit: bool) -> None:
        """Finalize this Unit of Work as either committed or read-only rollback."""

        self._commit_requested = commit

    def service(self, factory: ServiceFactory[T]) -> T:
        """Build a service from the active connection, policy engine and project root."""

        return factory(self.require_connection(), self.policy_engine(), self.project_root)

    def goal_service(self) -> GoalService:
        return GoalService(self.require_connection(), self.policy_engine())

    def feature_request_service(self) -> FeatureRequestService:
        return FeatureRequestService(self.require_connection(), self.policy_engine())

    def github_service(self) -> GitHubService:
        return GitHubService(self.require_connection(), self.policy_engine(), self.project_root)

    def reconciliation_service(self) -> GitHubReconciliationService:
        return GitHubReconciliationService(self.require_connection(), self.policy_engine(), self.project_root)

    def work_service(self) -> WorkService:
        return WorkService(self.require_connection(), self.policy_engine())

    def scope_service(self) -> ScopeService:
        return ScopeService(self.require_connection(), self.policy_engine())

    def patch_service(self) -> PatchService:
        return PatchService(self.require_connection(), self.policy_engine(), self.project_root)

    def review_service(self) -> ReviewService:
        return ReviewService(self.require_connection(), self.policy_engine(), self.project_root)

    def acceptance_service(self) -> AcceptanceService:
        return AcceptanceService(self.require_connection(), self.policy_engine(), self.project_root)

    def policy_check_service(self) -> PolicyCheckService:
        return PolicyCheckService(self.require_connection(), self.policy_engine(), self.project_root)

    def merge_service(self) -> MergeService:
        return MergeService(self.require_connection(), self.policy_engine(), self.project_root)

    def schedule_service(self) -> ScheduleService:
        return ScheduleService(self.project_root, connection=self.require_connection(), policy=self.policy_engine())

    def generation_service(self) -> GenerationService:
        return GenerationService(self.project_root, connection=self.require_connection(), policy=self.policy_engine())
