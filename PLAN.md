# brig — implementation plan

Phases are sequential where noted; within a phase, tasks are parallelizable. Each phase ends with a conventional commit. Verification for every phase: `uv run pytest` green.

## Phase 0 — scaffold (single agent)

- `pyproject.toml` (project `brig`, deps: `tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`; dev: `pytest`), MIT `LICENSE`, `.gitignore`, `README.md` stub.
- Package layout: `src/brig/__init__.py`, `src/brig/cli.py`, `src/brig/db.py`, `src/brig/parse.py`, `src/brig/langs/` (registry), `src/brig/query.py`, `src/brig/mcp.py`.
- `AGENTS.md` (canonical) + `CLAUDE.md` symlink. `tests/` with conftest + one smoke test.
- Commit: `feat: scaffold brig package, tests, agents profile`

## Phase 1 — storage + symbol extraction (TDD) — two agents in parallel after Phase 0

**1a db + indexing core** (`db.py`, `index` pipeline):
- Tests first: open/create `{slug}.db` with WAL, schema migration, upsert symbols/files/imports, incremental reindex (unchanged file skipped via mtime+sha fast-path), `.meta` sidecar.
- Commit: `feat: sqlite wal index with incremental upserts`

**1b language specs** (`langs/`):
- Tests first: for each of python/js/ts: extract defs/classes with qualname, kind, sig, doc, byte offsets from fixture files; import extraction (EXTRACTED).
- Registry pattern: `LanguageSpec` protocol, `get_spec(path)`.
- Commit: `feat: tree-sitter symbol extraction for python/js/ts`

## Phase 2 — queries (TDD), single agent, depends on Phase 1

- `search_symbols` (BM25 or ranked substring if BM25 dep unwanted — stdlib first), `get_symbol` (byte-exact slice via raw cache), `get_outline`, `check_refs`. INFERRED call edges pass-2 + `callers/callees` + `blast_radius` (BFS reverse, confirmed vs potential). `_meta` freshness envelope on all.
- Tests: synthetic fixture repo asserting exact results including negative cases (absent symbol → scan counts).
- Commit: `feat: query tools with meta envelope` (may split into 2-3 commits)

## Phase 3 — surfaces, two agents in parallel

**3a CLI** (`cli.py`): `brig index|search|outline|refs|callers|blast` — argparse, JSON out. Commit: `feat: cli mirror`.
**3b MCP server** (`mcp.py`): stdio MCP exposing the 7 tools, schema < 4000 tokens. One `configs/mcp.json` snippet. Commit: `feat: mcp stdio server`.

## Phase 4 — swarm kit + polish, single agent

- `skills/investigator|builder|reviewer/SKILL.md` per SPEC contracts. `plans/README.md` template. `.local/` gitignored with example.
- README: what/why, quickstart, honest limitations section.
- Full test pass, `uv run brig index` on brig itself as smoke test.
- Commits: `feat: swarm skills and plan templates`, `docs: readme`

## Bug policy

Bugs found in any phase → open `plans/fix-<slug>.md` with repro + verification, delegate to an agent at `xhigh`, commit `fix: <desc>`.
