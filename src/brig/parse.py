"""tree-sitter parsing pipeline. See SPEC.md (Architecture: repo -> parse -> symbols/edges)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def extract(path: Path | str, source: bytes) -> tuple[Sequence[dict], list[str]]:
    """Extract (symbols, import_specs) from one file.

    Phase 1a stub: always returns ([], []). Phase 1b implements tree-sitter
    extraction per language spec; the return shape is stable so db.index_repo
    can already depend on it.
    """
    _ = (path, source)
    return ([], [])
