"""tree-sitter parsing pipeline. See SPEC.md (Architecture: repo -> parse -> symbols/edges)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Iterator


@dataclass
class Symbol:
    """One extracted def/class with a byte-exact span.

    Mapping-compatible (``s["qualname"]`` / ``s.get("sig", "")``) so the
    result unpacks straight into ``db.index_file`` / ``db.index_repo``.
    """

    path: str = ""
    qualname: str = ""
    kind: str = ""  # function | class | method (v1 only)
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
    """Symbol + import extraction for one file.

    Unpacks as ``symbols, imports = result`` for the ``db.index_repo``
    ``extract_fn`` contract.
    """

    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def __iter__(self) -> Iterator:
        return iter((self.symbols, self.imports))

    def __len__(self) -> int:
        return 2


def extract(path: Path | str, source: bytes | str) -> ExtractResult | None:
    """Dispatch to the registered LanguageSpec for *path*.

    Returns None when no spec matches (unsupported language).
    """
    from brig.langs import get_spec  # lazy: langs imports this module

    spec = get_spec(path)
    if spec is None:
        return None
    res = spec.extract(source)
    for s in res.symbols:
        s.path = str(path)
    return res
