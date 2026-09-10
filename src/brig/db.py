"""SQLite WAL index storage + incremental index pipeline.

See SPEC.md (Architecture: Storage, Incremental) and PLAN.md Phase 1a.
stdlib ``sqlite3`` only, no ORM.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1

_BUILTIN_IGNORE_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__"})

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    qualname TEXT NOT NULL,
    kind TEXT NOT NULL,
    sig TEXT NOT NULL DEFAULT '',
    doc TEXT NOT NULL DEFAULT '',
    start_byte INTEGER NOT NULL,
    end_byte INTEGER NOT NULL,
    UNIQUE(path, qualname, kind)
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    src_path TEXT NOT NULL,
    dst_spec TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    src_id INTEGER NOT NULL,
    dst_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('EXTRACTED', 'INFERRED'))
);
"""

# extract_fn(path, source) -> (symbols, imports); see parse.extract stub.
ExtractFn = Callable[[Path, bytes], tuple[Sequence[Mapping], Iterable]]


def default_root() -> Path:
    return Path.home() / ".brig"


def index_dir(root: Path | str | None = None) -> Path:
    return Path(root) if root is not None else default_root()


def _store_root(root: Path | str | None) -> Path:
    base = Path(root) if root is not None else default_root()
    return base / "index"


def db_path(slug: str, root: Path | str | None = None) -> Path:
    return _store_root(root) / f"{slug}.db"


def meta_path(slug: str, root: Path | str | None = None) -> Path:
    return _store_root(root) / f"{slug}.meta"


def norm_path(path: Path | str) -> str:
    """Lexical normalization to forward slashes (Windows-proof). No resolving."""
    return Path(path).as_posix()


def open_or_create(slug: str, root: Path | str | None = None) -> sqlite3.Connection:
    store = _store_root(root)
    store.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(store / f"{slug}.db")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_SCHEMA_SQL)
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version';").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?);",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    elif row[0] != str(SCHEMA_VERSION):
        conn.close()
        raise RuntimeError(
            f"schema version mismatch for {slug!r}: have {row[0]}, want {SCHEMA_VERSION}"
        )
    return conn


