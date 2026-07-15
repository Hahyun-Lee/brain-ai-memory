# Semantic adapters, event boundaries, and the read-only observer

This page describes Brain-AI acting as an **MCP client** of Smart Connections
for ATL retrieval. To expose Brain-AI itself as a server to an agent, see the
[MCP server guide](07-mcp-server.md). The directions are independent and may be
used together.

Semantic adapters extend only the ATL retrieval side of the memory-management
kernel. They do not ingest provider sessions, assemble or inject model working
context, apply lifecycle decisions, or enforce the optional proposed-action
control bridge.

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
Markdown file into a retrieval result. This is a per-result snippet bound, not
a global token-safe working-context budget, and the adapter does not inject the
result into a model. `SMART_VAULT_PATH` is always set from `vault_path` and
cannot be overridden through `mcp_env`.

The tested hybrid server is
[Hahyun-Lee/smart-connections-mcp](https://github.com/Hahyun-Lee/smart-connections-mcp).
Build it from source and point `mcp_command` at its `dist/index.js`; the
unscoped npm package currently refers to upstream rather than the hybrid fork.

External vault/MCP hits do not carry Brain-AI entity bindings. For strict
entity-scoped recall, `v0.3` omits those unverified hits rather than silently
mixing projects. Run unscoped recall to inspect them, or import/link the
selected knowledge into the local store.

## Event and ingestion boundary

The public episodic contract is an explicitly selected event written through
`brain-ai remember --type episodic`, `brain_remember`, or the Python store API.
The stored record includes an ID, text, source label, tags, optional promotion
metadata and entity bindings, and an ingest timestamp. It is not a provider
transcript envelope and does not contain structured session/message IDs,
occurred-at time, outcome, or a raw-evidence hash unless a host preserves those
separately.

None of the semantic adapters watches Claude Code JSONL, Codex rollouts, chat
logs, or provider transcripts. A host must select and map events explicitly,
with its own privacy, retention, idempotency, and evidence policy. Retrieval hits from an
external vault also remain candidate knowledge; they are not automatically
written into the local event or semantic stores.

## Read-only reference observer

```bash
brain-ai serve
```

Open `http://127.0.0.1:8765`. The read-only dashboard reports component counts,
recent audit events, and checkpoint state. JSON is available at:

- `/api/health`
- `/api/status`
- `/api/events`

`/api/health` reports process liveness and a version string. `/api/status`
reports configuration summary, counts, and the latest checkpoint;
`/api/events` returns recent audit records. These endpoints do not calculate
store integrity, lifecycle backlog, ingestion lag, provenance completeness,
context budget, trends, or alerts, so they should not be described as a memory
health engine.

The observer reads only public runtime state. It does not copy private Command
Center data, paths, endpoints, credentials, or project-specific logic, ingest
new events, or close a control loop. The server has no authentication and is for
localhost inspection only.
