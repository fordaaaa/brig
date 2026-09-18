# setup tests — written before src/brig/setup.py.
# covers codex toml wiring, claude .mcp.json wiring, and the cli command.

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from brig import cli, setup


def _repo(tmp_path: Path) -> Path:
    d = tmp_path / "myrepo"
    d.mkdir()
    (d / "app.py").write_text('def greet(name):\n    return "hi " + name\n', encoding="utf-8")
    return d


def test_codex_creates_config(tmp_path: Path):
    cfg = tmp_path / "codex-home" / "config.toml"
    assert setup.wire_codex(cfg, "/abs/brig") == "added"
    text = cfg.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["mcp_servers"]["brig"]["command"] == "uv"
    assert data["mcp_servers"]["brig"]["args"] == [
        "run",
        "--directory",
        "/abs/brig",
        "python",
        "-m",
        "brig.mcp",
    ]


def test_codex_idempotent(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    assert setup.wire_codex(cfg, "/abs/brig") == "added"
    assert setup.wire_codex(cfg, "/abs/brig") == "present"
    text = cfg.read_text(encoding="utf-8")
    assert text.count("[mcp_servers.brig]") == 1


def test_codex_keeps_existing_content(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('model = "x"\n\n[mcp_servers.other]\ncommand = "y"\n', encoding="utf-8")
    assert setup.wire_codex(cfg, "/abs/brig") == "added"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["model"] == "x"
    assert data["mcp_servers"]["other"]["command"] == "y"
    assert data["mcp_servers"]["brig"]["command"] == "uv"


def test_codex_escapes_weird_paths(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    root = '/we"ird\\path'
    assert setup.wire_codex(cfg, root) == "added"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcp_servers"]["brig"]["args"][2] == root


def test_codex_escapes_newline_in_path(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    root = "/weird\npath"
    assert setup.wire_codex(cfg, root) == "added"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcp_servers"]["brig"]["args"][2] == root


def test_codex_ignores_commented_header(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("# [mcp_servers.brig]\n", encoding="utf-8")
    assert setup.wire_codex(cfg, "/abs/brig") == "added"


def test_codex_rejects_stale_or_invalid_config(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    assert setup.wire_codex(cfg, "/old/brig") == "added"
    before = cfg.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        setup.wire_codex(cfg, "/new/brig")
    assert cfg.read_text(encoding="utf-8") == before

    cfg.write_text("not valid = [", encoding="utf-8")
    before = cfg.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Codex TOML"):
        setup.wire_codex(cfg, "/abs/brig")
    assert cfg.read_text(encoding="utf-8") == before


def test_codex_dry_run_changes_nothing(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    assert setup.wire_codex(cfg, "/abs/brig", dry_run=True) == "dry-run"
    assert not cfg.exists()


def test_codex_home_env(tmp_path: Path, monkeypatch):
    home = tmp_path / "chome"
    monkeypatch.setenv("CODEX_HOME", str(home))
    assert setup.codex_config_path() == home / "config.toml"


def test_claude_creates_mcp_json(tmp_path: Path):
    dest = tmp_path / "myrepo" / ".mcp.json"
    assert setup.wire_claude(dest, "/abs/brig") == "added"
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["mcpServers"]["brig"]["command"] == "uv"
    assert data["mcpServers"]["brig"]["args"][2] == "/abs/brig"


def test_claude_merges_and_idempotent(tmp_path: Path):
    dest = tmp_path / ".mcp.json"
    dest.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), encoding="utf-8")
    assert setup.wire_claude(dest, "/abs/brig") == "added"
    assert setup.wire_claude(dest, "/abs/brig") == "present"
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["brig"]["command"] == "uv"


def test_claude_rejects_stale_or_invalid_config(tmp_path: Path):
    dest = tmp_path / ".mcp.json"
    assert setup.wire_claude(dest, "/old/brig") == "added"
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        setup.wire_claude(dest, "/new/brig")
    assert dest.read_text(encoding="utf-8") == before

    for invalid in ("{not json", "[]", '{"mcpServers": []}'):
        dest.write_text(invalid, encoding="utf-8")
        with pytest.raises(ValueError):
            setup.wire_claude(dest, "/abs/brig")
        assert dest.read_text(encoding="utf-8") == invalid


def test_claude_dry_run_changes_nothing(tmp_path: Path):
    dest = tmp_path / ".mcp.json"
    assert setup.wire_claude(dest, "/abs/brig", dry_run=True) == "dry-run"
    assert not dest.exists()


def test_brig_checkout_points_at_repo_root():
    root = setup.brig_checkout()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "brig" / "setup.py").is_file()


def test_cli_setup_end_to_end(tmp_path: Path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    home = tmp_path / "brig-home"
    chome = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(chome))
    code = cli.main(["setup", str(repo), "--root", str(home)])
    out, _ = capsys.readouterr()
    assert code == 0, out
    data = json.loads(out)
    assert data["slug"] == "myrepo"
    assert data["indexed"] == 1
    assert data["codex"] == "added"
    assert data["claude"] == "added"
    assert data["checkout"] == str(setup.brig_checkout())
    assert (chome / "config.toml").is_file()
    assert (repo / ".mcp.json").is_file()


def test_cli_setup_bad_dir(tmp_path: Path, capsys):
    code = cli.main(["setup", str(tmp_path / "nope"), "--no-codex", "--no-claude"])
    assert code == 1


def test_cli_setup_dry_run_changes_nothing(tmp_path: Path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    home = tmp_path / "brig-home"
    chome = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(chome))
    code = cli.main(["setup", str(repo), "--root", str(home), "--dry-run"])
    out, _ = capsys.readouterr()
    assert code == 0, out
    data = json.loads(out)
    assert data["codex"] == "dry-run"
    assert data["claude"] == "dry-run"
    assert data["codex_config"] == str(chome / "config.toml")
    assert data["claude_config"] == str(repo / ".mcp.json")
    assert not (chome / "config.toml").exists()
    assert not (repo / ".mcp.json").exists()
    assert not (home / "index").exists()


def test_cli_setup_dry_run_rejects_invalid_slug(tmp_path: Path, capsys):
    repo = _repo(tmp_path)
    code = cli.main(["setup", str(repo), "--slug", "../bad", "--dry-run"])
    _, err = capsys.readouterr()
    assert code == 1
    assert "invalid slug" in err


def test_cli_setup_preflight_prevents_partial_changes(tmp_path: Path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    home = tmp_path / "brig-home"
    chome = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(chome))
    (repo / ".mcp.json").write_text("{not json", encoding="utf-8")

    code = cli.main(["setup", str(repo), "--root", str(home)])
    _, err = capsys.readouterr()

    assert code == 1
    assert "setup preflight failed" in err
    assert not (chome / "config.toml").exists()
    assert not (home / "index").exists()
