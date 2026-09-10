# Dogfood output — indexing brig itself (2026-09-10)

Commands run verbatim from the repo root.
Note: `search`/`outline`/`refs` initially failed with
`multiple indexed repos ['', '.db', 'brig']; require --slug` due to legacy
dotfiles in `~/.brig/index` (see `plans/fix-stale-dot-slugs.md`). Outputs below
were captured after that fix, running the bare commands exactly as specified.

## 1. `uv run brig index .`

```json
{
  "indexed": 4,
  "skipped": 39,
  "removed": 0,
  "slug": "brig"
}
```

## 2. `uv run brig search query`

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

## 3. `uv run brig outline src/brig/query.py`

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
        "qualname": "freshness_for_file",
        "kind": "function",
        "sig": "def freshness_for_file(\n    conn: sqlite3.Connection, path: str, repo_root: Path | str | None = None\n) -> str:"
      },
      {
        "qualname": "_scan_counts",
        "kind": "function",
        "sig": "def _scan_counts(conn: sqlite3.Connection, extra: dict | None = None) -> dict:"
      },
      {
        "qualname": "_worst",
        "kind": "function",
        "sig": "def _worst(freshnesses) -> str:"
      },
      {
        "qualname": "_meta",
        "kind": "function",
        "sig": "def _meta(conn: sqlite3.Connection, freshness: str, scan_counts: dict | None = None) -> dict:"
      },
      {
        "qualname": "_repo_freshness",
        "kind": "function",
        "sig": "def _repo_freshness(conn: sqlite3.Connection, repo_root: Path | str | None) -> str:"
      },
      {
        "qualname": "_symbol_row",
        "kind": "function",
        "sig": "def _symbol_row(row: tuple) -> dict:"
      },
      {
        "qualname": "_degrees",
        "kind": "function",
        "sig": "def _degrees(conn: sqlite3.Connection) -> dict[int, int]:"
      },
      {
        "qualname": "search_symbols",
        "kind": "function",
        "sig": "def search_symbols(\n    conn: sqlite3.Connection, q: str, repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "get_symbol",
        "kind": "function",
        "sig": "def get_symbol(\n    conn: sqlite3.Connection, symbol_id: int, repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "get_outline",
        "kind": "function",
        "sig": "def get_outline(\n    conn: sqlite3.Connection, path: str | None = None, repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "check_refs",
        "kind": "function",
        "sig": "def check_refs(\n    conn: sqlite3.Connection, identifier: str, repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "add_edge",
        "kind": "function",
        "sig": "def add_edge(\n    conn: sqlite3.Connection,\n    src_id: int,\n    dst_id: int,\n    kind: str = \"calls\",\n    confidence: str = \"INFERRED\",\n) -> int:"
      },
      {
        "qualname": "infer_call_edges",
        "kind": "function",
        "sig": "def infer_call_edges(\n    conn: sqlite3.Connection, repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "_walk_calls",
        "kind": "function",
        "sig": "def _walk_calls(\n    conn: sqlite3.Connection,\n    qualname: str,\n    depth: int,\n    direction: str,\n    repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "callers",
        "kind": "function",
        "sig": "def callers(\n    conn: sqlite3.Connection,\n    qualname: str,\n    depth: int = 1,\n    repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "callees",
        "kind": "function",
        "sig": "def callees(\n    conn: sqlite3.Connection,\n    qualname: str,\n    depth: int = 1,\n    repo_root: Path | str | None = None\n) -> dict:"
      },
      {
        "qualname": "_spec_hits_file",
        "kind": "function",
        "sig": "def _spec_hits_file(spec: str, path: str) -> bool:"
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

## 4. `uv run brig refs parse`

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
      "path": "src/brig/langs/javascript.py",
      "spec": "brig.parse"
    },
    {
      "kind": "import",
      "path": "src/brig/langs/python.py",
      "spec": "brig.parse"
    },
    {
      "kind": "import",
      "path": "src/brig/langs/typescript.py",
      "spec": "brig.parse"
    },
    {
      "kind": "import",
      "path": "src/brig/langs/__init__.py",
      "spec": "brig.parse"
    },
    {
      "kind": "import",
      "path": "src/brig/cli.py",
      "spec": "brig.parse"
    },
    {
      "kind": "import",
      "path": "src/brig/db.py",
      "spec": "brig.parse"
    },
    {
      "kind": "text",
      "path": "AGENTS.md",
      "matches": 2,
      "lines": [42]
    },
    {
      "kind": "text",
      "path": "PLAN.md",
      "matches": 1,
      "lines": [8]
    },
    {
      "kind": "text",
      "path": "SPEC.md",
      "matches": 1,
      "lines": [18]
    },
    {
      "kind": "text",
      "path": "plans/fix-stale-dot-slugs.md",
      "matches": 1,
      "lines": [28]
    },
    {
      "kind": "text",
      "path": "src/brig/cli.py",
      "matches": 1,
      "lines": [139]
    },
    {
      "kind": "text",
      "path": "src/brig/db.py",
      "matches": 3,
      "lines": [57, 318]
    },
    {
      "kind": "text",
      "path": "src/brig/langs/__init__.py",
      "matches": 2,
      "lines": [12, 31]
    },
    {
      "kind": "text",
      "path": "src/brig/langs/javascript.py",
      "matches": 2,
      "lines": [17, 145]
    },
    {
      "kind": "text",
      "path": "src/brig/langs/python.py",
      "matches": 2,
      "lines": [11, 78]
    },
    {
      "kind": "text",
      "path": "src/brig/langs/typescript.py",
      "matches": 4,
      "lines": [5, 17, 33, 35]
    },
    {
      "kind": "text",
      "path": "src/brig/mcp.py",
      "matches": 2,
      "lines": [195, 441]
    },
    {
      "kind": "text",
      "path": "src/brig/parse.py",
      "matches": 1,
      "lines": [1]
    },
    {
      "kind": "text",
      "path": "tests/test_langs_js.py",
      "matches": 6,
      "lines": [7, 35, 43, 58, 71, 78]
    },
    {
      "kind": "text",
      "path": "tests/test_langs_python.py",
      "matches": 7,
      "lines": [7, 35, 43, 54, 68, 79, 86]
    },
    {
      "kind": "text",
      "path": "tests/test_langs_ts.py",
      "matches": 6,
      "lines": [7, 33, 41, 56, 68, 75]
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
