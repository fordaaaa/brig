"""Regression tests for plans/fix-dot-path-slug.md.

`brig index .` must default to the resolved directory name, not an empty slug.
TDD: written before the fix in src/brig/cli.py + src/brig/db.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from brig import cli, db


def _touch(store: Path, name: str) -> None:
    store.mkdir(parents=True, exist_ok=True)
    (store / name).write_bytes(b"junk")


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


def test_available_slugs_ignores_legacy_dotfiles(tmp_path: Path):
    store = tmp_path / "index"
    _touch(store, ".db")  # legacy slug ""
    _touch(store, ".db.db")  # legacy slug ".db"
    _touch(store, "myproj.db")

    assert cli._available_slugs(tmp_path) == ["myproj"]


def test_open_or_create_rejects_dot_slugs(tmp_path: Path):
    import pytest

    for bad in ("", ".db", ".", ".."):
        with pytest.raises(ValueError):
            db.open_or_create(bad, root=tmp_path)


def test_search_ignores_legacy_dotfiles(tmp_path: Path, monkeypatch, capsys):
    repo = tmp_path / "myproj"
    repo.mkdir()
    (repo / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    home = tmp_path / "brig-home"
    monkeypatch.chdir(repo)

    _run_json(["index", ".", "--root", str(home)], capsys)
    _touch(home / "index", ".db")
    _touch(home / "index", ".db.db")
    _, data, _ = _run_json(["search", "hello", "--root", str(home)], capsys)

    assert [r["qualname"] for r in data["results"]][0] == "hello"
