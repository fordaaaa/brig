# one-command setup: index a repo and wire brig into codex + claude code.
# no new deps. toml is appended by hand (stdlib has no toml writer).

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path


def brig_checkout() -> Path:
    # the checkout holding this file (src/brig/setup.py -> root).
    return Path(__file__).resolve().parent.parent.parent


def codex_config_path(home: str | None = None) -> Path:
    # codex looks at $CODEX_HOME first, then ~/.codex.
    base = home or os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    return Path(base) / "config.toml"


def _toml_str(value: str) -> str:
    # JSON string escaping is compatible with TOML basic strings.
    return json.dumps(value, ensure_ascii=False)


def _server_config(checkout: Path | str) -> dict:
    return {
        "command": "uv",
        "args": ["run", "--directory", str(checkout), "python", "-m", "brig.mcp"],
    }


def _is_current(server: object, want: dict) -> bool:
    return (
        isinstance(server, dict)
        and server.get("command") == want["command"]
        and server.get("args") == want["args"]
    )


def codex_section(checkout: Path | str) -> str:
    want = _server_config(checkout)
    args = ", ".join(_toml_str(a) for a in want["args"])
    return f'[mcp_servers.brig]\ncommand = "uv"\nargs = [{args}]\n'


def wire_codex(config: Path | str, checkout: Path | str, dry_run: bool = False) -> str:
    # add [mcp_servers.brig] to the codex config. returns what happened.
    # never touches existing content, never writes twice.
    cfg = Path(config)
    try:
        text = cfg.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    except OSError as exc:
        raise ValueError(f"cannot read Codex config {cfg}: {exc}") from exc
    want = _server_config(checkout)
    if text:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid Codex TOML in {cfg}: {exc}") from exc
        servers = data.get("mcp_servers")
        if servers is not None and not isinstance(servers, dict):
            raise ValueError(f"invalid mcp_servers table in {cfg}")
        current = servers.get("brig") if servers is not None else None
        if current is not None:
            if _is_current(current, want):
                return "present"
            raise ValueError(f"existing mcp_servers.brig in {cfg} differs; update or remove it manually")
    if dry_run:
        return "dry-run"
    if text and not text.endswith("\n"):
        text += "\n"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text + "\n" + codex_section(checkout), encoding="utf-8")
    return "added"


def wire_claude(dest: Path | str, checkout: Path | str, dry_run: bool = False) -> str:
    # merge mcpServers.brig into a .mcp.json file. returns what happened.
    # keeps every other server, writes nothing twice.
    path = Path(dest)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    except OSError as exc:
        raise ValueError(f"cannot read Claude config {path}: {exc}") from exc
    if text:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object in {path}")
    servers = data.get("mcpServers")
    if servers is None:
        servers = {}
        data["mcpServers"] = servers
    elif not isinstance(servers, dict):
        raise ValueError(f"expected mcpServers to be an object in {path}")
    want = _server_config(checkout)
    current = servers.get("brig")
    if current is not None:
        if _is_current(current, want):
            return "present"
        raise ValueError(f"existing mcpServers.brig in {path} differs; update or remove it manually")
    if dry_run:
        return "dry-run"
    servers["brig"] = want
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return "added"
