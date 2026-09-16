# brig

Deterministic code-graph index for one repo. tree-sitter parses your code into symbols stored in a single SQLite file — queryable through a CLI, 7 MCP tools, and a read-only HTTP API.

Agents waste tokens reading whole files. Index once, retrieve exact spans: symbol search, outlines, refs, caller/callee walks — every response carries freshness and scan counts in a `_meta` envelope instead of guessed negatives. No embeddings, no graph DB, no telemetry.

## Features

- **Index once, retrieve exactly** — tree-sitter AST → symbols with byte offsets → fetch exact source spans, not whole files.
- **Graph without a graph DB** — import/call edges derived from symbols on read, tagged `EXTRACTED` vs `INFERRED`.
- **7 MCP tools, hard cap** — `index`, `search_symbols`, `get_symbol`, `get_outline`, `callers_callees`, `blast_radius`, `check_refs`.
- **CLI mirror** — every tool available as `brig <subcommand>` with JSON output.
- **Read-only HTTP API** — same queries over `GET` as JSON (`brig serve`).
- **Incremental** — mtime+size fast-path with SHA-256 fallback; only changed files re-index.
- **Honest negatives** — absence claims always carry `scan_counts`, never hallucinated.

## Supported languages

| Language | Extensions | Symbols extracted | Imports |
| --- | --- | --- | --- |
| Python | `.py` | functions, classes, methods + docstrings | `import` / `from` |
| JavaScript | `.js` `.jsx` `.mjs` `.cjs` | functions, classes, methods + leading comments | `import` / `require` / dynamic `import()` |
| TypeScript | `.ts` `.tsx` `.mts` `.cts` | same as JS (TSX fallback) | same as JS |
| C | `.c` `.h` | functions, structs/enums (as classes) | `#include` |
| C++ | `.cpp` `.hpp` `.cc` `.cxx` `.hh` `.h++` | functions, classes, methods, ctors, templates, namespaces | `#include` |
| C# | `.cs` | classes, interfaces, methods, ctors, namespaces | `using` |
| Java | `.java` | classes, methods, ctors (package-qualified) | `package` + `import` |

Notes: `.h` is owned by C. Symbol kinds are `function` | `class` | `method` (constructors, structs, enums, interfaces map into these). Sigs cap at 200 chars, docs at 500. Other files (CSS, HTML, Markdown, …) are skipped at index time so scan counts stay honest.

## Quickstart

Requires Python >= 3.11 and [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest      # must be green
uv run brig --help # CLI smoke test

uv run brig index . --slug myrepo
uv run brig search my_function --slug myrepo
uv run brig outline src/app.py --slug myrepo
```

Storage is one SQLite WAL file per repo at `~/.brig/index/{slug}.db` (plus a `.meta` sidecar). When a single repo is indexed the `--slug` flag can be omitted.

## CLI reference

```sh
brig index <path> [--slug <name>] [--root <store>]
brig search <query> [--slug] [--repo] [--root]
brig outline [path] [--slug] [--repo] [--root]
brig symbol <id> [--slug] [--repo] [--root]
brig refs <identifier> [--slug] [--repo] [--root]
brig callers <qualname> [--depth 1-3] [--slug] [--repo] [--root]
brig callees <qualname> [--depth 1-3] [--slug] [--repo] [--root]
brig blast <qualname|path> [--slug] [--repo] [--root]
brig list [--root]
brig serve [--host 127.0.0.1] [--port 8000] [--root <store>]
```

- `--slug` picks the repo when several are indexed.
- `--repo` overrides the checkout path (defaults to the path recorded at index time).
- `--root` moves the store (defaults to `~/.brig`).
- `--depth` caps caller/callee walks at 3.
- Output is JSON on stdout (forward-slash paths, `_meta` envelope included); errors go to stderr with exit code 1.

## MCP setup

`brig` serves its 7 tools over stdio (JSON-RPC 2.0, stdlib only — see `src/brig/mcp.py`). A wiring snippet lives at `configs/mcp.json`; replace the `"."` placeholder with the **absolute** path of this checkout, then restart your client.

Generic snippet:

```json
{"mcpServers": {"brig": {"command": "uv", "args": ["run", "--directory", "/abs/path/to/brig", "python", "-m", "brig.mcp"]}}}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.brig]
command = "uv"
args = ["run", "--directory", "/abs/path/to/brig", "python", "-m", "brig.mcp"]
```

Claude Code (`.mcp.json` in your project or global config): use the generic snippet above.

Typical agent flow: `index` (or `brig index` beforehand) → `search_symbols` → `get_symbol` for exact spans → `callers_callees` / `blast_radius` before edits → `check_refs` before deletes. Details: `configs/README.md`.

## HTTP API

Read-only. Same queries, no new tools. Binds loopback unless `--host` is set.

```sh
brig serve --port 8000
curl "http://127.0.0.1:8000/api/v1/search?slug=myrepo&q=norm_path"
```

| Endpoint | Query params |
| --- | --- |
| `/api/v1/live` | — returns `{"status": "ok"}` |
| `/api/v1/slugs` | — lists indexed slugs |
| `/api/v1/search` | `slug`, `q` |
| `/api/v1/outline` | `slug`, optional `path` |
| `/api/v1/symbol` | `slug`, `id` (positive integer) |
| `/api/v1/refs` | `slug`, `ident` |
| `/api/v1/callers` | `slug`, `qualname`, optional `depth` (1–3) |
| `/api/v1/callees` | `slug`, `qualname`, optional `depth` (1–3) |
| `/api/v1/blast` | `slug`, `target` |

Errors are `{"error": msg}` with 400 (missing/bad param) or 404 (unknown slug/endpoint). `/` serves a tiny human landing page. Routes: `src/brig/serve.py`.

## Docker

```sh
mkdir -p deploy/repos  # checkouts to index, mounted read-only
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml exec brig brig index /repos/<name> --slug <name>
curl "http://localhost/brig/api/v1/search?slug=<name>&q=<query>"
```

The image serves `brig serve --host 0.0.0.0 --port 8000` (`Dockerfile`); index data lives in the `brig-index` volume, repos mount at `/repos:ro`, healthcheck hits `/api/v1/live`. The compose file targets a Traefik homelab gateway (`PathPrefix(`/brig`)`) — adjust networks/labels if you don't use one.

## Architecture

```text
repo -> tree-sitter parse -> symbols/edges -> SQLite WAL (~/.brig/index/{slug}.db)
  -> 7 MCP tools + CLI mirror (index|search|outline|symbol|refs|callers|callees|blast|list)
  -> HTTP transport (brig serve, same queries over GET as JSON)
