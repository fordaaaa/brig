# fix-dot-path-slug: `brig index .` creates an empty slug and unusable index

## Goal

Make `brig index .` (and any repo path whose `Path.name` is empty) default to the
resolved directory name, so the index lands in `<dirname>.db` and follow-up
commands (`search`, `outline`, `refs`, `list`) resolve it without `--slug`.

## Non-goals

- No storage schema changes; no new query tools or CLI subcommands.
- No change to explicit `--slug` behavior.

## Files in scope

- `src/brig/cli.py` — default slug from resolved repo dir name; list slugs by
  stripping the `.db` suffix instead of `Path.stem`.
- `src/brig/db.py` — same resolved-name default in `index_repo`; reject empty /
  path-like slugs in `open_or_create`.
- `tests/test_cli_dot_slug.py` — regression tests (dot-path index + search roundtrip).

## Repro

```sh
uv run brig index .          # prints "slug": "" and writes ~/.brig/index/.db
uv run brig search query     # opens a NEW empty ~/.brig/index/.db.db -> 0 symbols scanned
uv run brig list             # shows slugs [".db", ".db"] (stem of dotfiles)
```

Root cause: `Path(".").name == ""`, so `args.slug or repo.name` yields `""`;
`db_path("", ...)` is `.db`; and `_available_slugs` uses `p.stem`, which does
not strip the suffix from dotfiles (stem of `.db` is `.db`).

## Verification command

```sh
uv run pytest tests/test_cli_dot_slug.py tests/test_cli.py tests/test_db.py
```

## Definition of done

- [ ] `brig index .` in a dir named `X` prints `"slug": "X"` and creates `X.db`
- [ ] Follow-up `search` without `--slug` scans the indexed symbols (>0)
- [ ] `brig list` shows the real slug, no `.db` entries
- [ ] `uv run pytest` green (full suite, no regressions)

## Open threads

- None.
