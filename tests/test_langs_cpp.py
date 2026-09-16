"""Polyglot: C++ LanguageSpec tests. TDD: written before langs/cpp.py."""

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec

FIXTURE = Path(__file__).parent / "fixtures" / "sample.cpp"

EXPECTED = {
    "Greeter": "class",
    "Greeter.Greeter": "method",
    "Greeter.greet": "method",
    "double_it": "function",
}


def _load() -> bytes:
    return FIXTURE.read_bytes()


def test_get_spec_dispatches_cpp():
    from brig.langs.cpp import CppSpec

    assert isinstance(get_spec(str(FIXTURE)), CppSpec)
    assert isinstance(get_spec("x.hpp"), CppSpec)
    assert isinstance(get_spec("x.cc"), CppSpec)
    # C owns .h per plan decision.
    from brig.langs.c import CSpec

    assert isinstance(get_spec("x.h"), CSpec)


def test_cpp_qualnames_and_kinds():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == EXPECTED


def test_cpp_byte_spans_slice_source():
    src = _load()
    res = parse.extract(FIXTURE, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.qualname == "Greeter":
            assert sl.lstrip().startswith("class "), sl
        elif s.qualname == "double_it":
            assert "double_it(" in sl, sl
        else:
            assert "Greeter(" in sl or "greet(" in sl, sl


def test_cpp_sig_and_doc():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert "Greeter class." in by_name["Greeter"].doc
    assert "Greet a name." in by_name["Greeter.greet"].doc
    assert "Double a value." in by_name["double_it"].doc
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_cpp_imports():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert res.imports == ["vector", "foo.h"]


def test_cpp_path_stamped():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert all(s.path == str(FIXTURE) for s in res.symbols)
