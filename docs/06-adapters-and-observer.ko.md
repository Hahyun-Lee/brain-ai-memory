# Semantic adapter와 공개 observer

이 문서는 Brain-AI가 ATL 검색을 위해 Smart Connections의 **MCP client**로
동작하는 경우를 설명합니다. Brain-AI 자체를 agent에 MCP server로 제공하려면
[한국어 MCP server guide](07-mcp-server.ko.md)를 참고하세요. 두 방향은 서로
독립적이며 함께 사용할 수 있습니다.

## Smart Connections는 전체 시스템이 아니라 ATL adapter입니다

`.brain-ai/config.json`의 `semantic.backend`를 다음 중 하나로 지정합니다.

- `local`: SQLite knowledge와 다국어 BM25
- `vault-bm25`: Markdown file 직접 lexical 검색
- `smart-connections`: MCP `search_notes` 사용. v1, upstream `plugin` profile,
  또는 MCP 장애일 때 vault BM25 safety path 병합

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

Adapter는 v1 result list와 v2 response envelope를 모두 처리합니다. v1 또는
v2 `plugin` profile에서는 score scale이 다른 MCP와 local BM25 ranking을
reciprocal-rank fusion으로 결합합니다. v2 hybrid profile(`fast`, `balanced`,
`adaptive`, `quality`)은 server가 이미 disk file을 대조하고 BM25를 fusion했기
때문에 같은 lexical evidence를 두 번 더하지 않고 server ranking을 보존합니다.
MCP가 실패하면 local BM25가 동작합니다. Diagnostic에는 MCP mode, profile,
warning, latency, local fallback 실행 여부가 기록됩니다.

Adapter lifetime 동안 stdio server process 하나를 재사용하므로 local embedding과
reranker model을 query마다 다시 load하지 않습니다. 명시적 shutdown lifecycle이
있는 host에 embedding할 때는 `adapter.close()`를 호출하세요. Process 종료 시에도
child process가 정리됩니다.

v2 hybrid fork에서는 `mcp_env`에 `SMART_SEARCH_PROFILE=adaptive`를 지정하는 것을
권장합니다. Adapter는 Markdown 전체를 agent context에 넣지 않고 v2의 제한된
snippet을 사용합니다. `SMART_VAULT_PATH`는 항상 `vault_path`에서 설정되므로
`mcp_env`로 덮어쓸 수 없습니다.

검증한 hybrid server는
[Hahyun-Lee/smart-connections-mcp](https://github.com/Hahyun-Lee/smart-connections-mcp)입니다.
Source에서 build한 뒤 `mcp_command`가 `dist/index.js`를 가리키게 하세요. 현재
unscoped npm package는 hybrid fork가 아니라 upstream을 설치합니다.

외부 vault/MCP result에는 Brain-AI entity binding이 없습니다. `v0.3`은 엄격한
entity-scoped recall에서 project를 조용히 섞지 않도록 이 unverified result를
제외합니다. 이를 확인하려면 unscoped recall을 실행하거나 선택한 knowledge를
local store로 import하고 entity에 연결하세요.

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
