"""Regression tests for plans/fix-dot-path-slug.md.

`brig index .` must default to the resolved directory name, not an empty slug.
TDD: written before the fix in src/brig/cli.py + src/brig/db.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from brig import cli


def _run_json(argv: list[str], capsys) -> tuple[int, dict, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    assert code == 0, f"exit {code}: {err}"
    return code, json.loads(out), err


def test_index_dot_path_uses_dir_name(tmp_path: Path, monkeypatch, capsys):
    repo = tmp_path / "myproj"
    repo.mkdir()
    (repo / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    home = tmp_path / "brig-home"
    monkeypatch.chdir(repo)

    _, data, _ = _run_json(["index", ".", "--root", str(home)], capsys)

    assert data["slug"] == "myproj"
    assert (home / "index" / "myproj.db").exists()
    assert not (home / "index" / ".db").exists()


def test_search_after_dot_index_needs_no_slug(tmp_path: Path, monkeypatch, capsys):
    repo = tmp_path / "myproj"
    repo.mkdir()
    (repo / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    home = tmp_path / "brig-home"
    monkeypatch.chdir(repo)

    _run_json(["index", ".", "--root", str(home)], capsys)
    _, data, _ = _run_json(["search", "hello", "--root", str(home)], capsys)

    assert data["_meta"]["scan_counts"]["symbols_scanned"] > 0
    assert [r["qualname"] for r in data["results"]][0] == "hello"


def test_list_shows_real_slug_after_dot_index(tmp_path: Path, monkeypatch, capsys):
    repo = tmp_path / "myproj"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    home = tmp_path / "brig-home"
    monkeypatch.chdir(repo)

    _run_json(["index", ".", "--root", str(home)], capsys)
    _, data, _ = _run_json(["list", "--root", str(home)], capsys)

    assert data["slugs"] == ["myproj"]
