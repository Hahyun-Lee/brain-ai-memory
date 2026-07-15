# Semantic adapters and the public observer

## Smart Connections is an ATL adapter, not the whole system

Set `semantic.backend` in `.brain-ai/config.json` to one of:

- `local`: SQLite knowledge plus multilingual BM25;
- `vault-bm25`: direct lexical search over Markdown files; or
- `smart-connections`: `search_notes` over MCP, merged with direct vault BM25.

Example:

```json
{
  "semantic": {
    "backend": "smart-connections",
    "vault_path": "/path/to/Obsidian Vault",
    "mcp_command": ["node", "/path/to/smart-connections-mcp/dist/index.js"],
    "timeout_seconds": 20,
    "merge_local_vault": true
  }
}
```

The adapter combines the rankings with reciprocal-rank fusion because raw
embedding and BM25 scores are not calibrated to the same scale. The merged
fallback addresses two independent operational failures: a semantic
server may be slow or unavailable, and its index may lag files on disk. Results
name `smart-connections-mcp` or `vault-bm25` as their backend so the fallback is
observable rather than silent. The local fallback adds Korean character
bigrams, but remains lexical retrieval.

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
