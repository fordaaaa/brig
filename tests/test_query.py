# Phase 2: query core tests — search/get_symbol/outline/check_refs/_meta.
# TDD: written before src/brig/query.py. Synthetic multi-file repo
# (python + ts, cross-file imports) indexed via db.index_repo.

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from brig import db, query

helpers_py = '''"""Helper utilities."""

def helper(name):
    """Greet by name."""
    return "hi " + name


class Worker:
    """Does work."""

    def run(self, name):
        """Run worker."""
        return helper(name)
'''

main_py = '''import helpers
from helpers import helper


def main():
    """Entry point."""
    return helper("world") + helpers.helper("again")


def entry():
    """Boot."""
    return main()


def lonely():
    """Nobody calls this."""
    return 0
'''

app_ts = '''import { formatName } from "./lib";

export function greet(name: string): string {
  return formatName(name);
}

export function unusedTs(): number {
  return 42;
}
'''

lib_ts = '''/** Format a name. */
export function formatName(name: string): string {
  return name.trim();
}
'''


@pytest.fixture
def qrepo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "helpers.py").write_text(helpers_py, encoding="utf-8")
    (repo / "main.py").write_text(main_py, encoding="utf-8")
    (repo / "app.ts").write_text(app_ts, encoding="utf-8")
    (repo / "lib.ts").write_text(lib_ts, encoding="utf-8")
    return repo


@pytest.fixture
def conn(qrepo: Path, tmp_path: Path):
    c = db.open_or_create("q", root=tmp_path / "home")
    db.index_repo(qrepo, conn=c)
    try:
        yield c, qrepo
    finally:
        c.close()


def _db_symbols(c: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in c.execute("SELECT qualname, id FROM symbols;")}


# --- search_symbols ---


def test_search_exact_qualname_ranks_first(conn):
    c, repo = conn
    res = query.search_symbols(c, "helper", repo_root=repo)
    assert res["results"], "expected hits for 'helper'"
    assert res["results"][0]["qualname"] == "helper"
    assert "_meta" in res


def test_search_qualname_substring(conn):
    c, repo = conn
    res = query.search_symbols(c, "help", repo_root=repo)
    names = [r["qualname"] for r in res["results"]]
    assert "helper" in names


def test_search_doc_substring(conn):
    c, repo = conn
    res = query.search_symbols(c, "Greet by name", repo_root=repo)
    names = [r["qualname"] for r in res["results"]]
    assert "helper" in names


def test_search_sig_substring(conn):
    c, repo = conn
    res = query.search_symbols(c, "Entry point", repo_root=repo)
    names = [r["qualname"] for r in res["results"]]
    assert "main" in names


def test_search_absent_returns_empty_with_scan_counts(conn):
    c, repo = conn
    res = query.search_symbols(c, "zzz_no_such_symbol", repo_root=repo)
    assert res["results"] == []
    sc = res["_meta"]["scan_counts"]
    assert sc["files_scanned"] == 4
    assert sc["symbols_scanned"] == len(_db_symbols(c))


def test_search_empty_query(conn):
    c, repo = conn
    res = query.search_symbols(c, "", repo_root=repo)
    assert res["results"] == []
    assert "scan_counts" in res["_meta"]


# --- get_symbol ---


def test_get_symbol_byte_exact_slice(conn):
    c, repo = conn
    ids = _db_symbols(c)
    res = query.get_symbol(c, ids["helper"], repo_root=repo)
    assert res["error"] is None
    assert res["symbol"]["qualname"] == "helper"
    assert res["source"].startswith("def helper(")
    assert "Greet by name." in res["source"]
    # byte-exact: slice of the file on disk must equal returned source.
    raw = (repo / "helpers.py").read_bytes()
    s = res["symbol"]
    assert raw[s["start_byte"] : s["end_byte"]].decode("utf-8") == res["source"]


def test_get_symbol_unknown_id(conn):
    c, repo = conn
    res = query.get_symbol(c, 999999, repo_root=repo)
    assert res["symbol"] is None
    assert res["error"] == "not_found"
    assert "scan_counts" in res["_meta"]


