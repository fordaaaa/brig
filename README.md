# brig

![brig — index once, retrieve exactly](docs/assets/brig-banner.svg)

Your codebase is too big to paste into a prompt. `brig` indexes it once into a single SQLite file, so you (or your agent) can search symbols and fetch exact code slices instead of reading whole files. No embeddings, no graph DB, no telemetry.

- **Status:** v0.1.0 · Python >= 3.11 · `uv run pytest` green on `main` · MIT
- **Store:** one SQLite WAL file per repo at `~/.brig/index/{slug}.db` (+ `.meta` sidecar)

## The 30-second version

![search, fetch the exact span, check the blast radius](docs/assets/agent-loop.svg)

1. **Index it once** — `brig index . --slug myrepo` parses every supported file into symbols (name, signature, byte offsets).
2. **Search, don't read** — `brig search greet` finds the symbol and its id. No guessing, no whole-file reads.
3. **Fetch the exact slice** — `brig symbol 1` returns just that function (~90 tokens, not the whole file). `brig blast greet` tells you what breaks if you edit it.

Measured on this repo: full outline ~9k tokens vs ~33k reading all sources. Every answer carries freshness + `scan_counts`, so "not found" is evidence, not a guess.

## Quickstart

Requires [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest      # must be green
uv run brig index . --slug myrepo
uv run brig search my_function --slug myrepo
uv run brig outline src/app.py --slug myrepo
```

One repo indexed? Drop `--slug`. Several? Add it (`brig list` shows them). Output is JSON with a `_meta` envelope; errors go to stderr, exit 1.

## How it works

![walk, parse, store, fetch](docs/assets/how-it-works.svg)

1. **Walk** — respects `.gitignore` (plus `.git`, `.venv`, `node_modules`, `__pycache__`), drops deleted files, re-indexes only what changed (mtime+size, SHA-256 fallback).
2. **Parse** — each file goes to a `LanguageSpec` by suffix (`src/brig/langs/`). Spans are tree-sitter byte offsets sliced from disk — never guessed.
3. **Store** — upserts into `files` / `symbols` / `imports`, then derives call edges so `callers` / `blast` work.
4. **Retrieve** — `search` → `symbol` → `callers` / `blast` before edits → `refs` before deletes.

Same index, three doors: CLI (`brig search …`), 7 MCP tools over stdio, read-only HTTP (`brig serve`). Flags: `--slug` picks the repo, `--repo` overrides the checkout path, `--root` moves the store, `--depth` caps caller walks at 3.

## Languages

| Language | Extensions |
| --- | --- |
| Python | `.py` |
| JavaScript | `.js` `.jsx` `.mjs` `.cjs` |
| TypeScript | `.ts` `.tsx` `.mts` `.cts` |
| C | `.c` `.h` |
| C++ | `.cpp` `.hpp` `.cc` `.cxx` `.hh` `.h++` |
| C# | `.cs` |
| Java | `.java` |

`.h` belongs to C. Kinds are `function` | `class` | `method` (ctors, structs, enums map into these). CSS/HTML/etc. index as 0-symbol rows for now. Adding a language = one `LanguageSpec` + one registry line, no core changes.

## MCP setup

Same 7 tools over stdio (`index`, `search_symbols`, `get_symbol`, `get_outline`, `callers_callees`, `blast_radius`, `check_refs`). Put this in your client config with the **absolute** checkout path, then restart it:

```json
{"mcpServers": {"brig": {"command": "uv", "args": ["run", "--directory", "/abs/path/to/brig", "python", "-m", "brig.mcp"]}}}
```

Codex (`~/.codex/config.toml`): same thing as `[mcp_servers.brig]` with `command` + `args`. Details: `configs/README.md`.

## HTTP (local)

```sh
brig serve --port 8000
curl "http://127.0.0.1:8000/api/v1/search?slug=myrepo&q=norm_path"
```

Nine `GET` endpoints under `/api/v1` (`live`, `slugs`, `search`, `outline`, `symbol`, `refs`, `callers`, `callees`, `blast`) — same answers as the CLI, loopback by default. Routes: `src/brig/serve.py`.

## Dev

```sh
uv sync && uv run pytest   # green every change
```

TDD, conventional commits (`feat:` `fix:` …), small diffs. `uv.lock` is committed; `*.db` and `.local/` are gitignored. Won't do: embeddings, graph DBs, per-IDE installers, telemetry.

Skills/plans: `skills/`, `plans/` · MIT — see `LICENSE`.
