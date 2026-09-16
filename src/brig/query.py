# search, outline, refs, callers, blast. no cli/mcp stuff here.
# every function takes an open db connection and returns plain data
# with a _meta envelope (freshness, confidence, scan counts).

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

fresh = "fresh"
edited = "edited_uncommitted"
stale = "stale_index"

max_depth = 3

_CONFIDENCE = {fresh: 1.0, edited: 0.5, stale: 0.0}
_SEVERITY = {fresh: 0, edited: 1, stale: 2}

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
    # how fresh is one file. fresh = sha matches disk;
    # edited = changed but not reindexed; stale = gone or unknown.
    row = conn.execute(
        "SELECT sha256, mtime FROM files WHERE path = ?;", (path,)
    ).fetchone()
    disk = _disk_path(path, repo_root)
    try:
        st = disk.stat()
    except OSError:
        return stale
    if row is None:
        return stale
    stored_sha, stored_mtime = row
    try:
        data = disk.read_bytes()
    except OSError:
        return stale
    if hashlib.sha256(data).hexdigest() == stored_sha:
        return fresh
    if st.st_mtime >= stored_mtime:
        return edited
    return stale


def _scan_counts(conn: sqlite3.Connection, extra: dict | None = None) -> dict:
    counts = {
        "files_scanned": conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0],
        "symbols_scanned": conn.execute("SELECT COUNT(*) FROM symbols;").fetchone()[0],
    }
    if extra:
        counts.update(extra)
    return counts


def _worst(freshnesses) -> str:
    worst = fresh
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
        return fresh
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
    # substring search. exact name first, then name contains,
    # then sig/doc contains. ties go to the best-connected symbol.
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
    # full symbol row + the exact source slice from disk.
    counts = _scan_counts(conn)
    row = conn.execute(
        f"SELECT {_SYMBOL_COLS} FROM symbols WHERE id = ?;", (symbol_id,)
    ).fetchone()
    if row is None:
        return {
            "symbol": None,
            "source": None,
            "error": "not_found",
            "_meta": _meta(conn, stale, counts),
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
            "_meta": _meta(conn, stale, counts),
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
    # outline of one file or the whole repo. names only, no bodies.
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
                    "_meta": _meta(conn, stale, counts),
                }
            continue
        files[key] = [
            {"qualname": qn, "kind": kind, "sig": sig or ""} for qn, kind, sig in rows
        ]
        freshness_by_file[key] = freshness_for_file(conn, key, repo_root)
    freshness = _worst(freshness_by_file.values()) if freshness_by_file else fresh
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
    # is this name used anywhere? checks imports, symbols, raw text.
    # no hits still returns scan counts, so 'unused' is proven.
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


# --- call edges (EXTRACTED vs INFERRED) ---


def add_edge(
    conn: sqlite3.Connection,
    src_id: int,
    dst_id: int,
    kind: str = "calls",
    confidence: str = "INFERRED",
) -> int:
    # small helper to add one edge. db.py has none.
    cur = conn.execute(
        "INSERT INTO edges (src_id, dst_id, kind, confidence) VALUES (?, ?, ?, ?);",
        (src_id, dst_id, kind, confidence),
    )
    conn.commit()
    return cur.lastrowid


def infer_call_edges(
    conn: sqlite3.Connection, repo_root: Path | str | None = None
) -> dict:
    # second pass: if a symbol body mentions another symbol's short name,
    # link them as a call. rebuilds guessed edges from scratch;
    # extracted ones are left alone.
    counts = _scan_counts(conn)
    syms = conn.execute(
        "SELECT id, path, qualname, start_byte, end_byte FROM symbols;"
    ).fetchall()
    by_short: dict[str, list[tuple[int, str]]] = {}
    for sid, sym_path, qualname, _sb, _eb in syms:
        by_short.setdefault(qualname.rsplit(".", 1)[-1], []).append((sid, sym_path))
    conn.execute("DELETE FROM edges WHERE kind = 'calls' AND confidence = 'INFERRED';")
    spans = [(sid, sym_path, sb, eb) for sid, sym_path, _qn, sb, eb in syms]
    cache: dict[str, bytes | None] = {}
    seen: set[tuple[int, int]] = set()
    added = 0
    for sid, sym_path, _qualname, sb, eb in syms:
        if sym_path not in cache:
            try:
                cache[sym_path] = _disk_path(sym_path, repo_root).read_bytes()
            except OSError:
                cache[sym_path] = None
        data = cache[sym_path]
        if not data or not (0 <= sb <= eb <= len(data)):
            continue
        # only the symbol's own lines count, not nested symbols inside it.
        # (else a method's calls would also land on its class).
        inner = sorted(
            (osb, oeb)
            for oid, opath, osb, oeb in spans
            if oid != sid
            and opath == sym_path
            and osb >= sb
            and oeb <= eb
            and (osb, oeb) != (sb, eb)
        )
        parts: list[bytes] = []
        cursor = sb
        for osb, oeb in inner:
            if osb > cursor:
                parts.append(data[cursor:osb])
            cursor = max(cursor, oeb)
        parts.append(data[cursor:eb])
        own = b"\n".join(parts).decode("utf-8", errors="replace")
        for ident in set(_IDENT_RE.findall(own)):
            for did, _dpath in by_short.get(ident, []):
                if did == sid or (sid, did) in seen:
                    continue
                seen.add((sid, did))
                conn.execute(
                    "INSERT INTO edges (src_id, dst_id, kind, confidence)"
                    " VALUES (?, ?, 'calls', 'INFERRED');",
                    (sid, did),
                )
                added += 1
    conn.commit()
    return {
        "edges_added": added,
        "_meta": _meta(conn, _repo_freshness(conn, repo_root), counts),
    }