```

Tables: `files(path, sha256, mtime, size)`, `symbols(path, qualname, kind, sig, doc, start_byte, end_byte)`, `imports(src_path, dst_spec)`, `edges(src_id, dst_id, kind, confidence)`. New languages are additive: one `LanguageSpec` per language in `src/brig/langs/` plus a registry entry — no core changes. Design: `SPEC.md`. Agent profile: `AGENTS.md`.

## Token savings

Measured on this repo (`brig` itself, 62 files): the full outline is ~9k tokens vs ~33k to read all Python sources (**~72% saved**); a single `search` + `get_symbol` round-trip returns a ~90-token exact slice instead of a whole file. Per-fix savings on larger repos typically land at 90%+ vs naive whole-file reads (estimated — scales with repo size and how many files the agent would otherwise open).

## Project layout

```text
src/brig/db.py      SQLite WAL storage + incremental index pipeline
src/brig/parse.py   tree-sitter parse pipeline (Symbol, ExtractResult)
src/brig/langs/     LanguageSpec registry (c/cpp/csharp/java/python/js/ts)
src/brig/query.py   search/outline/refs/callers/blast + _meta envelope
src/brig/cli.py     argparse CLI mirror
src/brig/mcp.py     stdio MCP server (7 tools, hard cap)
src/brig/serve.py   read-only HTTP API
tests/fixtures/     tiny synthetic repos for tests
configs/mcp.json    MCP client wiring snippet
deploy/             Dockerfile + compose for gateway hosting
skills/             investigator/builder/reviewer agent skills
plans/              per-task plans (see plans/README.md)
```

## Development

```sh
uv sync
uv run pytest            # full suite, must be green every change
uv run pytest tests/test_langs_java.py   # narrower run
uv run brig index .      # smoke test on brig itself
```

Conventions: TDD (failing test first), conventional commits (`feat:` `fix:` `test:` `docs:` `refactor:`), 1–2 files per change with `path:line-range — change` receipts. `uv.lock` is committed. Index files (`*.db`) and `.local/` are gitignored — never commit them. Non-goals (bloat firewall): no embeddings/vector store, no graph DBs, no per-IDE installers, no telemetry — anything needing a backend beyond `tree-sitter` + stdlib `sqlite3` waits for v2.

## Links

- Spec: `SPEC.md` · Agents: `AGENTS.md` · Implementation plan: `PLAN.md`
- Swarm kit: `skills/`, `plans/` (template: `plans/README.md`)
- MCP wiring: `configs/mcp.json`, `configs/README.md`
- Service definition: `deploy/docker-compose.yml`

MIT — see `LICENSE`.
