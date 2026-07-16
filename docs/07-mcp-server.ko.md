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
/absolute/path/to/brain-ai-memory/.venv/bin/python \
  -m brain_ai_memory.mcp_server \
  --home /absolute/path/to/.brain-ai --entity Atlas
```

기본 transport는 `stdio`입니다. `--entity Atlas`는 server의 default project
scope를 설정합니다. Tool call에 entity가 없으면 `brain_context`,
`brain_check_action`, `brain_remember`, `brain_checkpoint`, `brain_resume`,
`brain_supersede`가 이 값을 사용하며, 명시적 tool argument가 default를
override합니다.

권장 project setup은 먼저 host config diff를 preview하고 `--apply`가 있을 때만
기록합니다. Connection을 apply하기 전에 entity를 만드세요.

```bash
brain-ai entity add --name Atlas --type project

brain-ai connect codex --entity Atlas --project-root .
brain-ai connect codex --entity Atlas --project-root . --apply

# 또는 Claude Code:
brain-ai connect claude-code --entity Atlas --project-root .
brain-ai connect claude-code --entity Atlas --project-root . --apply
```

기본값은 project scope입니다. Command는 `.codex/config.toml`에 표시된 managed
block을 쓰거나 `.mcp.json`에 managed server entry를 쓰며, 현재 Python interpreter,
absolute Brain-AI home, default entity를 포함합니다. 이 machine-local path는
commit 전에 확인해야 합니다. 충돌하는 unmanaged entry는 덮어쓰지 않고, non-empty
config를 변경하기 전 backup을 저장합니다. Preview에는 managed
`brain-ai-memory` entry의 sanitize된 view만 나오며 예상하지 않은 environment
data는 redact하고 관계없는 host config는 출력하지 않습니다.

제거도 preview와 apply를 분리합니다. 이 command가 소유한다고 표시한 entry만 같은
scope와 project config에서 제거하며, 기록된 Brain-AI home이 현재 `--home`과
일치해야 합니다. `--entity`를 전달했다면 entity도 일치해야 합니다.

```bash
brain-ai disconnect codex --entity Atlas --project-root .
brain-ai disconnect codex --entity Atlas --project-root . --apply

brain-ai disconnect claude-code --entity Atlas --project-root .
brain-ai disconnect claude-code --entity Atlas --project-root . --apply
```

User-level connection이 의도된 경우에만 `--scope user`를 사용하세요. 수동 client
설정은 보통 다음과 같습니다.

```json
{
  "mcpServers": {
    "brain-ai-memory": {
      "command": "/absolute/path/to/brain-ai-memory/.venv/bin/python",
      "args": [
        "-m", "brain_ai_memory.mcp_server",
        "--home", "/absolute/path/to/.brain-ai",
        "--entity", "Atlas"
      ]
    }
  }
}
```

Package와 MCP extra를 설치한 environment의 Python interpreter와 home을 모두
absolute path로 지정하세요. 그래야 host가 활성화된 shell에 의존하지 않고 client와
CLI가 같은 state를 사용합니다.

이 설정과 아래의 수동 또는 client-created entry는 의도적으로
**unmanaged**입니다.
`brain-ai connect`는 덮어쓰지 않고 `brain-ai disconnect`도 제거하지 않습니다.
해당 host config나 entry를 만든 client에서 직접 수정·제거하세요. 관리 가능한
소유권과 preview가 필요하면 위의 `brain-ai connect ...` workflow를 사용하세요.

### Codex CLI, desktop, IDE

Codex client들은 MCP 설정을 공유합니다. `~/.codex/config.toml` 또는 trusted
project의 `.codex/config.toml`에 다음을 추가합니다.

```toml
[mcp_servers.brain-ai-memory]
command = "/absolute/path/to/brain-ai-memory/.venv/bin/python"
args = ["-m", "brain_ai_memory.mcp_server", "--home", "/absolute/path/to/.brain-ai", "--entity", "Atlas"]
```

공식 문서는 desktop app, CLI, IDE extension에서 local stdio와 Streamable HTTP
server를 지원한다고 설명합니다. [Codex MCP 공식
문서](https://developers.openai.com/codex/mcp)

### Claude Code

Local stdio server를 등록합니다.

```bash
claude mcp add --transport stdio brain-ai-memory -- \
  /absolute/path/to/brain-ai-memory/.venv/bin/python \
  -m brain_ai_memory.mcp_server \
  --home /absolute/path/to/.brain-ai --entity Atlas