def _walk_calls(
    conn: sqlite3.Connection,
    qualname: str,
    depth: int,
    direction: str,
    repo_root: Path | str | None,
) -> dict:
    counts = _scan_counts(
        conn, {"edges_scanned": conn.execute("SELECT COUNT(*) FROM edges;").fetchone()[0]}
    )
    depth = max(0, min(depth, max_depth))
    start_ids = [
        r[0]
        for r in conn.execute("SELECT id FROM symbols WHERE qualname = ?;", (qualname,))
    ]
    if not start_ids or depth == 0:
        return {"results": [], "_meta": _meta(conn, _repo_freshness(conn, repo_root), counts)}
    info = {
        r[0]: {"qualname": r[1], "path": r[2], "kind": r[3]}
        for r in conn.execute("SELECT id, qualname, path, kind FROM symbols;")
    }
    visited = set(start_ids)
    frontier = list(start_ids)
    results: list[dict] = []
    for d in range(1, depth + 1):
        nxt: list[int] = []
        for cur in frontier:
            if direction == "callers":
                rows = conn.execute(
                    "SELECT src_id, confidence FROM edges"
                    " WHERE dst_id = ? AND kind = 'calls';",
                    (cur,),
                ).fetchall()
                neighbours = [(src, conf) for src, conf in rows]
            else:
                rows = conn.execute(
                    "SELECT dst_id, confidence FROM edges"
                    " WHERE src_id = ? AND kind = 'calls';",
                    (cur,),
                ).fetchall()
                neighbours = [(dst, conf) for dst, conf in rows]
            for nid, conf in neighbours:
                if nid in visited or nid not in info:
                    continue
                visited.add(nid)
                nxt.append(nid)
                results.append({**info[nid], "depth": d, "confidence": conf})
        if not nxt:
            break
        frontier = nxt
    results.sort(key=lambda r: (r["depth"], r["qualname"]))
    return {
        "results": results,
        "_meta": _meta(conn, _repo_freshness(conn, repo_root), counts),
    }


def callers(
    conn: sqlite3.Connection,
    qualname: str,
    depth: int = 1,
    repo_root: Path | str | None = None,
) -> dict:
    # walk 'calls' edges backwards. safe on cycles, max depth 3.
    return _walk_calls(conn, qualname, depth, "callers", repo_root)


def callees(
    conn: sqlite3.Connection,
    qualname: str,
    depth: int = 1,
    repo_root: Path | str | None = None,
) -> dict:
    # walk 'calls' edges forwards. safe on cycles, max depth 3.
    return _walk_calls(conn, qualname, depth, "callees", repo_root)


# --- blast_radius ---


def _spec_hits_file(spec: str, path: str) -> bool:
    # does this import string point at this file? best guess.
    cand = _REL_PREFIX_RE.sub("", spec.strip()).rstrip("/")
    if not cand:
        return False
    stem = Path(path).stem
    dotted = Path(path).with_suffix("").as_posix().replace("/", ".")
    return cand == stem or cand == dotted or cand.endswith("." + stem)


def blast_radius(
    conn: sqlite3.Connection, target: str, repo_root: Path | str | None = None
) -> dict:
    # what would this break? reverse calls + reverse imports.
    # confirmed = real calls and real imports;
    # potential = guessed calls.
    counts = _scan_counts(
        conn, {"edges_scanned": conn.execute("SELECT COUNT(*) FROM edges;").fetchone()[0]}
    )
    files = {r[0] for r in conn.execute("SELECT path FROM files;")}
    syms = conn.execute("SELECT id, path, qualname FROM symbols;").fetchall()
    if target in files:
        kind, seed_ids, owner_paths = "file", [s[0] for s in syms if s[1] == target], [target]
    else:
        seed = [(s[0], s[1]) for s in syms if s[2] == target]
        if not seed:
            return {
                "target": target,
                "kind": "unknown",
                "confirmed": [],
                "potential": [],
                "_meta": _meta(conn, _repo_freshness(conn, repo_root), counts),
            }
        kind, seed_ids = "symbol", [s[0] for s in seed]
        owner_paths = sorted({s[1] for s in seed})
    info = {
        r[0]: {"qualname": r[1], "path": r[2], "kind": r[3]}
        for r in conn.execute("SELECT id, qualname, path, kind FROM symbols;")
    }
    confirmed: list[dict] = []
    potential: list[dict] = []
    seen_callers: set[int] = set()
    for sid in seed_ids:
        for src_id, conf in conn.execute(
            "SELECT src_id, confidence FROM edges WHERE dst_id = ? AND kind = 'calls';",
            (sid,),
        ):
            if src_id in seen_callers or src_id not in info:
                continue
            seen_callers.add(src_id)
            entry = {**info[src_id], "confidence": conf, "via": target}
            (confirmed if conf == "EXTRACTED" else potential).append(entry)
    for src_path, dst_spec in conn.execute("SELECT src_path, dst_spec FROM imports;"):
        if any(_spec_hits_file(dst_spec or "", owner) for owner in owner_paths):
            if not any(
                e["kind"] == "import" and e["path"] == src_path and e["spec"] == dst_spec
                for e in confirmed
            ):
                confirmed.append({"kind": "import", "path": src_path, "spec": dst_spec})
    confirmed.sort(key=lambda e: (e["kind"], e.get("qualname", ""), e["path"]))
    potential.sort(key=lambda e: (e["qualname"], e["path"]))
    freshness = _worst(
        [freshness_for_file(conn, p, repo_root) for p in owner_paths]
        + [_repo_freshness(conn, repo_root)]
    )
    return {
        "target": target,
        "kind": kind,
        "confirmed": confirmed,
        "potential": potential,
        "_meta": _meta(conn, freshness, counts),
    }
