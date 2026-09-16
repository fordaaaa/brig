"""Polyglot: Java LanguageSpec tests. TDD: written before langs/java.py."""

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec

FIXTURE = Path(__file__).parent / "fixtures" / "sample.java"

EXPECTED = {
    "com.example.Greeter": "class",
    "com.example.Greeter.greet": "method",
    "com.example.Greeter.Greeter": "method",
}


def _load() -> bytes:
    return FIXTURE.read_bytes()


def test_get_spec_dispatches_java():
    from brig.langs.java import JavaSpec

    assert isinstance(get_spec(str(FIXTURE)), JavaSpec)
    assert isinstance(get_spec("x.JAVA"), JavaSpec)


def test_java_qualnames_and_kinds():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == EXPECTED


def test_java_byte_spans_slice_source():
    src = _load()
    res = parse.extract(FIXTURE, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.kind == "class":
            assert "class Greeter" in sl, sl
        else:
            assert "greet(" in sl or "Greeter(" in sl, sl


def test_java_sig_and_doc():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert "Greeter class." in by_name["com.example.Greeter"].doc
    assert "Greet a name." in by_name["com.example.Greeter.greet"].doc
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_java_imports():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert res.imports == ["java.util.List", "java.util.Collections.emptyList"]


def test_java_path_stamped():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert all(s.path == str(FIXTURE) for s in res.symbols)