claude mcp get brain-ai-memory
```

협업자와 검토 가능한 `.mcp.json`을 공유하려는 경우에만 `--scope project`를
사용합니다. Claude Code는 project-scoped server를 사용자에게 승인받습니다.
[Claude Code MCP 공식 문서](https://code.claude.com/docs/en/mcp)

격리된 local HTTP 환경에서는 다음처럼 실행할 수 있습니다.

```bash
/absolute/path/to/brain-ai-memory/.venv/bin/python \
  -m brain_ai_memory.mcp_server \
  --transport streamable-http --host 127.0.0.1 --port 8000
```

이 alpha server를 public interface에 bind하면 안 됩니다. 인증, multi-tenancy,
network hardening은 아직 포함하지 않습니다.

## Agent가 호출할 수 있는 기능

Memory interface와 downstream control interface는 contract가 다릅니다.

- `brain_remember`, entity/relation tool, checkpoint, consolidation preview,
  resume, supersession과 `brain_context`의 recall 부분은 memory-management
  kernel을 사용합니다.
- `brain_check_action`과 `brain_context`의 optional `proposed_action`은 control
  verdict를 반환합니다. MCP는 이를 강제하지 않으며, host가 해당 action을
  실행하기 전에 verdict를 소비해야 합니다.

| MCP interface | 책임 |
|---|---|
| `brain_context` | optional entity를 binding하고 recall을 routing한 뒤 optional proposed-action verdict 반환 |
| `brain_remember` | 사건, 사실, 규칙, exact state를 담당 store에 기록 |
| `brain_upsert_entity` | stable identity와 alias 생성 또는 resolve |
| `brain_add_relation` | 기존 entity 사이에 typed edge 추가 |
| `brain_checkpoint` | explicit/default entity가 있으면 `summary`, `next_actions`, scoped count, pending consolidation을 포함한 scoped handoff 저장; 둘 다 없으면 기존 global checkpoint 동작 유지 |
| `brain_resume` | explicit/default entity 하나의 최신 handoff를 반환하며, 첫 handoff 전에는 빈 field와 `status: not_found` 반환 |
| `brain_consolidation_preview` | event promotion을 적용하지 않고 검토 |
| `brain_supersede` | explicit/default entity 하나에서 이미 연결된 fact만 이전 row와 source link를 보존하며 교체 |
| `brain_check_action` | 제안된 행동 하나를 allow, warn, block으로 deterministic 판정하는 optional downstream control |
| `brain-ai://status` | runtime config, component count, latest checkpoint 조회 |
| `brain-ai://ontology` | 검증된 component/channel schema 조회 |

Server는 임의 command execution을 의도적으로 제공하지 않습니다.
`brain_check_action`은 행동 허용 여부를 판정하고, 실제 실행은 host agent나
workflow engine이 담당합니다. 명시적인 fallback command는 operator가 process
boundary를 통제하는 local `brain-ai sequence --entity ...` CLI에서 계속 사용할 수
있습니다.

MCP interface는 Markdown `audit`, `review`, `apply`, `rollback`이나 host config
편집을 노출하지 않습니다. 이들은 local operator가 명시적으로 실행하는 CLI
action입니다. 특히 server 연결은 provider transcript를 scan하거나 기존
`MEMORY.md`를 import하지 않습니다. [한국어 runtime guide](05-runtime.ko.md)의
명시적 hash-guarded workflow를 사용해야 합니다. Source hash 또는 typed store
revision conflict는 자동 merge하지 않고 CLI exit status 3으로 거부합니다.

