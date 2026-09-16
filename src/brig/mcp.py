# the mcp server: 7 tools over stdin/stdout as json-rpc.
# stdlib only.

from __future__ import annotations

import json
import sys
from pathlib import Path

protocol_version = "2024-11-05"
server_name = "brig"
server_version = "0.1.0"

tools = [
    {
        "name": "index",
        "description": "Index a repo dir (incremental).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "root": {"type": "string"},
                "slug": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_symbols",
        "description": "Search symbols by name/sig/doc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "slug": {"type": "string"},
                "root": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_symbol",
        "description": "Symbol + byte-exact source by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "slug": {"type": "string"},
                "root": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "get_outline",
        "description": "Outline of file or whole repo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "slug": {"type": "string"},
                "root": {"type": "string"},
                "repo": {"type": "string"},
            },
        },
    },
    {
        "name": "callers_callees",
        "description": "Callers or callees of symbol, depth<=3.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "direction": {"type": "string", "enum": ["callers", "callees"]},
                "depth": {"type": "integer"},
                "slug": {"type": "string"},
                "root": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["symbol", "direction"],
        },
    },
    {
        "name": "blast_radius",
        "description": "Reverse deps of symbol or file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "slug": {"type": "string"},
                "root": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "check_refs",
        "description": "Is identifier referenced? + evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string"},
                "slug": {"type": "string"},
                "root": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["identifier"],
        },
    },
]

_TOOL_NAMES = {t["name"] for t in tools}


class InvalidParams(Exception):
    # bad arguments from the caller.
    pass


class ToolRuntimeError(Exception):
    # something broke while running the tool.
    pass


def _base(root: str | None) -> Path:
    from brig import db

    return Path(root) if root is not None else db.default_root()


def _store(base: Path) -> Path:
    return base / "index"


def _slugs(base: Path) -> list[str]:
    store = _store(base)
    if not store.is_dir():
        return []
    return sorted(p.stem for p in store.glob("*.db") if p.is_file())


def _resolve_slug(slug: str | None, base: Path) -> str:
    if slug is not None:
        if (_store(base) / f"{slug}.db").exists():
            return slug
        raise ToolRuntimeError(f"unknown slug {slug!r}; index it first.")
    slugs = _slugs(base)
    if len(slugs) == 1:
        return slugs[0]
    if not slugs:
        raise ToolRuntimeError("no indexed repos; run index first.")
    raise ToolRuntimeError(f"multiple repos {slugs}; pass slug.")


def _repo_root(slug: str, base: Path, explicit: str | None) -> Path | None:
    if explicit is not None:
        return Path(explicit)
    try:
        from brig import db

        meta = db.read_meta(slug, root=base)
    except Exception:
        meta = None
    if isinstance(meta, dict) and meta.get("repo_root"):
        return Path(meta["repo_root"])
    return None


