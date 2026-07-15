# Semantic adapters and the public observer

This page describes Brain-AI acting as an **MCP client** of Smart Connections
for ATL retrieval. To expose Brain-AI itself as a server to an agent, see the
[MCP server guide](07-mcp-server.md). The directions are independent and may be
used together.

## Smart Connections is an ATL adapter, not the whole system

Set `semantic.backend` in `.brain-ai/config.json` to one of:

- `local`: SQLite knowledge plus multilingual BM25;
- `vault-bm25`: direct lexical search over Markdown files; or
- `smart-connections`: `search_notes` over MCP, with a direct vault BM25 safety
  path for v1, upstream `plugin` profile, or MCP failure.

Example:

```json
{
  "semantic": {
    "backend": "smart-connections",
    "vault_path": "/path/to/Obsidian Vault",
    "mcp_command": ["node", "/path/to/smart-connections-mcp/dist/index.js"],
    "mcp_env": {"SMART_SEARCH_PROFILE": "adaptive"},
    "timeout_seconds": 20,
    "merge_local_vault": true
  }
}
```

The adapter accepts both the v1 result list and the v2 response envelope. With
v1 or the v2 `plugin` profile, it combines MCP and local BM25 rankings using
reciprocal-rank fusion because their raw scores are not calibrated. With the v2
hybrid profiles (`fast`, `balanced`, `adaptive`, or `quality`), the server has
already reconciled disk files and fused BM25, so Brain-AI preserves the server
ranking instead of counting the same lexical evidence twice. An MCP failure
still activates local BM25. Diagnostics expose the MCP mode, profile, warning,
latency, and whether local fallback ran.

The adapter keeps one stdio server process alive for its lifetime, so local
embedding and reranker models are loaded once rather than on every query. Call
`adapter.close()` when embedding it in a host with an explicit shutdown
lifecycle; process exit also cleans up the child.

For the v2 hybrid fork, set `SMART_SEARCH_PROFILE=adaptive` through `mcp_env`.
The adapter uses the bounded v2 snippet rather than injecting the entire
Markdown file into agent context. `SMART_VAULT_PATH` is always set from
`vault_path` and cannot be overridden through `mcp_env`.

The tested hybrid server is
[Hahyun-Lee/smart-connections-mcp](https://github.com/Hahyun-Lee/smart-connections-mcp).
Build it from source and point `mcp_command` at its `dist/index.js`; the
unscoped npm package currently refers to upstream rather than the hybrid fork.

External vault/MCP hits do not carry Brain-AI entity bindings. For strict
entity-scoped recall, `v0.3` omits those unverified hits rather than silently
mixing projects. Run unscoped recall to inspect them, or import/link the
selected knowledge into the local store.

## Clean-room Command Center

```bash
brain-ai serve
```

Open `http://127.0.0.1:8765`. The read-only dashboard reports component counts,
recent control-loop traces, and checkpoint state. JSON is available at:

- `/api/health`
- `/api/status`
- `/api/events`

It reads only the public runtime event contract. It does not copy private
Command Center data, paths, endpoints, credentials, or project-specific logic.
The server has no authentication and is for localhost inspection only.
