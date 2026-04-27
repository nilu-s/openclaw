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
    parser.add_argument("--tls-cert-file", default=None)
    parser.add_argument("--tls-key-file", default=None)
    parser.add_argument("--allow-insecure-remote", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db_path).expanduser().resolve()
    initialize_database(db_path)
    if args.seed:
        issued_tokens = seed_mvp_data(db_path)
        if issued_tokens:
            print("Seeded fresh agent tokens (store securely):")
            for agent_id, token in sorted(issued_tokens.items()):
                print(f"  {agent_id}: {token}")

    running = start_server(
        BackendConfig(
            host=args.host,
            port=args.port,
            db_path=db_path,
            tls_cert_path=Path(args.tls_cert_file).expanduser().resolve() if args.tls_cert_file else None,
            tls_key_path=Path(args.tls_key_file).expanduser().resolve() if args.tls_key_file else None,
            allow_insecure_remote=bool(args.allow_insecure_remote),
        )
    )
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
