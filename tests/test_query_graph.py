"""Phase 2: query graph tests — INFERRED call edges, callers/callees, blast_radius.

TDD: written before src/brig/query.py. Uses the same synthetic repo
shape as tests/test_query.py (duplicated builder: keep files independent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brig import db, query

HELPERS_PY = '''"""Helper utilities."""

def helper(name):
    """Greet by name."""
    return "hi " + name


class Worker:
    """Does work."""

    def run(self, name):
        """Run worker."""
        return helper(name)
'''

MAIN_PY = '''import helpers
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

APP_TS = '''import { formatName } from "./lib";

export function greet(name: string): string {
  return formatName(name);
}

export function unusedTs(): number {
  return 42;
}
'''

LIB_TS = '''/** Format a name. */
export function formatName(name: string): string {
  return name.trim();
}
'''


@pytest.fixture
def qrepo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "helpers.py").write_text(HELPERS_PY, encoding="utf-8")
    (repo / "main.py").write_text(MAIN_PY, encoding="utf-8")
    (repo / "app.ts").write_text(APP_TS, encoding="utf-8")
    (repo / "lib.ts").write_text(LIB_TS, encoding="utf-8")
    return repo


@pytest.fixture
def conn(qrepo: Path, tmp_path: Path):
    c = db.open_or_create("qg", root=tmp_path / "home")
    db.index_repo(qrepo, conn=c)
    query.infer_call_edges(c, repo_root=qrepo)
    try:
        yield c, qrepo
    finally:
        c.close()


def _names(res) -> set[str]:
    return {r["qualname"] for r in res["results"]}


# --- infer_call_edges ---


def test_infer_call_edges_expected_set(conn):
    c, repo = conn
    got = {
        (r[0], r[1])
        for r in c.execute(
            "SELECT s1.qualname, s2.qualname FROM edges e"
            " JOIN symbols s1 ON s1.id = e.src_id"
            " JOIN symbols s2 ON s2.id = e.dst_id"
            " WHERE e.kind = 'calls';"
        )
    }
    assert got == {
        ("main", "helper"),
        ("entry", "main"),
        ("Worker.run", "helper"),
        ("greet", "formatName"),
    }
    confs = {r[0] for r in c.execute("SELECT DISTINCT confidence FROM edges;")}
    assert confs == {"INFERRED"}


def test_infer_call_edges_idempotent(conn):
    c, repo = conn
    before = c.execute("SELECT COUNT(*) FROM edges;").fetchone()[0]
    res = query.infer_call_edges(c, repo_root=repo)
    after = c.execute("SELECT COUNT(*) FROM edges;").fetchone()[0]
    assert res["edges_added"] == before == after == 4


def test_infer_no_self_edges(conn):
    c, _ = conn
    rows = c.execute("SELECT src_id, dst_id FROM edges;").fetchall()
    assert rows, "expected inferred edges"
    assert all(s != d for s, d in rows)


# --- callers / callees ---


def test_callees_direct(conn):
    c, repo = conn
    res = query.callees(c, "main", repo_root=repo)
    assert _names(res) == {"helper"}


def test_callees_transitive_depth2(conn):
    c, repo = conn
    res = query.callees(c, "entry", depth=2, repo_root=repo)
    by_depth = {r["qualname"]: r["depth"] for r in res["results"]}
    assert by_depth == {"main": 1, "helper": 2}


def test_callers_direct(conn):
    c, repo = conn
    res = query.callers(c, "helper", repo_root=repo)
    assert _names(res) == {"main", "Worker.run"}


def test_callers_transitive_depth2(conn):
    c, repo = conn
    res = query.callers(c, "helper", depth=2, repo_root=repo)
    by_depth = {r["qualname"]: r["depth"] for r in res["results"]}
    assert by_depth == {"main": 1, "Worker.run": 1, "entry": 2}


def test_callers_depth_capped_at_3(conn):
    c, repo = conn
    res = query.callers(c, "helper", depth=99, repo_root=repo)
    assert res["results"], "clamped depth must still return results"
    assert all(r["depth"] <= 3 for r in res["results"])


def test_callers_depth_zero_empty(conn):
    c, repo = conn
    res = query.callers(c, "helper", depth=0, repo_root=repo)
    assert res["results"] == []


def test_callers_unknown_qualname(conn):
    c, repo = conn
    res = query.callers(c, "zzz_no_such_symbol", repo_root=repo)
    assert res["results"] == []
    assert "scan_counts" in res["_meta"]


def test_callees_leaf_empty_with_scan_counts(conn):
    c, repo = conn
    res = query.callees(c, "lonely", repo_root=repo)
    assert res["results"] == []
    assert "scan_counts" in res["_meta"]


def test_graph_walk_cycle_safe(conn):
    c, repo = conn
    ids = {r[0]: r[1] for r in c.execute("SELECT qualname, id FROM symbols;")}
    query.add_edge(c, ids["main"], ids["entry"], "calls", "INFERRED")
    query.add_edge(c, ids["entry"], ids["main"], "calls", "INFERRED")
    res = query.callers(c, "main", depth=3, repo_root=repo)
    assert "entry" in _names(res)  # terminates, no hang
    res2 = query.callees(c, "main", depth=3, repo_root=repo)
    assert "entry" in _names(res2)


# --- blast_radius ---


def test_blast_symbol_splits_confirmed_vs_potential(conn):
    c, repo = conn
    res = query.blast_radius(c, "helper", repo_root=repo)
    pot = {e["qualname"] for e in res["potential"]}
    assert pot == {"main", "Worker.run"}
    # reverse importers of helpers.py land in confirmed.
    imp_paths = {e["path"] for e in res["confirmed"] if e["kind"] == "import"}
    assert "main.py" in imp_paths
    assert all(e["confidence"] == "INFERRED" for e in res["potential"])


def test_blast_file_reverse_imports(conn):
    c, repo = conn
    res = query.blast_radius(c, "helpers.py", repo_root=repo)
    imp_paths = {e["path"] for e in res["confirmed"] if e["kind"] == "import"}
    assert imp_paths == {"main.py"}
    pot = {e["qualname"] for e in res["potential"]}
    assert pot == {"main", "Worker.run"}


def test_blast_ts_file(conn):
    c, repo = conn
    res = query.blast_radius(c, "lib.ts", repo_root=repo)
    imp_paths = {e["path"] for e in res["confirmed"] if e["kind"] == "import"}
    assert "app.ts" in imp_paths
    assert {e["qualname"] for e in res["potential"]} == {"greet"}


def test_blast_unknown_target(conn):
    c, repo = conn
    res = query.blast_radius(c, "zzz_no_such_target", repo_root=repo)
    assert res["confirmed"] == []
    assert res["potential"] == []
    assert "scan_counts" in res["_meta"]


def test_search_degree_tiebreak_after_infer(conn):
    c, repo = conn
    res = query.search_symbols(c, "e", repo_root=repo)
    names = [r["qualname"] for r in res["results"]]
    # helper has the highest in-degree among 'e' matches -> must lead.
    assert names[0] == "helper"
    assert "lonely" in names  # low-degree match still present, ranked lower
    assert names.index("helper") < names.index("lonely")


def test_graph_meta_fresh(conn):
    c, repo = conn
    for res in (
        query.infer_call_edges(c, repo_root=repo),
        query.callers(c, "helper", repo_root=repo),
        query.callees(c, "entry", depth=2, repo_root=repo),
        query.blast_radius(c, "helper", repo_root=repo),
    ):
        meta = res["_meta"]
        assert meta["freshness"] == "fresh"
        assert 0.0 <= meta["confidence"] <= 1.0
