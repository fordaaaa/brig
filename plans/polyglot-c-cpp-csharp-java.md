# polyglot-c-cpp-csharp-java: add C, C++, C#, Java LanguageSpecs

## Goal

Add four `LanguageSpec`s so `.cs/.cpp/.c/.java` yield symbols (class/method/function) with qualname, kind, sig, doc, and byte offsets, reusing the registry pattern in `src/brig/langs/`. Unlocks C#/C++/C/Java repos for exact-span retrieval.

## Non-goals

- No schema migration, no new query/MCP tools (7-tool hard cap stays).
- No CSS/HTML symbols (separate skip-unsupported task).
- No full template/generic resolution, no overload disambiguation beyond qualname+kind uniqueness.
- No new backend beyond `tree-sitter` + `tree-sitter-*` grammars.

## Files in scope

- `pyproject.toml` — add `tree-sitter-c`, `tree-sitter-cpp`, `tree-sitter-c-sharp`, `tree-sitter-java`
- `src/brig/langs/c.py` — C spec (`.c,.h`; C owns `.h`)
- `src/brig/langs/cpp.py` — C++ spec (`.cpp,.hpp,.cc,.cxx,.hh,.h++`; NOT `.h`)
- `src/brig/langs/csharp.py` — C# spec (`.cs`, `using` imports)
- `src/brig/langs/java.py` — Java spec (`.java`, `package+import`)
- `src/brig/langs/__init__.py` — register 4 specs (C before C++)
- `tests/test_langs_c.py`, `tests/test_langs_cpp.py`, `tests/test_langs_csharp.py`, `tests/test_langs_java.py` — fixture-based tests
- `tests/fixtures/sample.c`, `sample.cpp`, `sample.cs`, `sample.java` — tiny fixtures

## Verification command

```sh
uv run pytest tests/test_langs_c.py tests/test_langs_cpp.py tests/test_langs_csharp.py tests/test_langs_java.py
uv run pytest
```

## Definition of done

- [ ] `get_spec()` dispatches all new suffixes; `get_spec("x.h")` is C
- [ ] Each fixture extracts expected `{qualname: kind}` with `kind in {function,class,method}`
- [ ] Byte spans slice source correctly
- [ ] `len(sig)<=200, len(doc)<=500`; imports exact-order list
- [ ] `uv run pytest` green (full suite, no regressions)

## Open threads

- C-family `sig` anchor: cut before `{`/`;` but keep throws/where; strip attributes.
- Import canonical form: angle vs quote includes, wildcard/static imports.
- Overloads/generics duplicate `(path,qualname,kind)` UNIQUE handling.
