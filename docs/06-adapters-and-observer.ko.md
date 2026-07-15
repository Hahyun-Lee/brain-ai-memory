# Semantic adapter와 공개 observer

## Smart Connections는 전체 시스템이 아니라 ATL adapter입니다

`.brain-ai/config.json`의 `semantic.backend`를 다음 중 하나로 지정합니다.

- `local`: SQLite knowledge와 다국어 BM25
- `vault-bm25`: Markdown file 직접 lexical 검색
- `smart-connections`: MCP `search_notes`와 vault BM25 결과 병합

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

Embedding score와 BM25 score는 같은 scale이 아니므로 reciprocal-rank fusion으로
두 ranking을 결합합니다. 병합 fallback은 semantic server의 지연·장애와 disk file보다 index가 늦게
갱신되는 문제를 각각 처리합니다. 각 result는 backend를
`smart-connections-mcp` 또는 `vault-bm25`로 표시하므로 fallback이 숨겨지지
않습니다. Local fallback에는 한국어 character bigram이 있지만 lexical
retrieval이며 embedding과 같다고 주장하지 않습니다.

## Clean-room Command Center

```bash
brain-ai serve
```

`http://127.0.0.1:8765`에서 component count, 최근 control-loop trace,
checkpoint를 확인할 수 있습니다. Read-only JSON endpoint는 `/api/health`,
`/api/status`, `/api/events`입니다.

공개 runtime event contract만 읽습니다. 비공개 Command Center의 data, path,
endpoint, credential, project-specific logic을 복사하지 않았습니다. 인증이 없는
localhost inspection 용도이며 network에 직접 노출하면 안 됩니다.
