"""Phase 1a: db core tests — open/create, schema, sidecar. TDD: written before db.py."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from brig import db


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "brig-home"


def test_open_or_create_creates_db_and_dir(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        db_path = root / "index" / "myrepo.db"
        assert db_path.exists()
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_schema_tables_exist(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
        assert {"files", "symbols", "imports", "edges"} <= tables
    finally:
        conn.close()


def test_schema_version_guard(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    conn.close()
    # Corrupt the stored version -> reopen must refuse.
    raw = sqlite3.connect(root / "index" / "myrepo.db")
    raw.execute("UPDATE schema_meta SET value = '9999' WHERE key = 'schema_version';")
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError):
        db.open_or_create("myrepo", root=root)


def test_sidecar_meta_written(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        db.write_meta(conn, "myrepo", root=root)
        meta_path = root / "index" / "myrepo.meta"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == db.SCHEMA_VERSION
        assert data["file_count"] == 0
        assert "last_indexed" in data
    finally:
        conn.close()


def test_sidecar_meta_file_count(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        db.index_file(
            conn,
            "a.py",
            [{"qualname": "f", "kind": "function", "start_byte": 0, "end_byte": 10}],
            [],
            sha256="x" * 64,
            mtime=1.0,
            size=10,
        )
        db.write_meta(conn, "myrepo", root=root)
        data = json.loads((root / "index" / "myrepo.meta").read_text(encoding="utf-8"))
        assert data["file_count"] == 1
    finally:
        conn.close()


def test_paths_stored_forward_slashes(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        db.index_file(
            conn,
            "a\\b\\c.py",
            [{"qualname": "f", "kind": "function", "start_byte": 0, "end_byte": 5}],
            [],
            sha256="y" * 64,
            mtime=1.0,
            size=5,
        )
        row = conn.execute("SELECT path FROM files;").fetchone()
        assert row[0] == "a/b/c.py"
        row = conn.execute("SELECT path FROM symbols;").fetchone()
        assert row[0] == "a/b/c.py"
    finally:
        conn.close()


def test_symbols_unique_path_qualname_kind(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        sym = {"qualname": "f", "kind": "function", "start_byte": 0, "end_byte": 5}
        db.index_file(conn, "a.py", [sym], [], sha256="a" * 64, mtime=1.0, size=5)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO symbols (path, qualname, kind, sig, doc, start_byte, end_byte)"
                " VALUES (?, ?, ?, '', '', ?, ?)",
                ("a.py", "f", "function", 0, 5),
            )
    finally:
        conn.close()


def test_edges_confidence_check(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO edges (src_id, dst_id, kind, confidence) VALUES (1, 2, 'calls', 'GUESSED');"
            )
    finally:
        conn.close()


def test_imports_store_spec_string(root: Path):
    conn = db.open_or_create("myrepo", root=root)
    try:
        db.index_file(conn, "a.py", [], ["brig.db"], sha256="b" * 64, mtime=1.0, size=5)
        row = conn.execute("SELECT src_path, dst_spec FROM imports;").fetchone()
        assert row == ("a.py", "brig.db")
    finally:
        conn.close()
