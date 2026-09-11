# brig

Deterministic code-graph index for one repo: tree-sitter parses Python, JavaScript, and TypeScript into symbols in one SQLite WAL file, queryable through a CLI and 7 MCP tools.

## Why

Agents waste tokens reading whole files. Index once, retrieve exact spans — symbol search, outlines, refs, caller/callee walks — with freshness and scan counts in every `_meta` envelope instead of guessed negatives. No embeddings, no graph DB, no telemetry. Design: `SPEC.md`. Agent profile: `AGENTS.md`.

## Quickstart

Requires Python >= 3.11.

```sh
uv sync
uv run pytest      # must be green
uv run brig --help # CLI smoke test
uv run brig index .
uv run brig search query
uv run brig outline src/brig/query.py
uv run brig refs parse
uv run brig callers some.qualname --depth 2
uv run brig blast src/brig/query.py
uv run brig list
```

Storage is one SQLite WAL file per repo at `~/.brig/index/{slug}.db`. Flags: `--slug` picks the repo when several are indexed, `--repo` overrides the checkout path, `--root` moves the store, `--depth` caps caller/callee walks at 3.

## Architecture

```text
repo -> tree-sitter parse -> symbols/edges -> SQLite WAL (~/.brig/index/{slug}.db)
  -> 7 MCP tools + CLI mirror (brig index|search|outline|symbol|refs|callers|callees|blast|list)
  -> HTTP transport (brig serve, same queries over GET as JSON)
```

## Serve

Read-only HTTP API. Same queries, no new tools. Binds loopback unless `--host` is set.

```sh
brig serve --port 8000
curl "http://127.0.0.1:8000/api/v1/search?slug=brig&q=norm_path"
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

Errors are `{"error": msg}` with 400 (missing/bad param) or 404 (unknown slug/endpoint). Flags from `src/brig/cli.py`: `brig serve [--host 127.0.0.1] [--port 8000] [--root ~/.brig]`. Routes from `src/brig/serve.py`.

## Docker

```sh
mkdir -p deploy/repos  # checkouts to index, mounted read-only
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml exec brig brig index /repos/<name> --slug <name>
curl "http://localhost/brig/api/v1/search?slug=<name>&q=<query>"
```

Image serves `brig serve --host 0.0.0.0 --port 8000` (`Dockerfile`), index data lives in the `brig-index` volume, repos mount at `/repos:ro`, healthcheck hits `/api/v1/live`.

## Homelab path

`deploy/docker-compose.yml` joins the external `homelab-gateway` network and carries the Traefik labels: `PathPrefix(`/brig`)`, priority `10`, `strip-brig-prefix@file`, `loadbalancer.server.port=8000`. The gateway side needs the matching `strip-brig-prefix` middleware (pattern in the homelab repo at `plugins/brig.yml`). Gateway URL after attach: `http://localhost/brig/api/v1/live`.

## Status

| Subcommand | What it does | Status |
| --- | --- | --- |
| `index` | Incrementally index a repo | Live — `brig index <path> [--slug]` |
| `search` | Search symbols by query | Live |
| `outline` | Repo or single-file outline | Live |
| `symbol` | Get a symbol with its source slice | Live — `brig symbol <id>` |
| `refs` | Check references of an identifier | Live |
| `callers` | Transitive callers of a qualname | Live — `--depth` capped at 3 |
| `callees` | Transitive callees of a qualname | Live — `--depth` capped at 3 |
| `blast` | Blast radius of a symbol or file | Live |
| `list` | List indexed slugs | Live |
| `serve` | Run the read-only HTTP API (default `127.0.0.1:8000`) | Live |

MCP tools (7, hard cap): `index`, `search_symbols`, `get_symbol`, `get_outline`, `callers_callees` (`direction: callers|callees`), `blast_radius`, `check_refs`. Wiring snippet: `configs/mcp.json` (replace the `"."` placeholder with your checkout path).

## Links

- Spec: `SPEC.md` (Tool surface section) · Agents: `AGENTS.md` · Swarm kit: `skills/`, `plans/`
- MCP wiring: `configs/mcp.json`, `configs/README.md`
- Service definition: `deploy/docker-compose.yml`

MIT — see `LICENSE`.
