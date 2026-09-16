# parse one file with tree-sitter.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Iterator


@dataclass
class Symbol:
    # one function/class/method found in a file.
    # acts like a dict so db.py can use it directly.

    path: str = ""
    qualname: str = ""
    kind: str = ""  # function, class or method
    sig: str = ""
    doc: str = ""
    start_byte: int = 0
    end_byte: int = 0

    _KEYS: ClassVar[tuple[str, ...]] = (
        "path",
        "qualname",
        "kind",
        "sig",
        "doc",
        "start_byte",
        "end_byte",
    )

    def __getitem__(self, key: str):  # type: ignore[no-untyped-def]
        if key not in self._KEYS:
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default=None):  # type: ignore[no-untyped-def]
        return getattr(self, key, default) if key in self._KEYS else default

    def __contains__(self, key: object) -> bool:
        return key in self._KEYS


@dataclass
class ExtractResult:
    # what we found in one file: symbols + imports.
    # unpacks as: symbols, imports = result.

    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def __iter__(self) -> Iterator:
        return iter((self.symbols, self.imports))

    def __len__(self) -> int:
        return 2


def extract(path: Path | str, source: bytes | str) -> ExtractResult | None:
    # pick the language spec by file suffix.
    # returns nothing when no spec matches.
    from brig.langs import get_spec  # lazy import, avoids a loop

    spec = get_spec(path)
    if spec is None:
        return None
    res = spec.extract(source)
    for s in res.symbols:
        s.path = str(path)
    return res