## Host가 소유하는 integration pattern

연결하는 host는 다음 loop를 닫을 수 있지만 server가 이를 자동 schedule하거나
실행하지는 않습니다.

1. Session 시작 시 이전 handoff가 있을 수 있으면 active entity로 `brain_resume`를
   호출합니다. `status: not_found`는 정상적인 첫 실행 결과로 처리한 뒤 user
   query로 `brain_context`를 호출합니다. Project config에 default
   entity가 있으면 매 call에서 생략할 수 있고, 의도적으로 override할 때만 명시적
   entity를 전달합니다. Control decision이 필요할 때만 proposed action을
   포함합니다.
2. Host 자체 context budget 안에서 관련 record를 선택해 executor에 주입합니다.
   Recall은 component별 record limit을 적용할 뿐 global token-safe working-context
   budget이 아닙니다.
3. Action을 검사했다면 `gate.allowed = false`를 참고 문구가 아니라 중단 조건으로
   처리합니다.
4. Model 추정값보다 `IPS`의 exact value를 우선한 뒤 허용된 action을 host에서
   실행합니다.
5. 선택한 outcome을 episodic event로 명시적으로 기록하거나 exact state를
   갱신합니다. 다음 session이 계속해야 하면 `brain_checkpoint(entity, summary,
   next_actions)`로 scoped handoff를 만듭니다.
6. Consolidation candidate는 local에서 검토하고 승인 후 적용합니다.
   Stale knowledge는 active entity를 명시해 supersede하며 old fact가 해당 scope에
   이미 연결되어 있어야 합니다.

이것은 shipped autonomous loop가 아니라 host integration pattern이며 host model의
conversation history를 대체하지 않습니다. Framework session store가 chat
transcript를 계속 소유하고 host가 Brain-AI의 differentiated operational memory에
기록할 내용을 선택해야 합니다. Action policy는 host가 enforcement boundary를
배선하기 전까지 advisory입니다.

`brain_resume`은 최신 scoped handoff를 읽으며 첫 handoff 전에는 빈 summary와
`next_actions`, `status: not_found`를 반환합니다. Handoff를 consume·acknowledge하거나
여러 entity를 merge하거나 conversation을 재구성하지 않습니다. Server는 충돌하는
prose에서 truth/currentness를 추론하지도 않습니다. Host가 write나 entity-scoped
supersession을 명시적으로 결정해야 합니다. MCP supersession에는 explicit/default
entity가 필요하며 global memory나 다른 entity의 memory를 비활성화할 수 없습니다.

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
필요한 record만 선택하며 이전 handoff가 있을 수 있으면 먼저 brain_resume을
호출한다. 변경 action 전에는 proposed action을 포함하고 gate.allowed가 false이면
중단한다. 추정값보다 IPS exact state를 우선한다. 작업 후 선택한 changed state나
event를 명시적으로 기록하고 handoff가 필요할 때 next_actions가 있는
entity-scoped checkpoint를 만든다.
```

## 현재 경계

현재 public MCP interface는 local-first single-user alpha입니다. Project connection
command는 host MCP config만 기록하며 hook을 설치하거나 host의 tool call을 강제하지
않습니다. Automatic Claude Code/Codex/provider transcript ingestion, token-budgeted
working-context assembly·injection, autonomous lifecycle scheduling, truth inference나
conflict-triggered supersession, checkpoint consume·acknowledge semantics, compact/split
transform, physical archive 이동이나 verified deletion, access control, encryption at
rest, distributed store migration, distributed-writer coordination은 아직 포함하지
않습니다. 이는 host의 책임이거나 production service의 release gate로 남아
있습니다.
