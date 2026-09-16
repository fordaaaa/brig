# Phase 3b: MCP stdio server tests — JSON-RPC over handler + subprocess.
# TDD: written before src/brig/mcp.py. Drives handle_request() directly
# (plus one stdio subprocess smoke test); no external SDK deps.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from brig import db
from brig.mcp import tools, handle_request

helpers_py = '''"""Helper utilities."""

def helper(name):
    """Greet by name."""
    return "hi " + name


class Worker:
    """Does work."""

    def run(self, name):
        """Run worker."""
        return helper(name)
'''

main_py = '''import helpers
from helpers import helper


def main():
    """Entry point."""
    return helper("world") + helpers.helper("again")


def entry():
    """Boot."""
    return main()
'''


@pytest.fixture
def setup(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "helpers.py").write_text(helpers_py, encoding="utf-8")
    (repo / "main.py").write_text(main_py, encoding="utf-8")
    home = tmp_path / "brig-home"
    conn = db.open_or_create("repo", root=home)
    db.index_repo(repo, conn=conn)
    from brig import query

    query.infer_call_edges(conn, repo_root=repo)
    conn.close()
    return {"repo": str(repo), "root": str(home), "slug": "repo"}


def _call(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    req: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        req["params"] = params
    res = handle_request(req)
    assert res is not None
    return res


def _tool_text(res: dict) -> dict:
    assert "result" in res, res
    content = res["result"]["content"]
    assert content and content[0]["type"] == "text"
    return json.loads(content[0]["text"])


def test_initialize_handshake():
    res = _call("initialize", {"protocolVersion": "2024-11-05"})
    assert res["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in res["result"]["capabilities"]
    assert res["result"]["serverInfo"]["name"] == "brig"


def test_tools_list_has_exactly_seven(setup):
    res = _call("tools/list")
    tools = res["result"]["tools"]
    assert len(tools) == 7
    names = {t["name"] for t in tools}
    assert names == {
        "index",
        "search_symbols",
        "get_symbol",
        "get_outline",
        "callers_callees",
        "blast_radius",
        "check_refs",
    }
    # hard cap: terse schema payload < 4000 tokens (~4 chars/token).
    assert len(json.dumps(tools)) < 16000
    assert len(tools) == 7


def test_search_round_trip(setup):
    res = _call("tools/call", {"name": "search_symbols", "arguments": {"query": "helper", "root": setup["root"]}})
    assert res["result"].get("isError", False) is False
    data = _tool_text(res)
    assert data["results"][0]["qualname"] == "helper"
    assert "_meta" in data


def test_index_then_get_outline(setup, tmp_path):
    new_repo = tmp_path / "other"
    new_repo.mkdir()
    (new_repo / "b.py").write_text("def bee():\n    return 1\n", encoding="utf-8")
    res = _call("tools/call", {"name": "index", "arguments": {"path": str(new_repo), "root": setup["root"]}})
    data = _tool_text(res)
    assert data["indexed"] == 1
    assert "_meta" in data
    res2 = _call(
        "tools/call",
        {"name": "get_outline", "arguments": {"slug": "other", "root": setup["root"]}},
    )
    data2 = _tool_text(res2)
    assert set(data2["files"]) == {"b.py"}


def test_callers_callees_direction_param(setup):
    res = _call(
        "tools/call",
        {"name": "callers_callees", "arguments": {"symbol": "helper", "direction": "callers", "root": setup["root"]}},
    )
    data = _tool_text(res)
    assert {r["qualname"] for r in data["results"]} >= {"main", "Worker.run"}
    res2 = _call(
        "tools/call",
        {"name": "callers_callees", "arguments": {"symbol": "entry", "direction": "callees", "depth": 2, "root": setup["root"]}},
    )
    by_depth = {r["qualname"]: r["depth"] for r in json.loads(res2["result"]["content"][0]["text"])["results"]}
    assert by_depth == {"main": 1, "helper": 2}


def test_unknown_method_error():
    res = _call("nope/method", {}, req_id=99)
    assert res["error"]["code"] == -32601
    assert res["id"] == 99


def test_malformed_params_error(setup):
    # tools/call without a tool name is malformed params.
    res = _call("tools/call", {"arguments": {}}, req_id=7)
    assert res["error"]["code"] == -32602
    # bad direction value is also malformed params.
    res2 = _call(
        "tools/call",
        {"name": "callers_callees", "arguments": {"symbol": "helper", "direction": "sideways", "root": setup["root"]}},
    )
    assert "error" in res2 or res2["result"].get("isError", False) is True


def test_tool_runtime_error_is_error_result(setup):
    res = _call("tools/call", {"name": "search_symbols", "arguments": {"query": "helper", "slug": "no-such-slug", "root": setup["root"]}})
    assert res["result"]["isError"] is True
    assert isinstance(res["result"]["content"][0]["text"], str)


def test_stdio_subprocess_initialize():
    proc = subprocess.run(
        [sys.executable, "-m", "brig.mcp"],
        input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    first = proc.stdout.strip().splitlines()[0]
    res = json.loads(first)
    assert res["result"]["protocolVersion"] == "2024-11-05"
