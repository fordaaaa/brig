"""CLI mirror for brig. See SPEC.md (Tool surface + CLI mirror)."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser (stub)."""
    parser = argparse.ArgumentParser(prog="brig", description="brig CLI (stub)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (stub)."""
    parser = build_parser()
    parser.parse_args(argv)
    return 0
