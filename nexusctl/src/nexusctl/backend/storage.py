from __future__ import annotations

import hashlib
import hmac
import json
import secrets
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


_PBKDF2_ITERATIONS = 200_000
_RANDOM_ID_HEX_CHARS = 16


def _random_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(_RANDOM_ID_HEX_CHARS // 2)}"


def _derive_token_material(token: str, *, salt: str | None = None) -> tuple[str, str]:
    salt_bytes = bytes.fromhex(salt) if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS)
    return salt_bytes.hex(), digest.hex()


def _verify_token(token: str, *, salt: str, digest_hex: str) -> bool:
    _, computed = _derive_token_material(token, salt=salt)
    return hmac.compare_digest(computed, digest_hex)


def _agent_seed_blueprint() -> list[tuple[str, str, str, str]]:
    return [
        ("trading-strategist-01", "trading-strategist", "trading-system", "Trading"),
        ("sw-techlead-01", "sw-techlead", "trading-system", "Software"),
        ("sw-builder-01", "sw-builder", "trading-system", "Software"),
    ]


def _resolve_seed_tokens(seed_tokens: dict[str, str] | None) -> dict[str, str]:
    if seed_tokens is None:
        return {agent_id: secrets.token_urlsafe(24) for agent_id, _, _, _ in _agent_seed_blueprint()}
    missing = [agent_id for agent_id, _, _, _ in _agent_seed_blueprint() if agent_id not in seed_tokens]
    if missing:
        missing_display = ", ".join(sorted(missing))
        raise ValueError(f"missing seed token(s) for agent id(s): {missing_display}")
    return {agent_id: seed_tokens[agent_id] for agent_id, _, _, _ in _agent_seed_blueprint()}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _prepare_agent_registry_hash_material(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "agent_registry")
    if "agent_token_hash" not in columns:
        conn.execute("ALTER TABLE agent_registry ADD COLUMN agent_token_hash TEXT")
    if "agent_token_salt" not in columns:
        conn.execute("ALTER TABLE agent_registry ADD COLUMN agent_token_salt TEXT")

    columns = _table_columns(conn, "agent_registry")
    if "agent_token" in columns:
        rows = conn.execute(
            """
            SELECT rowid, agent_token, agent_token_hash, agent_token_salt
            FROM agent_registry
            """
        ).fetchall()
        for rowid, legacy_token, token_hash, token_salt in rows:
            if token_hash and token_salt:
                continue
            material = legacy_token or secrets.token_urlsafe(24)
            salt_hex, digest_hex = _derive_token_material(material)
            conn.execute(
                """
                UPDATE agent_registry
                SET agent_token_hash = ?, agent_token_salt = ?
                WHERE rowid = ?
                """,
                (digest_hex, salt_hex, rowid),
            )


def _cutover_agent_registry_to_v2(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "agent_registry")
    needs_cutover = "agent_token" in columns or "agent_token_hash" not in columns or "agent_token_salt" not in columns
    if not needs_cutover:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_registry_token_hash ON agent_registry(agent_token_hash)")
        return

    _prepare_agent_registry_hash_material(conn)

    conn.execute("DROP TABLE IF EXISTS agent_registry__new")
    conn.executescript(
        """
        CREATE TABLE agent_registry__new (
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,
            project_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            active INTEGER NOT NULL CHECK(active IN (0, 1)),
            agent_token_hash TEXT NOT NULL,
            agent_token_salt TEXT NOT NULL,
            PRIMARY KEY (agent_id, project_id)
        );
        CREATE UNIQUE INDEX idx_agent_registry__new_token_hash ON agent_registry__new(agent_token_hash);
        """
    )
    conn.execute(
        """
        INSERT INTO agent_registry__new(agent_id, role, project_id, domain, active, agent_token_hash, agent_token_salt)
        SELECT agent_id, role, project_id, domain, active, agent_token_hash, agent_token_salt
        FROM agent_registry
        """
    )
    conn.execute("DROP TABLE agent_registry")
    conn.execute("ALTER TABLE agent_registry__new RENAME TO agent_registry")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_registry_token_hash ON agent_registry(agent_token_hash)")


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
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1)),
                agent_token_hash TEXT NOT NULL,
                agent_token_salt TEXT NOT NULL,
                PRIMARY KEY (agent_id, project_id)
            );
            """
        )
        _cutover_agent_registry_to_v2(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_registry_token_hash ON agent_registry(agent_token_hash)")
        conn.commit()
    finally:
        conn.close()


def seed_mvp_data(db_path: Path, *, seed_tokens: dict[str, str] | None = None) -> dict[str, str] | None:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM capabilities").fetchone()[0]
        if existing > 0:
            return None
        resolved_tokens = _resolve_seed_tokens(seed_tokens)
        agent_rows: list[tuple[str, str, str, str, str, str, int]] = []
        for agent_id, role, project_id, domain in _agent_seed_blueprint():
            salt_hex, digest_hex = _derive_token_material(resolved_tokens[agent_id])
            agent_rows.append((agent_id, role, project_id, domain, 1, digest_hex, salt_hex))
        conn.executemany(
            """
            INSERT INTO agent_registry(agent_id, role, project_id, domain, active, agent_token_hash, agent_token_salt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            agent_rows,
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
        return resolved_tokens
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
                rows = conn.execute(
                    """
                    SELECT agent_id, role, project_id, domain, active, agent_token_hash, agent_token_salt
                    FROM agent_registry
                    WHERE active = 1
                    """,
                ).fetchall()
                row = next(
                    (
                        item
                        for item in rows
                        if item["agent_token_hash"]
                        and item["agent_token_salt"]
                        and _verify_token(
                            agent_token,
                            salt=item["agent_token_salt"],
                            digest_hex=item["agent_token_hash"],
                        )
                    ),
                    None,
                )
                if row is None:
                    raise NexusError("NX-PERM-001", "invalid or inactive token")
                if domain and domain != row["domain"]:
                    raise NexusError("NX-PERM-001", "token is not valid for requested domain")

                auth_id = _random_id("AUTH-2026-")
                session_id = _random_id("S-2026-")
                timestamp = _utc_now()
                expires_at = timestamp + timedelta(minutes=60)
                resolved_domain = row["domain"]
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

                event_id = _random_id("CAP-STATUS-2026-")
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
