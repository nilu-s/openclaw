"""Command-module contracts for future Nexusctl CLI extraction."""

from __future__ import annotations

import argparse
from typing import Protocol


class CommandRegistrar(Protocol):
    """Register argparse subcommands on the supplied parser collection."""

    def __call__(self, subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None: ...


class CommandHandler(Protocol):
    """Handle a parsed CLI namespace and return a process exit code."""

    def __call__(self, args: argparse.Namespace) -> int: ...
