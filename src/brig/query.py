"""Query tools (search, outline, refs, callers, blast). See SPEC.md (Tool surface).

Logic layer only (no CLI/MCP wiring): every public function takes an open
``sqlite3`` connection from ``brig.db`` plus an optional ``repo_root`` used
to resolve the relative ``path`` keys stored in the index, and returns a
plain-data dict carrying a ``_meta`` envelope
``{freshness, confidence, scan_counts?}``.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

FRESH = "fresh"
EDITED = "edited_uncommitted"
STALE = "stale_index"

MAX_DEPTH = 3

_CONFIDENCE = {FRESH: 1.0, EDITED: 0.5, STALE: 0.0}
_SEVERITY = {FRESH: 0, EDITED: 1, STALE: 2}

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REL_PREFIX_RE = re.compile(r"^(?:\./|\.\./)+")

_SYMBOL_COLS = "id, path, qualname, kind, sig, doc, start_byte, end_byte"


# --- _meta envelope ---


def _disk_path(path: str, repo_root: Path | str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root) / path
    return Path(path)


def freshness_for_file(
    conn: sqlite3.Connection, path: str, repo_root: Path | str | None = None
) -> str:
    """Freshness of one indexed file: fresh | edited_uncommitted | stale_index.

    fresh = stored sha matches the bytes on disk; edited_uncommitted = sha
    differs (disk mtime newer); stale_index = missing from disk or index.
    """
    row = conn.execute(
        "SELECT sha256, mtime FROM files WHERE path = ?;", (path,)
    ).fetchone()
    disk = _disk_path(path, repo_root)
    try:
        st = disk.stat()
    except OSError:
        return STALE
    if row is None:
        return STALE
    stored_sha, stored_mtime = row
    try:
        data = disk.read_bytes()
    except OSError:
        return STALE
    if hashlib.sha256(data).hexdigest() == stored_sha:
        return FRESH
    if st.st_mtime >= stored_mtime:
        return EDITED
    return STALE


def _scan_counts(conn: sqlite3.Connection, extra: dict | None = None) -> dict:
    counts = {
        "files_scanned": conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0],
        "symbols_scanned": conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0],
    }
    if extra:
        counts.update(extra)
    return counts


def _worst(freshnesses) -> str:
    worst = FRESH
    for f in freshnesses:
        if _SEVERITY.get(f, 0) > _SEVERITY[worst]:
            worst = f
    return worst


def _meta(conn: sqlite3.Connection, freshness: str, scan_counts: dict | None = None) -> dict:
    meta: dict = {"freshness": freshness, "confidence": _CONFIDENCE[freshness]}
    if scan_counts is not None:
        meta["scan_counts"] = dict(scan_counts)
    return meta


def _repo_freshness(conn: sqlite3.Connection, repo_root: Path | str | None) -> str:
    paths = [r[0] for r in conn.execute("SELECT path FROM files;")]
    if not paths:
        return FRESH
    return _worst(freshness_for_file(conn, p, repo_root) for p in paths)


def _symbol_row(row: tuple) -> dict:
    sid, path, qualname, kind, sig, doc, start_byte, end_byte = row
    return {
        "id": sid,
        "path": path,
        "qualname": qualname,
        "kind": kind,
        "sig": sig or "",
        "doc": doc or "",
        "start_byte": start_byte,
        "end_byte": end_byte,
    }


def _degrees(conn: sqlite3.Connection) -> dict[int, int]:
    deg: dict[int, int] = {}
    for src, dst in conn.execute("SELECT src_id, dst_id FROM edges;"):
        deg[src] = deg.get(src, 0) + 1
        deg[dst] = deg.get(dst, 0) + 1
    return deg


# --- search_symbols ---


def search_symbols(
    conn: sqlite3.Connection, q: str, repo_root: Path | str | None = None
) -> dict:
    """Ranked substring search (stdlib only, no BM25 dep).

    exact qualname match > qualname substring > sig/doc substring;
    ties broken by symbol degree (edges touching the symbol).
    """
    counts = _scan_counts(conn)
    results: list[dict] = []
    if q:
        ql = q.lower()
        deg = _degrees(conn)
        ranked: list[tuple[int, int, str, dict]] = []
        for row in conn.execute(f"SELECT {_SYMBOL_COLS} FROM symbols;"):
            sym = _symbol_row(row)
            if q == sym["qualname"]:
                rank, base = 0, 1000
            elif ql in sym["qualname"].lower():
                rank, base = 1, 100
            elif ql in sym["sig"].lower() or ql in sym["doc"].lower():
                rank, base = 2, 10
            else:
                continue
            d = deg.get(sym["id"], 0)
            sym["score"] = base + d
            ranked.append((rank, -d, sym["qualname"], sym))
        ranked.sort(key=lambda t: (t[0], t[1], t[2]))
        results = [t[3] for t in ranked]
    return {
        "results": results,
        "_meta": _meta(conn, _repo_freshness(conn, repo_root), counts),
    }


# --- get_symbol ---


def get_symbol(
    conn: sqlite3.Connection, symbol_id: int, repo_root: Path | str | None = None
) -> dict:
    """Full symbol row + byte-exact source slice read from disk."""
    counts = _scan_counts(conn)
    row = conn.execute(
        f"SELECT {_SYMBOL_COLS} FROM symbols WHERE id = ?;", (symbol_id,)
    ).fetchone()
    if row is None:
        return {
            "symbol": None,
            "source": None,
            "error": "not_found",
            "_meta": _meta(conn, STALE, counts),
        }
    sym = _symbol_row(row)
    freshness = freshness_for_file(conn, sym["path"], repo_root)
    try:
        data = _disk_path(sym["path"], repo_root).read_bytes()
    except OSError:
        return {
            "symbol": sym,
            "source": None,
            "error": "file_missing",
            "_meta": _meta(conn, STALE, counts),
        }
    sb, eb = sym["start_byte"], sym["end_byte"]
    if not (0 <= sb <= eb <= len(data)):
        return {
            "symbol": sym,
            "source": None,
            "error": "span_out_of_range",
            "_meta": _meta(conn, freshness, counts),
        }
    return {
        "symbol": sym,
        "source": data[sb:eb].decode("utf-8", errors="replace"),
        "error": None,
        "_meta": _meta(conn, freshness, counts),
    }


# --- get_outline ---


def get_outline(
    conn: sqlite3.Connection, path: str | None = None, repo_root: Path | str | None = None
) -> dict:
    """Repo outline (file -> names/kinds/sigs) or single-file outline. No bodies."""
    counts = _scan_counts(conn)
    keys: list[str]
    if path is not None:
        keys = [Path(path).as_posix()]
    else:
        keys = [r[0] for r in conn.execute("SELECT path FROM files ORDER BY path;")]
    files: dict[str, list[dict]] = {}
    freshness_by_file: dict[str, str] = {}
    for key in keys:
        rows = conn.execute(
            "SELECT qualname, kind, sig FROM symbols WHERE path = ? ORDER BY start_byte;",
            (key,),
        ).fetchall()
        if not rows and conn.execute(
            "SELECT 1 FROM files WHERE path = ?;", (key,)
        ).fetchone() is None:
            if path is not None:
                return {
                    "files": {},
                    "freshness_by_file": {},
                    "error": "not_found",
                    "_meta": _meta(conn, STALE, counts),
                }
            continue
        files[key] = [
            {"qualname": qn, "kind": kind, "sig": sig or ""} for qn, kind, sig in rows
        ]
        freshness_by_file[key] = freshness_for_file(conn, key, repo_root)
    freshness = _worst(freshness_by_file.values()) if freshness_by_file else FRESH
    return {
        "files": files,
        "freshness_by_file": freshness_by_file,
        "error": None,
        "_meta": _meta(conn, freshness, counts),
    }


# --- check_refs ---


def check_refs(
    conn: sqlite3.Connection, identifier: str, repo_root: Path | str | None = None
) -> dict:
    """Combine import specs + raw text scan + symbol hits into is_referenced.

    Absence always carries scan_counts (never hallucinate negatives).
    """
    counts = _scan_counts(conn)
    evidence: list[dict] = []
    if identifier:
        rx = re.compile(r"\b" + re.escape(identifier) + r"\b")
        for src_path, dst_spec in conn.execute("SELECT src_path, dst_spec FROM imports;"):
            if dst_spec and rx.search(dst_spec):
                evidence.append({"kind": "import", "path": src_path, "spec": dst_spec})
        for sid, sym_path, qualname in conn.execute(
            "SELECT id, path, qualname FROM symbols;"
        ):
            if identifier == qualname or identifier in qualname.split("."):
                evidence.append(
                    {"kind": "symbol", "id": sid, "path": sym_path, "qualname": qualname}
                )
        for (file_path,) in conn.execute("SELECT path FROM files;"):
            try:
                text = _disk_path(file_path, repo_root).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
            hits = list(rx.finditer(text))
            if hits:
                evidence.append(
                    {
                        "kind": "text",
                        "path": file_path,
                        "matches": len(hits),
                        "lines": sorted(
                            {text.count("\n", 0, m.start()) + 1 for m in hits[:50]}
                        )[:10],
                    }
                )
    freshness = _repo_freshness(conn, repo_root)
    return {
        "is_referenced": bool(evidence),
        "evidence": evidence,
        "scan_counts": counts,
        "_meta": _meta(conn, freshness, counts),
    }
