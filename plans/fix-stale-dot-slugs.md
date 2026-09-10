# fix-stale-dot-slugs: bare commands fail on legacy junk slugs in store

## Goal

Bare `brig search/outline/refs` (no `--slug`) must auto-resolve when the store
holds exactly one real index, even if legacy dotfiles (`.db`, `.db.db`) from
the pre-fix `brig index .` empty-slug bug are still on disk.

## Non-goals

- No storage schema changes; no new tools or subcommands.
- No change to explicit `--slug` behavior for valid slugs.

## Files in scope

- `src/brig/db.py` — add `is_valid_slug()`; use it in `open_or_create`
  (also reject leading-dot slugs, which are hidden files on disk).
- `src/brig/cli.py` — `_available_slugs` skips filenames that are not valid
  slugs, so legacy junk never forces a `require --slug` error.
- `tests/test_cli_dot_slug.py` — regression tests (junk dotfiles ignored).

## Repro

```sh
uv run brig index .                       # indexed 0, skipped 42, slug brig
uv run brig search query                  # FAIL: multiple indexed repos ['', '.db', 'brig']; require --slug.
uv run brig outline src/brig/query.py     # FAIL: same
uv run brig refs parse                    # FAIL: same
uv run brig list                           # slugs ['', '.db', 'brig']
```

Store holds `~/.brig/index/.db` (slug `""`) and `.db.db` (slug `".db"`) —
leftovers from before plans/fix-dot-path-slug.md. Verified
`--slug brig` returns correct data (264 symbols, 42 files), so the index
itself is healthy; only slug discovery is at fault.

## Verification command

```sh
uv run pytest
```

## Definition of done

- [ ] Bare `search`/`outline`/`refs` auto-resolve to `brig` with junk present
- [ ] `brig list` shows only `["brig"]`
- [ ] `uv run pytest` green (full suite, no regressions)

## Open threads

- None.
