# MCP로 Brain-AI Memory 연결하기

MCP server는 공개 runtime을 기존 agent에 연결하는 가장 짧은 경로입니다.
Model이나 workflow engine을 대체하지 않고 typed context, deterministic action
check, memory write, entity relation, lifecycle handoff를 제공합니다.

## 설치와 시작

Repo checkout에서 실행합니다.

```bash
python -m pip install ".[mcp]"
brain-ai-mcp --home /absolute/path/to/.brain-ai
```

기본 transport는 `stdio`입니다. 일반적인 client 설정은 다음과 같습니다.

```json
{
  "mcpServers": {
    "brain-ai-memory": {
      "command": "brain-ai-mcp",
      "args": ["--home", "/absolute/path/to/.brain-ai"]
    }
  }
}
```

Client와 CLI가 같은 state를 사용하도록 home은 absolute path로 지정하세요.

### Codex CLI, desktop, IDE

Codex client들은 MCP 설정을 공유합니다. `~/.codex/config.toml` 또는 trusted
project의 `.codex/config.toml`에 다음을 추가합니다.

```toml
[mcp_servers.brain_ai_memory]
command = "brain-ai-mcp"
args = ["--home", "/absolute/path/to/.brain-ai"]
```

공식 문서는 desktop app, CLI, IDE extension에서 local stdio와 Streamable HTTP
server를 지원한다고 설명합니다. [Codex MCP 공식
문서](https://developers.openai.com/codex/mcp)

### Claude Code

Local stdio server를 등록합니다.

```bash
claude mcp add --transport stdio brain-ai-memory -- \
  brain-ai-mcp --home /absolute/path/to/.brain-ai
claude mcp get brain-ai-memory
```

협업자와 검토 가능한 `.mcp.json`을 공유하려는 경우에만 `--scope project`를
사용합니다. Claude Code는 project-scoped server를 사용자에게 승인받습니다.
[Claude Code MCP 공식 문서](https://code.claude.com/docs/en/mcp)

격리된 local HTTP 환경에서는 다음처럼 실행할 수 있습니다.

```bash
brain-ai-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

이 alpha server를 public interface에 bind하면 안 됩니다. 인증, multi-tenancy,
network hardening은 아직 포함하지 않습니다.

## Agent가 호출할 수 있는 기능

| MCP interface | 책임 |
|---|---|
| `brain_context` | optional entity를 binding하고 recall을 routing한 뒤 action verdict 반환 |
| `brain_check_action` | 제안된 행동 하나를 allow, warn, block으로 deterministic 판정 |
| `brain_remember` | 사건, 사실, 규칙, exact state를 담당 store에 기록 |
| `brain_upsert_entity` | stable identity와 alias 생성 또는 resolve |
| `brain_add_relation` | 기존 entity 사이에 typed edge 추가 |
| `brain_checkpoint` | handoff를 저장하고 consolidation candidate 표시 |
| `brain_consolidation_preview` | event promotion을 적용하지 않고 검토 |
| `brain_supersede` | provenance를 보존하며 오래된 사실을 새 version으로 교체 |
| `brain-ai://status` | runtime health와 component count 조회 |
| `brain-ai://ontology` | 검증된 component/channel schema 조회 |

Server는 임의 command execution을 의도적으로 제공하지 않습니다.
`brain_check_action`은 행동 허용 여부를 판정하고, 실제 실행은 host agent나
workflow engine이 담당합니다. 명시적인 fallback command는 operator가 process
boundary를 통제하는 local `brain-ai sequence` CLI에서 계속 사용할 수 있습니다.

## 권장 host-agent loop

1. User query, 의도한 action, 알고 있는 entity와 함께 `brain_context`를
   호출합니다.
2. `gate.allowed = false`는 참고 문구가 아니라 중단 조건으로 처리합니다.
3. Model의 추정값보다 `IPS`에 반환된 exact value를 우선합니다.
4. 허용된 행동을 host agent에서 실행합니다.
5. 새 event 또는 exact state를 기록하고 `brain_checkpoint`를 호출합니다.
6. Consolidation candidate는 local에서 검토하고 승인 후 적용합니다.

이것은 host model의 conversation history를 대체하는 것이 아니라 control
protocol입니다. Framework의 session store는 대화 기록을 계속 담당하고,
Brain-AI는 분화된 operational memory와 action policy를 담당할 수 있습니다.

## Integration 강도를 정직하게 선택하기

| 단계 | 연결하는 것 | 얻는 것 |
|---|---|---|
| 진단 | `brain-ai tour`, `run`, `status`를 수동 실행 | mapping이 내 failure에 맞는지 확인 |
| advisory agent memory | MCP를 연결하고 `brain_context` 호출을 지시 | scoped context, exact state, audit, deterministic verdict; tool 호출 여부는 host loop에 의존 |
| enforced control | mutation을 `brain-ai harness`로 통과시키거나 host pre-action hook이 `brain_check_action`을 소비 | block verdict가 실제 중단 조건이 됨 |

MCP 연결만으로는 두 번째 단계이며 세 번째 단계가 아닙니다. Server instruction은
client의 tool 선택을 돕지만, 관련 없는 모든 host tool call이 gate를 통과한다고
보장하지 못합니다. Production integration은 host boundary에서 이를 강제해야
합니다.

Advisory integration에는 다음과 같은 instruction을 추가합니다.

```text
세션을 넘는 작업이나 변경 행동 전에는 active entity와 proposed action으로
brain_context를 호출한다. gate.allowed가 false이면 중단한다. 추정값보다 IPS의
exact state를 우선한다. 작업 후 변경된 state를 기록하고 checkpoint를 만든다.
```

## 현재 경계

`v0.3` MCP interface는 local-first single-user alpha입니다. Access control,
encryption at rest, distributed store migration, concurrent-writer coordination,
framework-specific automatic hook wiring은 아직 포함하지 않습니다. 이는 production
service의 release gate로 남아 있습니다.
