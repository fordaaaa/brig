# AGENTS.md — brig canonical agent profile

> Single source of truth for agents. See SPEC.md (swarm layer) and PLAN.md (phases).

## Overview

brig = deterministic tree-sitter code-graph index + 7 MCP tools + CLI mirror.
Storage: one SQLite WAL file per repo. No embeddings, no graph DB, no telemetry.

## Build / test

- Setup: `uv sync`
- Test: `uv run pytest` (must be green every phase)
- Lint: none configured yet
- CLI smoke: `uv run brig`

## Conventions

- TDD: write failing tests first, then minimal implementation.
- Conventional commits: `feat:` `fix:` `test:` `docs:` `refactor:`.
- Small diffs: 1–2 files per step; receipt format `path:line-range — change`.
- Handoff: investigator output feeds the plan; builder executes only the plan;
  reviewer verifies diff vs plan line.
- Refusal lines are terminal: `too-big. split:`, `needs-confirm. op:`,
  `ambiguous. ask:`.
- Public-repo hygiene: no secrets, tokens, or personal paths in commits.
- Label README claims honestly: measured vs estimated.

## Repo map

- `src/brig/db.py` — SQLite WAL storage, incremental upserts.
- `src/brig/parse.py` — tree-sitter parse pipeline.
- `src/brig/langs/` — LanguageSpec registry (python/js/ts first).
- `src/brig/query.py` — search/outline/refs/callers/blast + `_meta` envelope.
- `src/brig/cli.py` — argparse CLI mirror.
- `src/brig/mcp.py` — stdio MCP server (7 tools, hard cap).
- `tests/fixtures/` — tiny synthetic repos for tests.

## Gotchas

- Python >= 3.11 required.
- `uv.lock` IS committed (brig is an app, not a lib).
- Index files (`*.db`) and `.local/` are gitignored — never commit them.
- Byte offsets from tree-sitter are authoritative; never guess spans.
- Absence claims require scan counts in `_meta` — never hallucinate negatives.
- New backends or deps beyond `tree-sitter` + stdlib `sqlite3` wait for v2.
- No per-IDE installers; one `mcp.json` snippet only.
