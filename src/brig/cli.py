"""CLI mirror for brig. See SPEC.md (Tool surface + CLI mirror).

JSON to stdout (forward-slash paths, ``_meta`` envelope as returned by the
query layer); errors to stderr with exit code 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _add_store_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        default=None,
        help="Brig store root (parent of index/); defaults to ~/.brig.",
    )
    parser.add_argument("--slug", default=None, help="Indexed repo slug.")
    parser.add_argument(
        "--repo",
        default=None,
        help="Repo checkout path override (defaults to the path recorded at index time).",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser."""
    from brig import db

    parser = argparse.ArgumentParser(prog="brig", description="brig code-graph index CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Incrementally index a repo.")
    p_index.add_argument("path", help="Repo directory to index.")
    p_index.add_argument("--root", default=None, help="Brig store root; defaults to ~/.brig.")
    p_index.add_argument("--slug", default=None, help="Slug (defaults to the repo dir name).")

    p_search = sub.add_parser("search", help="Search symbols.")
    p_search.add_argument("query", help="Search query.")
    _add_store_args(p_search)

    p_outline = sub.add_parser("outline", help="Repo or single-file outline.")
    p_outline.add_argument("path", nargs="?", default=None, help="File path (default: whole repo).")
    _add_store_args(p_outline)

    p_symbol = sub.add_parser("symbol", help="Get a symbol with its source slice.")
    p_symbol.add_argument("id", type=int, help="Symbol id.")
    _add_store_args(p_symbol)

    p_refs = sub.add_parser("refs", help="Check references of an identifier.")
    p_refs.add_argument("identifier", help="Identifier to check.")
    _add_store_args(p_refs)

    p_callers = sub.add_parser("callers", help="Transitive callers of a qualname.")
    p_callers.add_argument("qualname", help="Caller target qualname.")
    p_callers.add_argument("--depth", type=int, default=1, help="Walk depth (capped at 3).")
    _add_store_args(p_callers)

    p_callees = sub.add_parser("callees", help="Transitive callees of a qualname.")
    p_callees.add_argument("qualname", help="Callee source qualname.")
    p_callees.add_argument("--depth", type=int, default=1, help="Walk depth (capped at 3).")
    _add_store_args(p_callees)

    p_blast = sub.add_parser("blast", help="Blast radius of a symbol or file.")
    p_blast.add_argument("target", help="Symbol qualname or indexed file path.")
    _add_store_args(p_blast)

    p_list = sub.add_parser("list", help="List indexed slugs.")
    p_list.add_argument("--root", default=None, help="Brig store root; defaults to ~/.brig.")

    p_serve = sub.add_parser("serve", help="Run the read-only HTTP API.")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind address (default loopback).")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port.")
    p_serve.add_argument("--root", default=None, help="Brig store root; defaults to ~/.brig.")

    # Touch db import so missing dep fails fast at parser build.
    _ = db.default_root
    return parser


def _store_base(root_arg: str | None) -> Path:
    from brig import db

    return Path(root_arg) if root_arg is not None else db.default_root()


def _index_dir(base: Path) -> Path:
    return base / "index"


def _available_slugs(base: Path) -> list[str]:
    from brig import db

    store = _index_dir(base)
    if not store.is_dir():
        return []
    slugs = []
    for p in store.glob("*.db"):
        if p.is_file() and p.name.endswith(".db"):
            slug = p.name[: -len(".db")]
            if db.is_valid_slug(slug):
                slugs.append(slug)
    return sorted(slugs)


def _fail(message: str) -> int:
    print(f"brig: error: {message}", file=sys.stderr)
    return 1


