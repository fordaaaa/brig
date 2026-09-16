# Polyglot: C# LanguageSpec tests. TDD: written before langs/csharp.py.

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec

fixture = Path(__file__).parent / "fixtures" / "sample.cs"

expected = {
    "MyApp.Greeter": "class",
    "MyApp.Greeter.Greet": "method",
    "MyApp.Greeter.Greeter": "method",
}


def _load() -> bytes:
    return fixture.read_bytes()


def test_get_spec_dispatches_csharp():
    from brig.langs.csharp import CSharpSpec

    assert isinstance(get_spec(str(fixture)), CSharpSpec)
    assert isinstance(get_spec("x.CS"), CSharpSpec)


def test_csharp_qualnames_and_kinds():
    res = parse.extract(fixture, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == expected


def test_csharp_byte_spans_slice_source():
    src = _load()
    res = parse.extract(fixture, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.kind == "class":
            assert "class Greeter" in sl, sl
        else:
            assert "Greet(" in sl or "Greeter(" in sl, sl


def test_csharp_sig_and_doc():
    res = parse.extract(fixture, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert "Greeter class." in by_name["MyApp.Greeter"].doc
    assert "Greet the user." in by_name["MyApp.Greeter.Greet"].doc
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_csharp_imports():
    res = parse.extract(fixture, _load())
    assert res is not None
    assert res.imports == ["System", "System.Collections.Generic"]


def test_csharp_path_stamped():
    res = parse.extract(fixture, _load())
    assert res is not None
    assert all(s.path == str(fixture) for s in res.symbols)
