"""Phase 3a: CLI mirror tests — argparse JSON surface over the query layer.

TDD: written before src/brig/cli.py. Exercises each subcommand via
``cli.main(argv)`` with ``--root`` pointed at a tmp store, asserting stdout
parses as JSON with the expected keys.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from brig import cli

HELPERS_PY = '''"""Helper utilities."""

def helper(name):
    """Greet by name."""
    return "hi " + name


class Worker:
    """Does work."""

    def run(self, name):
        """Run worker."""
        return helper(name)
'''

MAIN_PY = '''import helpers
from helpers import helper


def main():
    """Entry point."""
    return helper("world") + helpers.helper("again")


def entry():
    """Boot."""
    return main()
'''


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    (d / "helpers.py").write_text(HELPERS_PY, encoding="utf-8")
    (d / "main.py").write_text(MAIN_PY, encoding="utf-8")
    return d


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "brig-home"


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def _run_json(argv: list[str], capsys) -> tuple[int, dict, str]:
    code, out, err = _run(argv, capsys)
    assert code == 0, f"exit {code}: {err}"
    return code, json.loads(out), err


@pytest.fixture
def indexed(repo: Path, home: Path, capsys) -> tuple[str, str]:
    code, out, err = _run(["index", str(repo), "--root", str(home)], capsys)
    assert code == 0, err
    return str(repo), str(home)


def test_index_prints_stats(repo: Path, home: Path, capsys):
    code, data, _ = _run_json(["index", str(repo), "--root", str(home)], capsys)
    assert code == 0
    assert data["indexed"] == 2
    assert data["skipped"] == 0
    assert data["removed"] == 0


def test_search_returns_meta(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["search", "helper", "--root", home], capsys)
    assert [r["qualname"] for r in data["results"]][0] == "helper"
    assert data["_meta"]["freshness"] == "fresh"


def test_outline_repo_wide(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["outline", "--root", home], capsys)
    assert set(data["files"]) == {"helpers.py", "main.py"}
    assert data["error"] is None
    assert "_meta" in data


def test_outline_single_file(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["outline", "helpers.py", "--root", home], capsys)
    assert set(data["files"]) == {"helpers.py"}
    assert len(data["files"]["helpers.py"]) == 3


def test_symbol_source_slice(indexed, capsys):
    _, home = indexed
    _, sdata, _ = _run_json(["search", "helper", "--root", home], capsys)
    sid = next(r["id"] for r in sdata["results"] if r["qualname"] == "helper")
    _, data, _ = _run_json(["symbol", str(sid), "--root", home], capsys)
    assert data["symbol"]["qualname"] == "helper"
    assert data["source"].startswith("def helper(")
    assert data["error"] is None


def test_refs(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["refs", "helper", "--root", home], capsys)
    assert data["is_referenced"] is True
    assert data["evidence"]
    assert "_meta" in data


def test_callers(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["callers", "helper", "--root", home], capsys)
    names = {r["qualname"] for r in data["results"]}
    assert {"main", "Worker.run"} <= names
    assert "_meta" in data


def test_callees(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["callees", "entry", "--depth", "2", "--root", home], capsys)
    by_depth = {r["qualname"]: r["depth"] for r in data["results"]}
    assert by_depth == {"main": 1, "helper": 2}


def test_blast(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["blast", "helper", "--root", home], capsys)
    assert data["target"] == "helper"
    assert {e["qualname"] for e in data["potential"]} == {"main", "Worker.run"}
    assert any(e["kind"] == "import" for e in data["confirmed"])


def test_list_slugs(indexed, capsys):
    _, home = indexed
    _, data, _ = _run_json(["list", "--root", home], capsys)
    assert "repo" in data["slugs"]


def test_slug_required_when_multiple(repo: Path, home: Path, capsys):
    other = repo.parent / "other"
    other.mkdir()
    (other / "b.py").write_text("x = 1\n", encoding="utf-8")
    assert cli.main(["index", str(repo), "--root", str(home)]) == 0
    capsys.readouterr()
    assert cli.main(["index", str(other), "--root", str(home)]) == 0
    capsys.readouterr()
    code, out, err = _run(["search", "helper", "--root", str(home)], capsys)
    assert code == 1
    assert "--slug" in err