def _resolve_slug(slug_arg: str | None, base: Path) -> tuple[str | None, int]:
    """Return (slug, 0) or (None, 1) after printing the error."""
    if slug_arg is not None:
        if (_index_dir(base) / f"{slug_arg}.db").exists():
            return slug_arg, 0
        return None, _fail(f"unknown slug {slug_arg!r}; see `brig list`.")
    slugs = _available_slugs(base)
    if len(slugs) == 1:
        return slugs[0], 0
    if not slugs:
        return None, _fail("no indexed repos found; run `brig index <path>` first.")
    return None, _fail(f"multiple indexed repos {slugs}; require --slug.")


def _repo_root_for(slug: str, base: Path, explicit: str | None) -> Path | None:
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


def _safe_extract(path, source):
    """Wrapper tolerating unsupported languages (None -> empty)."""
    from brig.parse import extract

    res = extract(path, source)
    if res is None:
        return ([], [])
    return res


def _emit(payload: dict) -> int:
    print(json.dumps(payload, indent=2))
    return 0


def _stash_repo_root(slug: str, base: Path, repo: Path) -> None:
    """Record the absolute repo checkout in the .meta sidecar (additive)."""
    from brig import db

    try:
        meta = db.read_meta(slug, root=base) or {}
        meta["repo_root"] = str(repo.resolve())
        (base / "index" / f"{slug}.meta").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError:
        pass


def _cmd_index(args: argparse.Namespace) -> int:
    from brig import db, query

    repo = Path(args.path)
    if not repo.is_dir():
        return _fail(f"not a directory: {args.path}")
    base = _store_base(args.root)
    slug = args.slug or db.default_slug_for_repo(repo)
    try:
        stats = db.index_repo(repo, slug=slug, index_root=base, extract_fn=_safe_extract)
    except Exception as exc:
        return _fail(f"index failed: {exc}")
    _stash_repo_root(slug, base, repo)
    # Best-effort INFERRED call edges so callers/callees/blast work from CLI.
    try:
        conn = db.open_or_create(slug, root=base)
        try:
            query.infer_call_edges(conn, repo_root=repo)
        finally:
            conn.close()
    except Exception:
        pass
    return _emit({"indexed": stats["indexed"], "skipped": stats["skipped"], "removed": stats["removed"], "slug": slug})


def _open_existing(slug: str, base: Path):
    from brig import db

    conn = db.open_or_create(slug, root=base)
    return conn


def _cmd_search(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.search_symbols(conn, args.query, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_outline(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.get_outline(conn, args.path, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_symbol(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.get_symbol(conn, args.id, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_refs(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.check_refs(conn, args.identifier, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_callers(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.callers(conn, args.qualname, depth=args.depth, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_callees(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.callees(conn, args.qualname, depth=args.depth, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_blast(args: argparse.Namespace) -> int:
    from brig import query

    base = _store_base(args.root)
    slug, code = _resolve_slug(args.slug, base)
    if slug is None:
        return code
    repo_root = _repo_root_for(slug, base, args.repo)
    conn = _open_existing(slug, base)
    try:
        return _emit(query.blast_radius(conn, args.target, repo_root=repo_root))
    finally:
        conn.close()


def _cmd_list(args: argparse.Namespace) -> int:
    from brig import db

    base = _store_base(args.root)
    slugs = _available_slugs(base)
    details: dict[str, dict] = {}
    for slug in slugs:
        try:
            meta = db.read_meta(slug, root=base)
        except Exception:
            meta = None
        details[slug] = dict(meta) if isinstance(meta, dict) else {}
    return _emit({"slugs": slugs, "repos": details})


def _cmd_serve(args: argparse.Namespace) -> int:
    from brig import serve as serve_mod

    serve_mod.serve(host=args.host, port=args.port, root=args.root)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "index": _cmd_index,
        "search": _cmd_search,
        "outline": _cmd_outline,
        "symbol": _cmd_symbol,
        "refs": _cmd_refs,
        "callers": _cmd_callers,
        "callees": _cmd_callees,
        "blast": _cmd_blast,
        "list": _cmd_list,
        "serve": _cmd_serve,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        return _fail(f"unknown command {args.command!r}.")
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
