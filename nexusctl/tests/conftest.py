from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from nexusctl.backend.server import BackendConfig, RunningServer, start_server
from nexusctl.backend.storage import initialize_database, seed_mvp_data


TEST_SEED_TOKENS = {
    "main-01": "tok_main",
    "nexus-01": "tok_nexus",
    "sw-architect-01": "tok_architect",
    "trading-strategist-01": "tok_trading",
    "trading-analyst-01": "tok_analyst",
    "trading-sentinel-01": "tok_sentinel",
    "sw-techlead-01": "tok_techlead",
    "sw-builder-01": "tok_builder",
    "sw-reviewer-01": "tok_reviewer",
}


@dataclass
class BackendServer:
    base_url: str
    db_path: Path
    _running: RunningServer

    def stop(self) -> None:
        self._running.stop()

    def execute(self, sql: str, params: tuple = ()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()


@pytest.fixture()
def backend_server(tmp_path: Path) -> BackendServer:
    db_path = tmp_path / "nexusctl.sqlite3"
    initialize_database(db_path)
    seed_mvp_data(db_path, seed_tokens=TEST_SEED_TOKENS)
    config = BackendConfig(host="127.0.0.1", port=0, db_path=db_path)
    running = start_server(config)
    instance = BackendServer(base_url=running.base_url, db_path=db_path, _running=running)
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture()
def cli_env(tmp_path: Path, backend_server: BackendServer) -> dict[str, str]:
    agent_dir = tmp_path / "agents" / "sw-techlead-01" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    return {
        "NEXUSCTL_API_BASE_URL": backend_server.base_url,
        "NEXUSCTL_AGENT_DIR": str(agent_dir),
    }
