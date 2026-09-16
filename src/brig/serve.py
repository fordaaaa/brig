# read-only web api over the index. same questions as cli/mcp, no new tools.
# each request opens its own db connection and returns the answer as-is.
# Endpoints (all GET, all JSON):
# /api/v1/live                        -> {"status": "ok"}
# /api/v1/slugs                       -> {"slugs": [...]}
# /api/v1/search?slug=&q=
# /api/v1/outline?slug=[&path=]
# /api/v1/symbol?slug=&id=
# /api/v1/refs?slug=&ident=
# /api/v1/callers?slug=&qualname=[&depth=]
# /api/v1/callees?slug=&qualname=[&depth=]
# /api/v1/blast?slug=&target=
# /                                 tiny human index page
# Errors are {"error": msg}: 400 = bad param, 404 = unknown slug.
# loopback only unless you pass --host behind a trusted proxy.

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from brig import db


def _store_base(root: str | None) -> Path:
    return Path(root).expanduser() if root else Path.home() / ".brig"


def _open(slug: str, base: Path):
    # open the slug's db, or raise saying it's unknown.
    if not slug or not db.is_valid_slug(slug):
        raise LookupError(f"unknown slug {slug!r}; see /api/v1/slugs.")
    if not (base / "index" / f"{slug}.db").exists():
        raise LookupError(f"unknown slug {slug!r}; see /api/v1/slugs.")
    conn = db.open_or_create(slug, root=base)
    repo_root = None
    try:
        meta = db.read_meta(slug, root=base) or {}
        if meta.get("repo_root"):
            repo_root = Path(meta["repo_root"])
    except OSError:
        pass
    return conn, repo_root


def _int(value: str | None, default: int) -> int:
    try:
        return max(1, min(3, int(value))) if value is not None else default
    except (TypeError, ValueError):
        return default


def _route(path: str, args: dict[str, list[str]], base: Path) -> tuple[int, dict]:
    from brig import query

    if path == "/api/v1/live":
        return 200, {"status": "ok"}
    if path == "/api/v1/slugs":
        slugs = sorted(
            p.name[: -len(".db")]
            for p in (base / "index").glob("*.db")
            if p.is_file() and db.is_valid_slug(p.name[: -len(".db")])
        )
        return 200, {"slugs": slugs}

    def need(name: str) -> str:
        value = (args.get(name) or [""])[0].strip()
        if not value:
            raise ValueError(f"missing required query param: {name}")
        return value

    slug = (args.get("slug") or [""])[0].strip()
    repo = (args.get("repo") or [None])[0]
    try:
        conn, recorded = _open(slug, base)
    except LookupError as exc:
        return 404, {"error": str(exc)}
    repo_root = Path(repo).expanduser() if repo else recorded
    try:
        if path == "/api/v1/search":
            return 200, query.search_symbols(conn, need("q"), repo_root=repo_root)
        if path == "/api/v1/outline":
            return 200, query.get_outline(conn, (args.get("path") or [None])[0], repo_root=repo_root)
        if path == "/api/v1/symbol":
            return 200, query.get_symbol(conn, _strict_id(need("id")), repo_root=repo_root)
        if path == "/api/v1/refs":
            return 200, query.check_refs(conn, need("ident"), repo_root=repo_root)
        if path == "/api/v1/callers":
            return 200, query.callers(conn, need("qualname"), _int((args.get("depth") or [None])[0], 1), repo_root=repo_root)
        if path == "/api/v1/callees":
            return 200, query.callees(conn, need("qualname"), _int((args.get("depth") or [None])[0], 1), repo_root=repo_root)
        if path == "/api/v1/blast":
            return 200, query.blast_radius(conn, need("target"), repo_root=repo_root)
    except ValueError as exc:
        return 400, {"error": str(exc)}
    finally:
        conn.close()
    return 404, {"error": f"unknown endpoint {path}"}


def _strict_id(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"bad id {raw!r}; want an integer.")
    if value < 1:
        raise ValueError(f"bad id {raw!r}; want a positive integer.")
    return value


_INDEX_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>brig</title></head>
<body><h1>brig code-graph index</h1>
<p>Read-only JSON API. Try <a href="/api/v1/live">/api/v1/live</a>,
<a href="/api/v1/slugs">/api/v1/slugs</a>, then
<code>/api/v1/search?slug=&lt;slug&gt;&amp;q=&lt;query&gt;</code>.</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "brig/serve"

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            raw = _INDEX_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        parsed = urlparse(self.path)
        try:
            code, payload = _route(parsed.path, parse_qs(parsed.query), self.server.brig_root)
        except ValueError as exc:
            code, payload = 400, {"error": str(exc)}
        self._send(code, payload)

    def log_message(self, *args) -> None:
        pass


def serve(host: str = "127.0.0.1", port: int = 8000, root: str | None = None) -> None:
    # serve forever. port 0 means 'pick one' (tests use that).
    server = ThreadingHTTPServer((host, port), Handler)
    server.brig_root = _store_base(root)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
