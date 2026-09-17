# setup-clients: safely index and wire MCP clients

## Goal

Add `brig setup` as a checkout-based onboarding command that indexes a repository
and safely wires Brig into Codex and Claude Code without silently accepting stale
or malformed client configuration.

## Non-goals

- No new dependency, MCP tool, transport, or standalone IDE installer package.
- No automatic replacement of an existing `brig` client entry.
- Do not commit the local setup regression tests, per user request.

## Files in scope

- `src/brig/setup.py` — validate, inspect, and safely add client configuration.
- `src/brig/cli.py` — expose `setup`, validate inputs, and preflight wiring.
- `tests/test_setup.py` — local-only regression coverage; never stage or commit.
- `README.md` — document setup behavior, limits, flags, and local config hygiene.
- `configs/README.md` — document automatic and manual client configuration.
- `SPEC.md` — reconcile the setup command with the bloat firewall.
- `AGENTS.md` — keep the canonical repository guidance consistent with the spec.

## Verification command

```sh
uv run pytest
```

## Definition of done

- [x] Fresh Codex and Claude configurations are added without losing existing entries.
- [x] Matching entries are idempotent; stale or malformed entries fail without rewrites.
- [x] Dry-run validates the slug and configuration while writing nothing.
- [x] Documentation states checkout-only behavior and never suggests committing `.mcp.json`.
- [x] `uv run pytest` is green.
- [x] `tests/test_setup.py` remains untracked and is excluded from every commit.

## Open threads

- Installed-wheel onboarding is deferred until Brig has a stable standalone MCP entry point.