def test_get_symbol_missing_file_is_stale(conn):
    c, repo = conn
    ids = _db_symbols(c)
    (repo / "helpers.py").unlink()
    res = query.get_symbol(c, ids["helper"], repo_root=repo)
    assert res["source"] is None
    assert res["error"] is not None
    assert res["_meta"]["freshness"] == "stale_index"


# --- get_outline ---


def test_get_outline_repo_wide(conn):
    c, repo = conn
    res = query.get_outline(c, repo_root=repo)
    files = res["files"]
    assert set(files) == {"helpers.py", "main.py", "app.ts", "lib.ts"}
    assert {s["qualname"] for s in files["helpers.py"]} == {"helper", "Worker", "Worker.run"}
    assert {s["qualname"] for s in files["main.py"]} == {"main", "entry", "lonely"}
    assert {s["qualname"] for s in files["app.ts"]} == {"greet", "unusedTs"}
    assert {s["qualname"] for s in files["lib.ts"]} == {"formatName"}
    kinds = {s["qualname"]: s["kind"] for s in files["helpers.py"]}
    assert kinds == {"helper": "function", "Worker": "class", "Worker.run": "method"}
    # no bodies: function bodies must not leak into the outline.
    for syms in files.values():
        for s in syms:
            assert "return" not in s["sig"]
            assert "body" not in s


def test_get_outline_single_file(conn):
    c, repo = conn
    res = query.get_outline(c, "helpers.py", repo_root=repo)
    assert set(res["files"]) == {"helpers.py"}
    assert len(res["files"]["helpers.py"]) == 3


def test_get_outline_unknown_file(conn):
    c, repo = conn
    res = query.get_outline(c, "nope.py", repo_root=repo)
    assert res["files"] == {}
    assert res["error"] == "not_found"
    assert "scan_counts" in res["_meta"]


# --- check_refs ---


def test_check_refs_import_and_text(conn):
    c, repo = conn
    res = query.check_refs(c, "helpers", repo_root=repo)
    assert res["is_referenced"] is True
    kinds = {e["kind"] for e in res["evidence"]}
    assert "import" in kinds
    assert "text" in kinds


def test_check_refs_symbol_and_text(conn):
    c, repo = conn
    res = query.check_refs(c, "helper", repo_root=repo)
    assert res["is_referenced"] is True
    kinds = {e["kind"] for e in res["evidence"]}
    assert "symbol" in kinds
    assert "text" in kinds


def test_check_refs_ts_import_spec(conn):
    c, repo = conn
    res = query.check_refs(c, "lib", repo_root=repo)
    assert res["is_referenced"] is True
    assert any(e["kind"] == "import" for e in res["evidence"])


def test_check_refs_absent_has_scan_counts(conn):
    c, repo = conn
    res = query.check_refs(c, "zzz_no_such_ident", repo_root=repo)
    assert res["is_referenced"] is False
    assert res["evidence"] == []
    assert res["scan_counts"]["files_scanned"] == 4
    assert res["scan_counts"]["symbols_scanned"] == len(_db_symbols(c))


# --- _meta envelope ---


def test_meta_envelope_fresh_everywhere(conn):
    c, repo = conn
    ids = _db_symbols(c)
    for res in (
        query.search_symbols(c, "helper", repo_root=repo),
        query.get_symbol(c, ids["helper"], repo_root=repo),
        query.get_outline(c, repo_root=repo),
        query.check_refs(c, "helper", repo_root=repo),
    ):
        meta = res["_meta"]
        assert meta["freshness"] == "fresh"
        assert 0.0 <= meta["confidence"] <= 1.0


def test_meta_edited_uncommitted_after_edit(conn):
    c, repo = conn
    ids = _db_symbols(c)
    with (repo / "helpers.py").open("a", encoding="utf-8") as f:
        f.write("\n# trailing comment\n")
    res = query.get_symbol(c, ids["helper"], repo_root=repo)
    assert res["_meta"]["freshness"] == "edited_uncommitted"
    assert res["source"] is not None  # span still readable
