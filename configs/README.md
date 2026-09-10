# brig MCP client config
Copy `mcp.json` into your MCP client config.
Replace `"."` in args with the ABSOLUTE repo path.
JSON has no comments, so `"."` is a placeholder.
Example: `["run", "--directory", "/abs/brig", ...]`.
Then restart the client; brig serves 7 tools over stdio.
Tools: index, search_symbols, get_symbol, get_outline,
callers_callees (direction callers|callees), blast_radius,
check_refs. Store defaults to `~/.brig`; override via root.
Requires `uv` on PATH and Python >= 3.11.
