from __future__ import annotations

import argparse
import time
from pathlib import Path

from nexusctl.backend.server import BackendConfig, start_server
from nexusctl.backend.storage import initialize_database, seed_mvp_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexusctl-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db-path", default=".nexusctl/nexusctl.sqlite3")
    parser.add_argument("--seed", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db_path).expanduser().resolve()
    initialize_database(db_path)
    if args.seed:
        seed_mvp_data(db_path)

    running = start_server(BackendConfig(host=args.host, port=args.port, db_path=db_path))
    try:
        print(f"nexusctl-server running on {running.base_url} (db={db_path})")
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        running.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