def _req_str(args: dict, key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val:
        raise InvalidParams(f"missing/invalid string param: {key}")
    return val


def _opt_str(args: dict, key: str) -> str | None:
    val = args.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise InvalidParams(f"invalid string param: {key}")
    return val or None


def _open(slug: str, base: Path):
    from brig import db

    return db.open_or_create(slug, root=base)


def _safe_extract(path, source):
    # unknown file types become empty (no crash).
    from brig.parse import extract

    res = extract(path, source)
    if res is None:
        return ([], [])
    return res


def _stash_repo_root(slug: str, base: Path, repo: Path) -> None:
    try:
        from brig import db

        meta = db.read_meta(slug, root=base) or {}
        meta["repo_root"] = str(repo.resolve())
        (_store(base) / f"{slug}.meta").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError:
        pass


def _fresh_meta() -> dict:
    return {"freshness": "fresh", "confidence": 1.0}


# --- the 7 tools (each returns plain data + _meta) ---


def _tool_index(args: dict) -> dict:
    from brig import db, query

    path = _req_str(args, "path")
    repo = Path(path)
    if not repo.is_dir():
        raise ToolRuntimeError(f"not a directory: {path}")
    base = _base(_opt_str(args, "root"))
    slug = _opt_str(args, "slug") or repo.name
    try:
        stats = db.index_repo(repo, slug=slug, index_root=base, extract_fn=_safe_extract)
    except Exception as exc:
        raise ToolRuntimeError(f"index failed: {exc}") from exc
    _stash_repo_root(slug, base, repo)
    try:
        conn = db.open_or_create(slug, root=base)
        try:
            query.infer_call_edges(conn, repo_root=repo)
        finally:
            conn.close()
    except Exception:
        pass
    return {
        "indexed": stats["indexed"],
        "skipped": stats["skipped"],
        "removed": stats["removed"],
        "slug": slug,
        "_meta": _fresh_meta(),
    }


def _tool_search_symbols(args: dict) -> dict:
    from brig import query

    if "query" not in args or not isinstance(args["query"], str):
        raise InvalidParams("missing/invalid string param: query")
    base = _base(_opt_str(args, "root"))
    slug = _resolve_slug(_opt_str(args, "slug"), base)
    repo_root = _repo_root(slug, base, _opt_str(args, "repo"))
    conn = _open(slug, base)
    try:
        return query.search_symbols(conn, args["query"], repo_root=repo_root)
    finally:
        conn.close()


def _tool_get_symbol(args: dict) -> dict:
    from brig import query

    sid = args.get("id")
    if isinstance(sid, bool) or not isinstance(sid, int):
        raise InvalidParams("missing/invalid integer param: id")
    base = _base(_opt_str(args, "root"))
    slug = _resolve_slug(_opt_str(args, "slug"), base)
    repo_root = _repo_root(slug, base, _opt_str(args, "repo"))
    conn = _open(slug, base)
    try:
        return query.get_symbol(conn, sid, repo_root=repo_root)
    finally:
        conn.close()


def _tool_get_outline(args: dict) -> dict:
    from brig import query

    path = args.get("path")
    if path is not None and not isinstance(path, str):
        raise InvalidParams("invalid string param: path")
    base = _base(_opt_str(args, "root"))
    slug = _resolve_slug(_opt_str(args, "slug"), base)
    repo_root = _repo_root(slug, base, _opt_str(args, "repo"))
    conn = _open(slug, base)
    try:
        return query.get_outline(conn, path or None, repo_root=repo_root)
    finally:
        conn.close()


def _tool_callers_callees(args: dict) -> dict:
    from brig import query

    symbol = _req_str(args, "symbol")
    direction = args.get("direction")
    if direction not in ("callers", "callees"):
        raise InvalidParams("direction must be callers|callees")
    depth = args.get("depth", 1)
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise InvalidParams("invalid integer param: depth")
    depth = max(0, min(depth, 3))
    base = _base(_opt_str(args, "root"))
    slug = _resolve_slug(_opt_str(args, "slug"), base)
    repo_root = _repo_root(slug, base, _opt_str(args, "repo"))
    conn = _open(slug, base)
    try:
        if direction == "callers":
            return query.callers(conn, symbol, depth=depth, repo_root=repo_root)
        return query.callees(conn, symbol, depth=depth, repo_root=repo_root)
    finally:
        conn.close()


def _tool_blast_radius(args: dict) -> dict:
    from brig import query

    target = _req_str(args, "target")
    base = _base(_opt_str(args, "root"))
    slug = _resolve_slug(_opt_str(args, "slug"), base)
    repo_root = _repo_root(slug, base, _opt_str(args, "repo"))
    conn = _open(slug, base)
    try:
        return query.blast_radius(conn, target, repo_root=repo_root)
    finally:
        conn.close()


def _tool_check_refs(args: dict) -> dict:
    from brig import query

    if "identifier" not in args or not isinstance(args["identifier"], str):
        raise InvalidParams("missing/invalid string param: identifier")
    base = _base(_opt_str(args, "root"))
    slug = _resolve_slug(_opt_str(args, "slug"), base)
    repo_root = _repo_root(slug, base, _opt_str(args, "repo"))
    conn = _open(slug, base)
    try:
        return query.check_refs(conn, args["identifier"], repo_root=repo_root)
    finally:
        conn.close()


_DISPATCH = {
    "index": _tool_index,
    "search_symbols": _tool_search_symbols,
    "get_symbol": _tool_get_symbol,
    "get_outline": _tool_get_outline,
    "callers_callees": _tool_callers_callees,
    "blast_radius": _tool_blast_radius,
    "check_refs": _tool_check_refs,
}


def _err(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def handle_request(req: dict) -> dict | None:
    # handle one json-rpc message. nothing back for notifications.
    if not isinstance(req, dict):
        return _err(None, -32600, "invalid request")
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params", {})
    if not isinstance(method, str):
        return _err(req_id, -32600, "invalid request: missing method")

    if method == "notifications/initialized":
        return None
    if req_id is None:
        return None

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_name, "version": server_version},
            },
        )
    if method == "ping":
        return _ok(req_id, {})
    if method == "tools/list":
        return _ok(req_id, {"tools": tools})
    if method == "tools/call":
        if not isinstance(params, dict):
            return _err(req_id, -32602, "invalid params: expected object")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in _DISPATCH:
            if isinstance(name, str):
                return _ok(
                    req_id,
                    {
                        "content": [{"type": "text", "text": f"unknown tool {name!r}"}],
                        "isError": True,
                    },
                )
            return _err(req_id, -32602, "missing/invalid param: name")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _err(req_id, -32602, "missing/invalid param: arguments")
        try:
            result = _DISPATCH[name](arguments)
        except InvalidParams as exc:
            return _err(req_id, -32602, str(exc))
        except ToolRuntimeError as exc:
            return _ok(req_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:
            return _ok(req_id, {"content": [{"type": "text", "text": f"tool failed: {exc}"}], "isError": True})
        if not isinstance(result, dict):
            return _ok(req_id, {"content": [{"type": "text", "text": "empty result"}], "isError": True})
        if "_meta" not in result:
            result["_meta"] = _fresh_meta()
        return _ok(req_id, {"content": [{"type": "text", "text": json.dumps(result)}]})
    return _err(req_id, -32601, f"method not found: {method}")


def serve() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        try:
            res = handle_request(req)
        except Exception as exc:  # never crash the server
            req_id = req.get("id") if isinstance(req, dict) else None
            res = _err(req_id, -32603, f"internal error: {exc}")
        if res is not None:
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
