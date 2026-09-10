"""Phase 1b: python LanguageSpec tests. TDD: written before langs/python.py."""

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec
from brig.langs.python import PythonSpec

FIXTURE = Path(__file__).parent / "fixtures" / "sample.py"

EXPECTED = {
    "top": "function",
    "top.nested": "function",
    "top.Inner": "class",
    "top.Inner.method": "method",
    "Foo": "class",
    "Foo.bar": "method",
}


def _load() -> bytes:
    return FIXTURE.read_bytes()


def test_get_spec_dispatches_py():
    spec = get_spec(str(FIXTURE))
    assert isinstance(spec, PythonSpec)
    assert get_spec("other.js") is not None  # sanity: registry has more langs
    assert get_spec("other.go") is None


def test_python_qualnames_and_kinds():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == EXPECTED


def test_python_byte_spans_slice_source():
    src = _load()
    res = parse.extract(FIXTURE, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.kind == "class":
            assert sl.startswith("class "), sl
        else:
            assert sl.startswith(("def ", "async def ")), sl


def test_python_sig_and_doc():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert by_name["top"].sig == "async def top(a, b=1):"
    assert by_name["top"].doc == "Top docstring."
    assert by_name["top.nested"].doc == "Nested doc."
    assert by_name["Foo"].sig == "class Foo(Base):"
    assert by_name["Foo"].doc == "Class doc."
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_python_imports():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert res.imports == ["os", "a.b", "x.y"]


def test_python_spec_extract_str_source():
    res = PythonSpec().extract(FIXTURE.read_text(encoding="utf-8"))
    assert {s.qualname for s in res.symbols} == set(EXPECTED)


def test_python_path_stamped():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert all(s.path == str(FIXTURE) for s in res.symbols)


def test_python_unpack_tuple_compat():
    # db.index_repo does `symbols, imports = extract_fn(path, source)`.
    symbols, imports = parse.extract(FIXTURE, _load())
    assert len(symbols) == len(EXPECTED)
    assert imports == ["os", "a.b", "x.y"]
