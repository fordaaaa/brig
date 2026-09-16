# Phase 1b: javascript LanguageSpec tests. TDD: written before langs/javascript.py.

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec
from brig.langs.javascript import JavaScriptSpec

fixture = Path(__file__).parent / "fixtures" / "sample.js"

expected = {
    "load": "function",
    "load.nested": "function",
    "double": "function",
    "Foo": "class",
    "Foo.bar": "method",
}


def _load() -> bytes:
    return fixture.read_bytes()


def test_get_spec_dispatches_js():
    assert isinstance(get_spec(str(fixture)), JavaScriptSpec)
    assert isinstance(get_spec("a.jsx"), JavaScriptSpec)
    assert isinstance(get_spec("a.mjs"), JavaScriptSpec)
    assert get_spec("a.ts") is not None  # sanity: ts handled elsewhere
    assert get_spec("other.go") is None


def test_js_qualnames_and_kinds():
    res = parse.extract(fixture, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == expected


def test_js_byte_spans_slice_source():
    src = _load()
    res = parse.extract(fixture, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.kind == "class":
            assert sl.startswith("class "), sl
        elif s.kind == "method":
            assert sl.startswith("bar("), sl
        elif s.qualname == "double":
            assert sl.startswith("double ="), sl
        else:
            assert sl.startswith(("function ", "async function ")), sl


def test_js_sig_and_doc():
    res = parse.extract(fixture, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert by_name["load"].sig == "async function load(url)"
    assert by_name["load"].doc == "leading comment for load"
    assert by_name["Foo"].sig == "class Foo extends Base"
    assert by_name["Foo.bar"].doc == "method doc"
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_js_imports():
    res = parse.extract(fixture, _load())
    assert res is not None
    assert res.imports == ["mod-a", "mod-b", "mod-c", "mod-d"]


def test_js_require_only_symbol_free():
    # `cfg` is a require() call, not a function: no symbol, but an import.
    res = parse.extract(fixture, _load())
    assert res is not None
    assert "cfg" not in {s.qualname for s in res.symbols}
