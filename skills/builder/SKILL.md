# builder skill — plan executor

> Executes a plan file, nothing else. Small diffs, receipts, tests.

## Input

A plan file at `plans/<task>.md` (see `plans/README.md` template).
Do not start without one. The plan's "files in scope" is authoritative.

## Procedure

1. Read the plan file fully before touching code.
2. Work in steps of **1–2 files max per step**.
3. After each step, run the plan's verification command
   (default: `uv run pytest`) — it must be green before continuing.
4. End every change with a receipt line:

```text
path:line-range — change
```

## Rules

- Execute only what the plan authorizes. No drive-by refactors,
  no out-of-scope files, no new backends or deps beyond
  `tree-sitter` + stdlib `sqlite3` (v2 firewall per SPEC.md).
- TDD where the plan requires it: failing test first, then minimal
  implementation.
- Byte offsets from tree-sitter are authoritative; never guess spans.
- Public-repo hygiene: no secrets, tokens, or personal paths in commits.

## Terminal refusal lines

Copy exactly. These end the step — do not work around them:

```text
too-big. split:
```

```text
needs-confirm. op:
```

```text
ambiguous. ask:
```

Use `too-big. split:` when a step would exceed 2 files — name the
proposed split after the prefix. Use `needs-confirm. op:` before any
destructive or out-of-scope operation — name it after the prefix.
Use `ambiguous. ask:` when the plan contradicts itself or underspecifies
the change — state the question after the prefix.

## Handoff

Output is the diff plus receipt lines. The reviewer verifies the diff
against the plan file line by line.
