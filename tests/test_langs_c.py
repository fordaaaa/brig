"""Phase polyglot: C LanguageSpec tests. TDD: written before langs/c.py."""

from __future__ import annotations

from pathlib import Path

from brig import parse
from brig.langs import get_spec

FIXTURE = Path(__file__).parent / "fixtures" / "sample.c"

EXPECTED = {
    "add": "function",
    "Point": "class",
    "Color": "class",
}


def _load() -> bytes:
    return FIXTURE.read_bytes()


def test_get_spec_dispatches_c():
    from brig.langs.c import CSpec

    spec = get_spec(str(FIXTURE))
    assert isinstance(spec, CSpec)
    assert isinstance(get_spec("x.h"), CSpec)


def test_c_qualnames_and_kinds():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    got = {s.qualname: s.kind for s in res.symbols}
    assert got == EXPECTED


def test_c_byte_spans_slice_source():
    src = _load()
    res = parse.extract(FIXTURE, src)
    assert res is not None
    for s in res.symbols:
        sl = src[s.start_byte : s.end_byte].decode("utf-8")
        if s.qualname == "add":
            assert "int add(" in sl, sl
        else:
            assert sl.lstrip().startswith(("struct ", "enum ")), sl


def test_c_sig_and_doc():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    by_name = {s.qualname: s for s in res.symbols}
    assert "int add(" in by_name["add"].sig
    assert "Add two numbers." in by_name["add"].doc
    for s in res.symbols:
        assert len(s.sig) <= 200
        assert len(s.doc) <= 500


def test_c_imports():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert res.imports == ["stdio.h", "my.h"]


def test_c_path_stamped():
    res = parse.extract(FIXTURE, _load())
    assert res is not None
    assert all(s.path == str(FIXTURE) for s in res.symbols)
