# typescript: same walker as javascript. tries ts, falls back to tsx.

from __future__ import annotations

from pathlib import PurePath

import tree_sitter_typescript
from tree_sitter import Language, Parser

from brig.langs.javascript import extract_source
from brig.parse import ExtractResult

_TS_LANGUAGE = Language(tree_sitter_typescript.language_typescript())
_TSX_LANGUAGE = Language(tree_sitter_typescript.language_tsx())

_SUFFIXES = frozenset({".ts", ".tsx", ".mts", ".cts"})


class TypeScriptSpec:
    # handles .ts, .tsx, .mts and .cts files.

    def matches(self, path: str) -> bool:
        return PurePath(path).suffix.lower() in _SUFFIXES

    def extract(self, source: str | bytes) -> ExtractResult:
        data = source.encode("utf-8") if isinstance(source, str) else bytes(source)
        tree = Parser(_TS_LANGUAGE).parse(data)
        if tree.root_node.has_error:
            alt = Parser(_TSX_LANGUAGE).parse(data)
            if not alt.root_node.has_error:
                return extract_source(data, _TSX_LANGUAGE)
        return extract_source(data, _TS_LANGUAGE)
