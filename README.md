# brig

brig is a deterministic code-graph index for a single repo: tree-sitter parses
Python, JavaScript, and TypeScript into symbols stored in one SQLite WAL file,
queryable through a CLI and 7 MCP tools. See [SPEC.md](SPEC.md) for the
detailed design (storage, tools, envelopes).

It exists so coding agents get grounded answers — symbol search, file
outlines, reference checks, caller/callee walks — with freshness and scan
counts in every `_meta` envelope instead of guessed negatives. A small swarm
kit (`skills/`, `plans/`) defines how investigator/builder/reviewer agents
use the index without stepping on each other. See [SPEC.md](SPEC.md) for the
swarm protocol and [AGENTS.md](AGENTS.md) for the canonical agent profile.

## Install

Requires Python >= 3.11.

```sh
uv sync
```

## Quickstart

All outputs below are real excerpts from indexing brig itself; the full
transcripts live in [plans/dogfood-output.md](plans/dogfood-output.md).

Index the current repo:

```sh
uv run brig index .
```

```json
{
  "indexed": 4,
  "skipped": 39,
  "removed": 0,
  "slug": "brig"
}
```

Search symbols:

```sh
uv run brig search query
```

```json
{
  "results": [
    {
      "id": 215,
      "path": "tests/test_query.py",
      "qualname": "test_search_empty_query",
      "kind": "function",
      "sig": "def test_search_empty_query(conn):",
      "doc": "",
      "start_byte": 3040,
      "end_byte": 3220,
      "score": 106
    }
  ],
  "_meta": {
    "freshness": "fresh",
    "confidence": 1.0,
    "scan_counts": {
      "files_scanned": 43,
      "symbols_scanned": 269
    }
  }
}
```

Outline a file (excerpt; 19 entries in total):

```sh
uv run brig outline src/brig/query.py
```

```json
{
  "files": {
    "src/brig/query.py": [
      {
        "qualname": "_disk_path",
        "kind": "function",
        "sig": "def _disk_path(path: str, repo_root: Path | str | None) -> Path:"
      },
      {
        "qualname": "search_symbols",
        "kind": "function",
        "sig": "def search_symbols(\n    conn: sqlite3.Connection, q: str, repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "blast_radius",
        "kind": "function",
        "sig": "def blast_radius(\n    conn: sqlite3.Connection, target: str, repo_root: Path | str | None = None\n) -> dict:"
      }
    ]
  },
  "freshness_by_file": {
    "src/brig/query.py": "fresh"
  },
  "error": null,
  "_meta": {
    "freshness": "fresh",
    "confidence": 1.0,
    "scan_counts": {
      "files_scanned": 43,
      "symbols_scanned": 269
    }
  }
}
```

Check references of an identifier (excerpt; import + text evidence):

```sh
uv run brig refs parse
```

```json
{
  "is_referenced": true,
  "evidence": [
    {
      "kind": "import",
      "path": "src/brig/mcp.py",
      "spec": "brig.parse"
    },
    {
      "kind": "import",
      "path": "src/brig/cli.py",
      "spec": "brig.parse"
    },
    {
      "kind": "text",
      "path": "AGENTS.md",
      "matches": 2,
      "lines": [42]
    }
  ],
  "scan_counts": {
    "files_scanned": 43,
    "symbols_scanned": 269
  },
  "_meta": {
    "freshness": "fresh",
    "confidence": 1.0,
    "scan_counts": {
      "files_scanned": 43,
      "symbols_scanned": 269
    }
  }
}
```

## CLI reference

| Subcommand | What it does |
| ---------- | ------------ |
| `index` | Incrementally index a repo |
| `search` | Search symbols by query |
| `outline` | Repo or single-file outline |
| `symbol` | Get a symbol with its source slice |
| `refs` | Check references of an identifier |
| `callers` | Transitive callers of a qualname |
| `callees` | Transitive callees of a qualname |
| `blast` | Blast radius of a symbol or file |

(`uv run brig list` also lists indexed slugs.)

## MCP wiring

`configs/mcp.json` is a snippet, not a drop-in config: it uses `"."` as the
working directory placeholder, so replace it with the absolute path of your
checkout before use. One snippet only — there are no per-IDE installers.

## Swarm kit

- `skills/investigator/SKILL.md` — read-only index explorer; produces findings, changes nothing.
- `skills/builder/SKILL.md` — executes a plan, 1–2 files per step.
- `skills/reviewer/SKILL.md` — verifies the diff against the plan line by line.
- `plans/` — one file per task (`plans/<task>.md`) following the goal /
  non-goals / files-in-scope / verification-command / definition-of-done
  template in `plans/README.md`; the builder executes only the plan.

## Honest limitations

- Language coverage is Python, JavaScript, and TypeScript only.
- `INFERRED` call edges are heuristic name-matching, not scope-aware
  resolution — treat them as leads, not proof.
- No embeddings and no graph database by design: one SQLite WAL file per
  repo, deterministic queries only.

## License

MIT — see [LICENSE](LICENSE).
