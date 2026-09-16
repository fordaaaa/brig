# HTTP serve tests — read-only JSON API over thread + ephemeral port.
# TDD: written before src/brig/serve.py. Spins up serve.serve() on port 0
# in a daemon thread, drives it with stdlib urllib, shuts it down cleanly.

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from brig import db
from brig.serve import Handler

helpers_py = '''"""Helper utilities."""

def helper(name):
    """Greet by name."""
    return "hi " + name
'''


def _start_server(home: Path) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.brig_root = home
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _get(port: int, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


@pytest.fixture
def live(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "helpers.py").write_text(helpers_py, encoding="utf-8")
    home = tmp_path / "brig-home"
    conn = db.open_or_create("repo", root=home)
    try:
        db.index_repo(repo, conn=conn)
    finally:
        conn.close()
    # Same as `brig index`: record the checkout so queries resolve freshness.
    meta = db.read_meta("repo", root=home) or {}
    meta["repo_root"] = str(repo.resolve())
    (home / "index" / "repo.meta").write_text(json.dumps(meta), encoding="utf-8")
    server, port = _start_server(home)
    yield port
    server.shutdown()
    server.server_close()


def test_live(live: int):
    code, body = _get(live, "/api/v1/live")
    assert code == 200
    assert body == {"status": "ok"}


def test_slugs_lists_index(live: int):
    code, body = _get(live, "/api/v1/slugs")
    assert code == 200
    assert body == {"slugs": ["repo"]}


def test_search_finds_symbol(live: int):
    code, body = _get(live, "/api/v1/search?slug=repo&q=helper")
    assert code == 200
    assert any(r["qualname"] == "helper" for r in body["results"])
    assert body["_meta"]["freshness"] == "fresh"


def test_outline_and_symbol(live: int):
    code, body = _get(live, "/api/v1/outline?slug=repo&path=helpers.py")
    assert code == 200
    assert "helpers.py" in body["files"]

    _, found = _get(live, "/api/v1/search?slug=repo&q=helper")
    symbol_id = next(r["id"] for r in found["results"] if r["qualname"] == "helper")
    code, body = _get(live, f"/api/v1/symbol?slug=repo&id={symbol_id}")
    assert code == 200
    assert "def helper(name):" in body["source"]


def test_blast_names_dependents(live: int):
    code, body = _get(live, "/api/v1/blast?slug=repo&target=" + urllib.parse.quote("helpers.py"))
    assert code == 200
    assert body["target"] == "helpers.py"


def test_missing_param_is_400(live: int):
    code, body = _get(live, "/api/v1/search?slug=repo")
    assert code == 400
    assert "error" in body


def test_unknown_slug_is_404(live: int):
    code, body = _get(live, "/api/v1/search?slug=nope&q=x")
    assert code == 404
    assert "error" in body


def test_unknown_endpoint_is_404(live: int):
    code, body = _get(live, "/api/v1/nonexistent?slug=repo")
    assert code == 404
    assert "error" in body
