from __future__ import annotations

import sys

from nexusctl.cli import run


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
