# Phase 1a: incremental indexing + index_repo tests. TDD: written before pipeline.

from __future__ import annotations

from pathlib import Path

import pytest

from brig import db


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "brig-home"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    return d


def _syms(names=("f",)):
    return [
        {"qualname": n, "kind": "function", "sig": f"{n}()", "doc": "", "start_byte": 0, "end_byte": 10}
        for n in names
    ]


def test_index_file_upsert_replaces_stale(root: Path):
    conn = db.open_or_create("r", root=root)
    try:
        db.index_file(conn, "a.py", _syms(("f", "g")), [], sha256="a" * 64, mtime=1.0, size=9)
        db.index_file(conn, "a.py", _syms(("f",)), [], sha256="b" * 64, mtime=2.0, size=9)
        rows = conn.execute("SELECT qualname FROM symbols WHERE path = 'a.py' ORDER BY qualname;").fetchall()
        assert [r[0] for r in rows] == ["f"]
        files = conn.execute("SELECT sha256, mtime FROM files WHERE path = 'a.py';").fetchone()
        assert files == ("b" * 64, 2.0)
    finally:
        conn.close()


def test_second_index_skips_unchanged_file_no_rewrites(root: Path, repo: Path):
    f = repo / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    conn = db.open_or_create("r", root=root)
    try:
        n1 = db.index_repo(repo, conn=conn)
        assert n1["indexed"] == 1
        before = conn.execute("SELECT id FROM symbols ORDER BY id;").fetchall()
        n2 = db.index_repo(repo, conn=conn)
        assert n2["indexed"] == 0
        assert n2["skipped"] == 1
        after = conn.execute("SELECT id FROM symbols ORDER BY id;").fetchall()
        assert before == after  # zero symbol rewrites: rowid stability
    finally:
        conn.close()


def test_needs_reindex_detects_content_change(root: Path, repo: Path):
    f = repo / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    conn = db.open_or_create("r", root=root)
    try:
        db.index_repo(repo, conn=conn)
        assert db.needs_reindex(conn, str(f), repo_root=repo) is False
        f.write_text("x = 2\n", encoding="utf-8")  # same size, different content
        assert db.needs_reindex(conn, str(f), repo_root=repo) is True
    finally:
        conn.close()


def test_needs_reindex_unknown_file_is_true(root: Path, repo: Path):
    f = repo / "new.py"
    f.write_text("x = 1\n", encoding="utf-8")
    conn = db.open_or_create("r", root=root)
    try:
        assert db.needs_reindex(conn, str(f), repo_root=repo) is True
    finally:
        conn.close()


def test_remove_file(root: Path):
    conn = db.open_or_create("r", root=root)
    try:
        db.index_file(conn, "a.py", _syms(("f",)), ["os"], sha256="a" * 64, mtime=1.0, size=9)
        db.remove_file(conn, "a.py")
        assert conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM imports;").fetchone()[0] == 0
    finally:
        conn.close()


def test_index_repo_removes_deleted_files(root: Path, repo: Path):
    a = repo / "a.py"
    a.write_text("x = 1\n", encoding="utf-8")
    conn = db.open_or_create("r", root=root)
    try:
        db.index_repo(repo, conn=conn)
        assert conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0] == 1
        a.unlink()
        stats = db.index_repo(repo, conn=conn)
        assert stats["removed"] == 1
        assert conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0] == 0
    finally:
        conn.close()


def test_index_repo_uses_extract_fn(root: Path, repo: Path):
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    calls: list[str] = []

    def fake_extract(path, source):
        calls.append(str(path))
        return (
            [{"qualname": "f", "kind": "function", "start_byte": 0, "end_byte": 5}],
            ["os"],
        )

    conn = db.open_or_create("r", root=root)
    try:
        db.index_repo(repo, conn=conn, extract_fn=fake_extract)
        assert len(calls) == 1
        assert conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0] == 1
        assert conn.execute("SELECT dst_spec FROM imports;").fetchone()[0] == "os"
    finally:
        conn.close()


def test_index_repo_respects_gitignore_and_builtin(root: Path, repo: Path):
    (repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (repo / "ignored.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "kept.py").write_text("x = 1\n", encoding="utf-8")
    venv_mod = repo / ".venv" / "m.py"
    venv_mod.parent.mkdir()
    venv_mod.write_text("x = 1\n", encoding="utf-8")
    nm_mod = repo / "node_modules" / "m.js"
    nm_mod.parent.mkdir()
    nm_mod.write_text("x = 1\n", encoding="utf-8")
    pyc = repo / "__pycache__" / "m.pyc"
    pyc.parent.mkdir()
    pyc.write_bytes(b"\x00")
    gitf = repo / ".git" / "HEAD"
    gitf.parent.mkdir()
    gitf.write_text("ref\n", encoding="utf-8")

    seen: list[str] = []

    def fake_extract(path, source):
        seen.append(str(path))
        return ([], [])

    conn = db.open_or_create("r", root=root)
    try:
        db.index_repo(repo, conn=conn, extract_fn=fake_extract)
        names = [Path(p).name for p in seen]
        assert "kept.py" in names
        assert "ignored.py" not in names
        assert "m.py" not in names
        assert "m.js" not in names
        assert "HEAD" not in names
        assert not any("__pycache__" in p for p in seen)
    finally:
        conn.close()
