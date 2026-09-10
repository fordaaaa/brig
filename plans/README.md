# plans — task plan template

Each task gets one file: `plans/<task>.md` (e.g. `plans/add-ruby-spec.md`,
`plans/fix-stale-index.md`). The builder executes only the plan; the
reviewer checks the diff against it. Keep plans short and specific.

## Template

```markdown
# <task slug>: <short goal>

## Goal

<1–2 sentences: what changes and why.>

## Non-goals

- <explicitly out of scope>
- <another exclusion>

## Files in scope

- `path/to/file.py` — <what changes there>
- `tests/test_x.py` — <covering test>

(Max 1–2 files per builder step; list all files the task may touch.
Anything not listed is out of scope and the reviewer will flag it.)

## Verification command

```sh
uv run pytest
```

(Or the narrower command, e.g. `uv run pytest tests/test_x.py`. Must be
green after every builder step.)

## Definition of done

- [ ] <observable criterion 1>
- [ ] <observable criterion 2>
- [ ] `uv run pytest` green

## Open threads

- <unresolved question or follow-up> (or `None.`)
```

## Filled-in example

```markdown
# add-ruby-spec: add ruby language spec

## Goal

Add a Ruby `LanguageSpec` so `.rb` files yield symbols (defs/classes)
with qualname, kind, sig, doc, and byte offsets, reusing the registry
pattern in `src/brig/langs/`.

## Non-goals

- No new storage schema or query tools.
- No new dependencies beyond `tree-sitter` + `tree-sitter-ruby`.

## Files in scope

- `src/brig/langs/ruby.py` — Ruby LanguageSpec (defs, classes, imports)
- `tests/test_langs_ruby.py` — fixture-based extraction tests

## Verification command

```sh
uv run pytest tests/test_langs_ruby.py
```

## Definition of done

- [ ] `.rb` fixture extracts `class` + `def` with correct byte offsets
- [ ] `get_spec("x.rb")` returns the Ruby spec
- [ ] `uv run pytest` green (full suite, no regressions)

## Open threads

- Which `tree-sitter-ruby` grammar revision to pin in `pyproject.toml`.
```
```