def write_meta(conn: sqlite3.Connection, slug: str, root: Path | str | None = None) -> dict:
    file_count = conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0]
    data = {
        "schema_version": SCHEMA_VERSION,
        "file_count": file_count,
        "last_indexed": datetime.now(timezone.utc).isoformat(),
    }
    path = meta_path(slug, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def read_meta(slug: str, root: Path | str | None = None) -> dict | None:
    path = meta_path(slug, root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def index_file(
    conn: sqlite3.Connection,
    path: Path | str,
    symbols: Sequence[Mapping],
    imports: Iterable[str | Mapping],
    *,
    sha256: str | None = None,
    mtime: float | None = None,
    size: int | None = None,
) -> None:
    """Upsert one file: delete stale symbols/imports for path, insert new ones."""
    key = norm_path(path)
    old_ids = [r[0] for r in conn.execute("SELECT id FROM symbols WHERE path = ?;", (key,))]
    if old_ids:
        marks = ",".join("?" for _ in old_ids)
        conn.execute(f"DELETE FROM edges WHERE src_id IN ({marks}) OR dst_id IN ({marks});", (*old_ids, *old_ids))
    conn.execute("DELETE FROM symbols WHERE path = ?;", (key,))
    conn.execute("DELETE FROM imports WHERE src_path = ?;", (key,))
    for s in symbols:
        conn.execute(
            "INSERT INTO symbols (path, qualname, kind, sig, doc, start_byte, end_byte)"
            " VALUES (?, ?, ?, ?, ?, ?, ?);",
            (
                key,
                s["qualname"],
                s["kind"],
                s.get("sig", ""),
                s.get("doc", ""),
                s["start_byte"],
                s["end_byte"],
            ),
        )
    for imp in imports:
        if isinstance(imp, Mapping):
            spec = str(imp.get("spec", imp.get("dst_spec", "")))
        else:
            spec = str(imp)
        conn.execute("INSERT INTO imports (src_path, dst_spec) VALUES (?, ?);", (key, spec))
    if sha256 is None or mtime is None or size is None:
        disk = Path(path)
        if disk.exists():
            st = disk.stat()
            data = disk.read_bytes()
            sha256 = sha256 if sha256 is not None else sha256_bytes(data)
            mtime = st.st_mtime if mtime is None else mtime
            size = st.st_size if size is None else size
        else:
            sha256 = sha256 if sha256 is not None else ""
            mtime = mtime if mtime is not None else 0.0
            size = size if size is not None else 0
    conn.execute(
        "INSERT INTO files (path, sha256, mtime, size) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(path) DO UPDATE SET sha256 = excluded.sha256,"
        " mtime = excluded.mtime, size = excluded.size;",
        (key, sha256, mtime, size),
    )
    conn.commit()


def _storage_key(path: Path | str, repo_root: Path | str | None) -> tuple[Path, str]:
    p = Path(path)
    if repo_root is not None:
        repo = Path(repo_root)
        if p.is_absolute():
            try:
                return p, p.relative_to(repo).as_posix()
            except ValueError:
                return p, p.as_posix()
        return repo / p, p.as_posix()
    return p, p.as_posix()


def needs_reindex(
    conn: sqlite3.Connection, path: Path | str, repo_root: Path | str | None = None
) -> bool:
    """True if the file needs (re)indexing.

    mtime+size fast-path; sha256 fallback when the stat differs.
    Unknown files always need indexing.
    """
    fspath, key = _storage_key(path, repo_root)
    try:
        st = fspath.stat()
    except OSError:
        return True
    row = conn.execute("SELECT sha256, mtime, size FROM files WHERE path = ?;", (key,)).fetchone()
    if row is None:
        return True
    stored_sha, stored_mtime, stored_size = row
    if stored_mtime == st.st_mtime and stored_size == st.st_size:
        return False
    try:
        current_sha = sha256_bytes(fspath.read_bytes())
    except OSError:
        return True
    return current_sha != stored_sha


def remove_file(conn: sqlite3.Connection, path: Path | str) -> None:
    key = norm_path(path)
    old_ids = [r[0] for r in conn.execute("SELECT id FROM symbols WHERE path = ?;", (key,))]
    if old_ids:
        marks = ",".join("?" for _ in old_ids)
        conn.execute(f"DELETE FROM edges WHERE src_id IN ({marks}) OR dst_id IN ({marks});", (*old_ids, *old_ids))
    conn.execute("DELETE FROM symbols WHERE path = ?;", (key,))
    conn.execute("DELETE FROM imports WHERE src_path = ?;", (key,))
    conn.execute("DELETE FROM files WHERE path = ?;", (key,))
    conn.commit()


def _load_gitignore_patterns(repo: Path) -> list[str]:
    ignore_file = repo / ".gitignore"
    if not ignore_file.exists():
        return []
    patterns: list[str] = []
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _pattern_matches(pattern: str, rel: str, is_dir: bool) -> bool:
    """Positive-form match only; callers handle '!' negation."""
    pat = pattern.strip("/")
    is_dir_pat = pattern.endswith("/")
    name = rel.rsplit("/", 1)[-1]
    hit = False
    if "/" in pat:
        hit = fnmatch.fnmatchcase(rel, pat) or (is_dir and fnmatch.fnmatchcase(rel + "/", pat))
        if not hit and is_dir_pat:
            hit = rel == pat or rel.startswith(pat + "/")
    else:
        if is_dir_pat:
            hit = rel == pat or rel.startswith(pat + "/") or (is_dir and name == pat)
        else:
            hit = fnmatch.fnmatchcase(name, pat) or fnmatch.fnmatchcase(rel, pat)
    return hit


def _is_ignored(rel: str, patterns: Sequence[str], is_dir: bool) -> bool:
    ignored = False
    for pattern in patterns:
        if pattern.startswith("!"):
            # Negation: un-ignore when the positive form matches.
            if _pattern_matches(pattern[1:], rel, is_dir):
                ignored = False
        elif _pattern_matches(pattern, rel, is_dir):
            ignored = True
    return ignored


def index_repo(
    repo_root: Path | str,
    conn: sqlite3.Connection | None = None,
    *,
    slug: str | None = None,
    index_root: Path | str | None = None,
    extract_fn: ExtractFn | None = None,
) -> dict:
    """Walk repo, index changed files, drop deleted ones. Returns stats dict."""
    repo = Path(repo_root)
    if extract_fn is None:
        from brig.parse import extract as extract_fn  # lazy: parse must stay core-free

    own_conn = conn is None
    if own_conn:
        slug = slug or repo.name
        conn = open_or_create(slug, root=index_root)
    assert conn is not None

    patterns = _load_gitignore_patterns(repo)
    indexed = skipped = removed = 0
    seen: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _BUILTIN_IGNORE_DIRS
            and not _is_ignored(
                (Path(dirpath) / d).relative_to(repo).as_posix(), patterns, is_dir=True
            )
        ]
        for filename in filenames:
            fpath = Path(dirpath) / filename
            rel = fpath.relative_to(repo).as_posix()
            if _is_ignored(rel, patterns, is_dir=False):
                continue
            seen.add(rel)
            if not needs_reindex(conn, fpath, repo_root=repo):
                skipped += 1
                continue
            try:
                source = fpath.read_bytes()
            except OSError:
                continue
            symbols, import_specs = extract_fn(fpath, source)
            st = fpath.stat()
            index_file(
                conn,
                rel,
                symbols,
                import_specs,
                sha256=sha256_bytes(source),
                mtime=st.st_mtime,
                size=st.st_size,
            )
            indexed += 1

    known = {r[0] for r in conn.execute("SELECT path FROM files;")}
    for stale in sorted(known - seen):
        remove_file(conn, stale)
        removed += 1

    if slug is not None:
        write_meta(conn, slug, root=index_root)
    if own_conn:
        conn.close()
    return {"indexed": indexed, "skipped": skipped, "removed": removed}
