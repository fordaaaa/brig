# to add a language, just add one line to registry below.

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from brig.parse import ExtractResult


class LanguageSpec(Protocol):
    # what one language knows how to do.

    def matches(self, path: str) -> bool:
        # true if this spec handles the file (goes by suffix).
        ...

    def extract(self, source: str | bytes) -> ExtractResult:
        # pull symbols + imports out of source. takes str or bytes.
        ...


def _specs() -> dict[str, LanguageSpec]:
    # imported here (not at the top) to avoid an import loop.
    from brig.langs.c import CSpec
    from brig.langs.cpp import CppSpec
    from brig.langs.csharp import CSharpSpec
    from brig.langs.java import JavaSpec
    from brig.langs.javascript import JavaScriptSpec
    from brig.langs.python import PythonSpec
    from brig.langs.typescript import TypeScriptSpec

    return {
        "c": CSpec(),
        "cpp": CppSpec(),
        "csharp": CSharpSpec(),
        "java": JavaSpec(),
        "python": PythonSpec(),
        "javascript": JavaScriptSpec(),
        "typescript": TypeScriptSpec(),
    }


registry: dict[str, LanguageSpec] = _specs()


def get_spec(path: Path | str) -> LanguageSpec | None:
    # first spec whose suffix matches, or nothing.
    name = str(path)
    for spec in registry.values():
        if spec.matches(name):
            return spec
    return None
