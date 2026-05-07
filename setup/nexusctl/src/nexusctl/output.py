from __future__ import annotations

import json
from typing import Any, Iterable, TextIO


def write_json(out: TextIO, payload: Any) -> None:
    out.write(json.dumps(payload, ensure_ascii=True, indent=2))
    out.write("\n")


def write_table(out: TextIO, headers: list[str], rows: Iterable[list[str]]) -> None:
    row_list = [list(row) for row in rows]
    widths = [len(h) for h in headers]
    for row in row_list:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def _line() -> str:
        return "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def _format(values: list[str]) -> str:
        padded = [f" {v}{' ' * (widths[i] - len(v))} " for i, v in enumerate(values)]
        return "|" + "|".join(padded) + "|"

    out.write(_line() + "\n")
    out.write(_format(headers) + "\n")
    out.write(_line() + "\n")
    for row in row_list:
        out.write(_format(row) + "\n")
    out.write(_line() + "\n")


def write_key_values(out: TextIO, pairs: list[tuple[str, str]]) -> None:
    write_table(out, ["field", "value"], [[k, v] for k, v in pairs])
