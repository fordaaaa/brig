"""LanguageSpec registry. See SPEC.md (Languages v1: Registry pattern).

Register a new language by adding one entry to REGISTRY only;
get_spec() dispatches purely off REGISTRY order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from brig.parse import ExtractResult


class LanguageSpec(Protocol):
    """Per-language tree-sitter extractor."""

    def matches(self, path: str) -> bool:
        """True when this spec handles the file at *path* (suffix check)."""
        ...

    def extract(self, source: str | bytes) -> ExtractResult:
        """Extract symbols + raw import specs from file source.

        Accepts str or bytes; byte spans index the UTF-8 encoding.
        """
        ...


def _specs() -> dict[str, LanguageSpec]:
    # Imported lazily so spec modules (which import brig.parse) never
    # create an import cycle at package import time.
    from brig.langs.javascript import JavaScriptSpec
    from brig.langs.python import PythonSpec
    from brig.langs.typescript import TypeScriptSpec

    return {
        "python": PythonSpec(),
        "javascript": JavaScriptSpec(),
        "typescript": TypeScriptSpec(),
    }


REGISTRY: dict[str, LanguageSpec] = _specs()


def get_spec(path: Path | str) -> LanguageSpec | None:
    """Return the first registered spec matching *path*, else None."""
    name = str(path)
    for spec in REGISTRY.values():
        if spec.matches(name):
            return spec
    return None
