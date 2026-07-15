# MCP로 Brain-AI Memory 연결하기

MCP server는 공개 runtime을 기존 agent에 연결하는 가장 짧은 경로입니다.
Typed write, scoped recall, entity relation, exact state, explicit handoff
primitive로 구성된 memory-management kernel과 optional proposed-action verdict를
제공합니다. Model, conversation history, working context, workflow engine을
대체하지 않습니다.

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

Memory interface와 downstream control interface는 contract가 다릅니다.

- `brain_remember`, entity/relation tool, checkpoint, consolidation preview,
  supersession과 `brain_context`의 recall 부분은 memory-management kernel을
  사용합니다.
- `brain_check_action`과 `brain_context`의 optional `proposed_action`은 control
  verdict를 반환합니다. MCP는 이를 강제하지 않으며, host가 해당 action을
  실행하기 전에 verdict를 소비해야 합니다.

| MCP interface | 책임 |
|---|---|
| `brain_context` | optional entity를 binding하고 recall을 routing한 뒤 optional proposed-action verdict 반환 |
| `brain_remember` | 사건, 사실, 규칙, exact state를 담당 store에 기록 |
| `brain_upsert_entity` | stable identity와 alias 생성 또는 resolve |
| `brain_add_relation` | 기존 entity 사이에 typed edge 추가 |
| `brain_checkpoint` | handoff를 저장하고 consolidation candidate 표시 |
| `brain_consolidation_preview` | event promotion을 적용하지 않고 검토 |
| `brain_supersede` | 이전 row와 source link를 보존하며 오래된 사실을 새 version으로 교체 |
| `brain_check_action` | 제안된 행동 하나를 allow, warn, block으로 deterministic 판정하는 optional downstream control |
| `brain-ai://status` | runtime config, component count, latest checkpoint 조회 |
| `brain-ai://ontology` | 검증된 component/channel schema 조회 |

Server는 임의 command execution을 의도적으로 제공하지 않습니다.
`brain_check_action`은 행동 허용 여부를 판정하고, 실제 실행은 host agent나
workflow engine이 담당합니다. 명시적인 fallback command는 operator가 process
boundary를 통제하는 local `brain-ai sequence --entity ...` CLI에서 계속 사용할 수
있습니다.

## Host가 소유하는 integration pattern

연결하는 host는 다음 loop를 닫을 수 있지만 server가 이를 자동 schedule하거나
실행하지는 않습니다.

1. User query와 알고 있는 entity로 `brain_context`를 호출합니다. Control decision이
   필요할 때만 proposed action을 포함합니다.
2. Host 자체 context budget 안에서 관련 record를 선택해 executor에 주입합니다.
   Recall은 component별 record limit을 적용할 뿐 global token-safe working-context
   budget이 아닙니다.
3. Action을 검사했다면 `gate.allowed = false`를 참고 문구가 아니라 중단 조건으로
   처리합니다.
4. Model 추정값보다 `IPS`의 exact value를 우선한 뒤 허용된 action을 host에서
   실행합니다.
5. 선택한 outcome을 episodic event로 명시적으로 기록하거나 exact state를
   갱신하고, handoff가 필요할 때 checkpoint를 만듭니다.
6. Consolidation candidate는 local에서 검토하고 승인 후 적용합니다.

이것은 shipped autonomous loop가 아니라 host integration pattern이며 host model의
conversation history를 대체하지 않습니다. Framework session store가 chat
transcript를 계속 소유하고 host가 Brain-AI의 differentiated operational memory에
기록할 내용을 선택해야 합니다. Action policy는 host가 enforcement boundary를
배선하기 전까지 advisory입니다.

## Integration 강도를 정직하게 선택하기

| 단계 | 연결하는 것 | 얻는 것 |
|---|---|---|
| 진단 | `brain-ai tour`, `run`, `status`를 수동 실행 | mapping이 내 failure에 맞는지 확인 |
| advisory memory | MCP를 연결하고 memory tool을 명시적으로 호출 | scoped recall candidate, exact state, 명시적 write, audit; context 선택과 tool 사용은 host에 의존 |
| advisory control | proposed action을 `brain_context`에 전달하거나 `brain_check_action` 호출 | host가 소비할 수 있는 deterministic verdict |
| enforced control | 지원되는 local command를 `brain-ai harness`로 통과시키거나 host pre-action hook이 `brain_check_action`을 소비 | 배선된 boundary에서 block verdict가 실제 중단 조건이 됨 |

MCP 연결만으로는 tool이 보일 뿐 memory 사용이나 control enforcement가 보장되지
않습니다. Server instruction은 client의 tool 선택을 돕지만 실제 호출, 올바른
record 선택, 관련 없는 모든 host tool call의 gate 통과를 보장하지 못합니다.
Production integration은 host boundary에서 이를 강제해야 합니다.

Advisory integration에는 다음과 같은 instruction을 추가합니다.

```text
세션을 넘는 작업에서는 active entity로 brain_context를 호출하고 host context에
필요한 record만 선택한다. 변경 action 전에는 proposed action을 포함하고
gate.allowed가 false이면 중단한다. 추정값보다 IPS exact state를 우선한다. 작업
후 선택한 changed state나 event를 명시적으로 기록하고 handoff가 필요할 때
checkpoint를 만든다.
```

## 현재 경계

현재 public MCP interface는 local-first single-user alpha입니다. Access control,
automatic Claude Code/Codex/provider transcript ingestion, token-budgeted working-context
assembly·injection, autonomous lifecycle scheduling, conflict-triggered supersession,
checkpoint consume/resume, compact/split transform, physical archive 이동이나 verified
deletion, encryption at rest, distributed store migration, concurrent-writer coordination,
framework-specific automatic hook wiring은 아직 포함하지 않습니다. 이는 host의
책임이거나 production service의 release gate로 남아 있습니다.
