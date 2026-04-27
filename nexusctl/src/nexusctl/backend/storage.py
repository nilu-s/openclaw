from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nexusctl.errors import NexusError


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS capabilities (
                capability_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('planned', 'available'))
            );

            CREATE TABLE IF NOT EXISTS capability_details (
                capability_id TEXT PRIMARY KEY,
                subfunction_ids TEXT NOT NULL,
                requirement_ids TEXT NOT NULL,
                state_summary TEXT NOT NULL,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_requirements (
                capability_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('not-started', 'in-progress', 'implemented', 'verified')),
                PRIMARY KEY (capability_id, requirement_id),
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_evidence (
                capability_id TEXT PRIMARY KEY,
                issue_ref TEXT NOT NULL,
                pr_ref TEXT NOT NULL,
                test_ref TEXT NOT NULL,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS capability_status_events (
                event_id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                reason TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(capability_id) REFERENCES capabilities(capability_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS auth_log (
                auth_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'expired', 'revoked')),
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_registry (
                agent_token TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_mvp_data(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0]
        if existing > 0:
            return
        conn.executemany(
            """
            INSERT INTO agent_registry(agent_token, agent_id, role, project_id, domain, active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("tok_trading", "trading-strategist-01", "trading-strategist", "trading-system", "Trading", 1),
                ("tok_techlead", "sw-techlead-01", "sw-techlead", "trading-system", "Software", 1),
                ("tok_builder", "sw-builder-01", "sw-builder", "trading-system", "Software", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO capabilities(capability_id, domain, title, status) VALUES (?, ?, ?, ?)",
            [
                ("F-001", "Trading", "Paper Trading", "available"),
                ("F-002", "Trading", "Kraken API Integration", "planned"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO capability_details(capability_id, subfunction_ids, requirement_ids, state_summary)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    "F-001",
                    json.dumps(["SF-001.1", "SF-001.2"]),
                    json.dumps(["FR-001.1.1", "FR-001.2.1"]),
                    "verified",
                ),
                (
                    "F-002",
                    json.dumps(["SF-002.1"]),
                    json.dumps(["FR-002.1.1", "FR-002.1.2"]),
                    "planned",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO capability_requirements(capability_id, requirement_id, status)
            VALUES (?, ?, ?)
            """,
            [
                ("F-001", "FR-001.1.1", "verified"),
                ("F-001", "FR-001.2.1", "verified"),
                ("F-002", "FR-002.1.1", "implemented"),
                ("F-002", "FR-002.1.2", "in-progress"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO capability_evidence(capability_id, issue_ref, pr_ref, test_ref)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("F-001", "issue://101", "pr://101", "test://101"),
                ("F-002", "none", "none", "none"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


@dataclass
class SessionContext:
    session_id: str
    agent_id: str
    role: str
    project_id: str
    domain: str


class Storage:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def authenticate(self, *, agent_token: str, domain: str | None) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT agent_id, role, project_id, domain, active
                    FROM agent_registry
                    WHERE agent_token = ?
                    """,
                    (agent_token,),
                ).fetchone()
                if row is None or row["active"] != 1:
                    raise NexusError("NX-PERM-001", "invalid or inactive token")

                auth_id = self._next_id(conn, "auth_log", "auth_id", "AUTH-2026-")
                session_id = self._next_id(conn, "agent_sessions", "session_id", "S-2026-")
                timestamp = _utc_now()
                expires_at = timestamp + timedelta(minutes=60)
                resolved_domain = domain or row["domain"]
                conn.execute(
                    """
                    INSERT INTO agent_sessions(session_id, agent_id, role, project_id, domain, status, issued_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        session_id,
                        row["agent_id"],
                        row["role"],
                        row["project_id"],
                        resolved_domain,
                        _iso(timestamp),
                        _iso(expires_at),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO auth_log(auth_id, session_id, agent_id, role, project_id, domain, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        auth_id,
                        session_id,
                        row["agent_id"],
                        row["role"],
                        row["project_id"],
                        resolved_domain,
                        _iso(timestamp),
                    ),
                )
                capabilities = self._query_capabilities(conn, status_filter="all", domain=None)
                conn.commit()
                return {
                    "ok": True,
                    "auth_id": auth_id,
                    "session_id": session_id,
                    "agent_id": row["agent_id"],
                    "role": row["role"],
                    "project_id": row["project_id"],
                    "domain": resolved_domain,
                    "timestamp": _iso(timestamp),
                    "expires_at": _iso(expires_at),
                    "capabilities": capabilities,
                }
            finally:
                conn.close()

    def validate_session(self, session_id: str) -> SessionContext:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, agent_id, role, project_id, domain, status, expires_at
                FROM agent_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None or row["status"] != "active":
                raise NexusError("NX-PRECONDITION-001", "no active session")
            if _parse_iso(row["expires_at"]) <= _utc_now():
                conn.execute(
                    "UPDATE agent_sessions SET status = 'expired' WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
                raise NexusError("NX-PRECONDITION-002", "session expired")
            return SessionContext(
                session_id=row["session_id"],
                agent_id=row["agent_id"],
                role=row["role"],
                project_id=row["project_id"],
                domain=row["domain"],
            )
        finally:
            conn.close()

    def list_capabilities(self, *, status_filter: str, domain: str | None) -> dict[str, Any]:
        conn = self._connect()
        try:
            return {"capabilities": self._query_capabilities(conn, status_filter=status_filter, domain=domain)}
        finally:
            conn.close()

    def show_capability(self, capability_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            base = conn.execute(
                "SELECT capability_id, title, status FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            if base is None:
                raise NexusError("NX-NOTFOUND-001", "capability not found")
            detail = conn.execute(
                """
                SELECT subfunction_ids, requirement_ids
                FROM capability_details
                WHERE capability_id = ?
                """,
                (capability_id,),
            ).fetchone()
            subfunctions = json.loads(detail["subfunction_ids"]) if detail else []
            requirements = json.loads(detail["requirement_ids"]) if detail else []
            return {
                "capability_id": base["capability_id"],
                "title": base["title"],
                "status": base["status"],
                "subfunctions": subfunctions,
                "requirements": requirements,
            }
        finally:
            conn.close()

    def set_status(self, *, actor: SessionContext, capability_id: str, to_status: str, reason: str) -> dict[str, Any]:
        if actor.role != "sw-techlead":
            raise NexusError("NX-PERM-001", "only sw-techlead may set status")
        if to_status != "available":
            raise NexusError("NX-PRECONDITION-003", "MVP allows only planned -> available")

        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT status FROM capabilities WHERE capability_id = ?",
                    (capability_id,),
                ).fetchone()
                if row is None:
                    raise NexusError("NX-NOTFOUND-001", "capability not found")
                old_status = row["status"]
                if old_status != "planned":
                    raise NexusError("NX-PRECONDITION-003", "invalid transition")

                req_rows = conn.execute(
                    "SELECT status FROM capability_requirements WHERE capability_id = ?",
                    (capability_id,),
                ).fetchall()
                if not req_rows or any(r["status"] != "verified" for r in req_rows):
                    raise NexusError("NX-PRECONDITION-003", "requirements not fully verified")

                evidence = conn.execute(
                    """
                    SELECT issue_ref, pr_ref, test_ref
                    FROM capability_evidence
                    WHERE capability_id = ?
                    """,
                    (capability_id,),
                ).fetchone()
                if evidence is None:
                    raise NexusError("NX-PRECONDITION-003", "missing evidence")
                if (
                    evidence["issue_ref"] == "none"
                    or evidence["pr_ref"] == "none"
                    or evidence["test_ref"] == "none"
                ):
                    raise NexusError("NX-PRECONDITION-003", "evidence incomplete")

                event_id = self._next_id(conn, "capability_status_events", "event_id", "CAP-STATUS-2026-")
                timestamp = _iso(_utc_now())
                conn.execute(
                    "UPDATE capabilities SET status = ? WHERE capability_id = ?",
                    (to_status, capability_id),
                )
                conn.execute(
                    "UPDATE capability_details SET state_summary = 'available' WHERE capability_id = ?",
                    (capability_id,),
                )
                conn.execute(
                    """
                    INSERT INTO capability_status_events(
                        event_id, capability_id, old_status, new_status, reason, agent_id, project_id, timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        capability_id,
                        old_status,
                        to_status,
                        reason,
                        actor.agent_id,
                        actor.project_id,
                        timestamp,
                    ),
                )
                conn.commit()
                return {
                    "ok": True,
                    "event_id": event_id,
                    "capability_id": capability_id,
                    "old_status": old_status,
                    "new_status": to_status,
                    "reason": reason,
                    "agent_id": actor.agent_id,
                    "project_id": actor.project_id,
                    "timestamp": timestamp,
                }
            finally:
                conn.close()

    @staticmethod
    def _next_id(conn: sqlite3.Connection, table: str, column: str, prefix: str) -> str:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return f"{prefix}{count + 1:04d}"

    @staticmethod
    def _query_capabilities(conn: sqlite3.Connection, *, status_filter: str, domain: str | None) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status_filter in {"planned", "available"}:
            clauses.append("status = ?")
            params.append(status_filter)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT capability_id, title, status
            FROM capabilities
            {where}
            ORDER BY capability_id ASC
            """,
            params,
        ).fetchall()
        return [
            {"capability_id": row["capability_id"], "title": row["title"], "status": row["status"]}
            for row in rows
        ]
