# brig — spec

> Deterministic code-graph index + minimal agent swarm kit. One MCP server, one profile file, one index file per repo.

## Why

Agents waste tokens reading whole files and whole repos. The inspiration trio (graphify, CodeGraphContext, jcodemunch) proves deterministic tree-sitter + a local index beats vector RAG for code — and all three drown in platform shims, DB matrices, export suites, and 30–90 tool surfaces. `brig` is the anti-bloat version: the ~3k LOC core agents will actually call.

## Core value props

1. **Index once, retrieve exactly.** tree-sitter AST → symbols with byte offsets → fetch exact spans, not whole files.
2. **Graph without a graph DB.** Edges (imports/calls/inherits) derived from symbols on read. Confidence-tagged: `EXTRACTED` vs `INFERRED`.
3. **Swarm coordination from markdown.** One canonical `AGENTS.md` + `plans/<task>.md` + three skills (investigator/builder/reviewer). No per-agent config sprawl.

## Architecture

```
repo -> tree-sitter parse -> symbols/edges -> SQLite WAL (one file per repo) -> 7 MCP tools + CLI mirror
```

- **Storage:** `~/.brig/index/{slug}.db` (WAL) + `raw/` file cache. Sidecar `.meta` for listing without opening DBs. Tables: `symbols(id, path, qualname, kind, sig, doc, hash, start_byte, end_byte)`, `files(path, hash, mtime)`, `imports(src, dst, spec)`, `edges(src, dst, kind, confidence)`.
- **Incremental:** SHA-256 + mtime fast-path per file; reindex only changed files.
- **Languages (v1):** Python, JS/JSX, TS/TSX, C (`.c`/`.h`), C++ (`.cpp`/`.hpp`/`.cc`/`.cxx`), C# (`.cs`), Java (`.java`). Registry pattern (`LanguageSpec` per lang) so more are additive, not core changes. Regex import fallback.
- **Graph:** edges derived at query time from stored symbols + AST pass-2 call resolution. `god_nodes` = degree rank; cycles = DFS. No Leiden, no clustering deps.
- **Every response carries `_meta`:** `{freshness: fresh|edited_uncommitted|stale_index, confidence: 0-1, scan_counts}`. Absence requires scan counts — never hallucinate negatives.

## Tool surface (7, hard cap)

| tool | does |
|---|---|
| `index <path>` | incremental index job |
| `search_symbols <q>` | BM25 + qualname seed + degree tiebreak |
| `get_symbol <id>` | byte-exact source + sig + doc |
| `get_outline <file\|repo>` | names + sigs, no bodies |
| `callers/callees <symbol> [depth]` | transitive, capped at depth 3 |
| `blast_radius <symbol\|file>` | reverse imports + callers, confirmed vs potential |
| `check_refs <identifier>` | imports + text → `is_referenced` bool |

Plus CLI mirror `brig index|search|outline|refs|...` for humans, and HTTP
transport `brig serve` (same 7 over GET as JSON) for humans and gateways.

## Swarm layer

```
AGENTS.md            <- canonical, <150 lines, symlinked as CLAUDE.md
skills/investigator/SKILL.md   read-only: returns `path:line — symbol — ≤6 words` or `No match.`
skills/builder/SKILL.md        1-2 files max per step, receipt `path:line-range — change`
skills/reviewer/SKILL.md       checks diff vs plan, cites plan line
plans/<task>.md       goal, non-goals, files in scope, verification cmd, DoD
.local/memory.md      gitignored, marker-delimited learnings (never auto-write AGENTS.md)
```

Handoff contract: investigator output feeds plan; builder executes only plan; reviewer verifies diff vs plan. Refusal lines are terminal: `too-big. split:`, `needs-confirm. op:`, `ambiguous. ask:`.

## Non-goals (bloat firewall)

No embeddings/vector store. No Neo4j/Falkor/Kuzu. No PDFs/Office/video/docs-LLM ingestion. No PR dashboards, viz suites, Obsidian/wiki exports. No per-IDE installers (one `mcp.json` snippet). No telemetry phone-home. No blocking hooks. If a feature needs a new backend or extra dep beyond `tree-sitter` + stdlib `sqlite3` — it waits for v2.

## Conventions

- Python 3.11+, `uv`-runnable, MIT license.
- Tests before implementation (TDD); pytest; fixtures are tiny synthetic repos in `tests/fixtures/`.
- Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- Public-repo hygiene: no secrets, no personal paths in committed files, README with honest measured-vs-estimated labels.
