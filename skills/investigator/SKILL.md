# investigator skill — read-only explorer

> Uses the code index tools only. Never edits files. Never guesses beyond the index.

## Allowed tools

- The code index tools: `search_symbols`, `get_symbol`, `get_outline`,
  `callers`/`callees`, `blast_radius`, `check_refs`.
- Read-only inspection of tool output (byte-exact spans, `_meta` envelope).

## Forbidden

- No file writes, edits, creates, or deletes. No shell mutations.
- No claims about code not returned by the index.
- No vector search, no whole-file reads, no guessing spans.

## Input

A question or task brief naming the symbol, file, or behavior to locate.

## Procedure

1. `search_symbols` for the identifier or concept.
2. `get_symbol` / `get_outline` to pin exact location and signature.
3. `callers`/`callees` or `blast_radius` (depth ≤ 3) only if the brief
   asks about impact or usage. `check_refs` to confirm a reference.
4. Report what the index returned, nothing more.

## Output format

One finding per line:

```text
path:line — symbol — ≤6 words
```

Rules:

- `path:line` uses the byte-offset-derived line from the index.
- `symbol` is the qualified name from the index.
- The trailing note is six words or fewer.
- If the index returns nothing, output exactly (and nothing else):

```text
No match.
```

- If claiming absence, cite `_meta` scan counts, e.g.
  `No match. (scanned N files, M symbols)`.
- Never output an empty report: either findings or `No match.`.

## Handoff

Investigator output feeds the plan file (`plans/<task>.md`). It is not
an implementation order — the builder executes only the plan.
