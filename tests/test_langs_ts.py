# Phase 1b: typescript LanguageSpec tests. TDD: written before langs/typescript.py.

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec
from brig.langs.typescript import TypeScriptSpec

fixture = Path(__file__).parent / "fixtures" / "sample.ts"

expected = {
    "greet": "function",
    "Greeter": "class",
    "Greeter.greet": "method",
    "double": "function",
}


def _load() -> bytes:
    return fixture.read_bytes()


def test_get_spec_dispatches_ts():
    assert isinstance(get_spec(str(fixture)), TypeScriptSpec)
    assert isinstance(get_spec("a.tsx"), TypeScriptSpec)
    assert get_spec("a.js") is not None  # sanity: js handled elsewhere
    assert get_spec("other.go") is None


def test_ts_qualnames_and_kinds():
    res = parse.extract(fixture, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == expected


def test_ts_byte_spans_slice_source():
    src = _load()
    res = parse.extract(fixture, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.kind == "class":
            assert sl.startswith("class "), sl
        elif s.kind == "method":
            assert sl.startswith("greet("), sl
        elif s.qualname == "double":
            assert sl.startswith("double ="), sl
        else:
            assert sl.startswith("function "), sl


def test_ts_sig_and_doc():
    res = parse.extract(fixture, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert by_name["greet"].sig == "function greet(name: string): string"
    assert by_name["greet"].doc == "Greet the user."
    assert by_name["Greeter.greet"].doc == "Greet doc."
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_ts_imports():
    res = parse.extract(fixture, _load())
    assert res is not None
    assert res.imports == ["./mod-a", "./types", "mod-c", "./dyn"]


def test_tsx_uses_tsx_grammar():
    src = b"const el = <div className=\"x\" />;\nexport function f(): number {\n return 1;\n}\n"
    res = parse.extract("comp.tsx", src)
    assert res is not None
    assert {s.qualname: s.kind for s in res.symbols} == {"f": "function"}
