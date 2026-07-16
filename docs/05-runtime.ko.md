# 설치 가능한 memory-management layer와 optional control bridge

공개 저장소에는 memory component contract를 실제로 실행하는 local-first,
provider-neutral implementation이 포함됩니다. 기존 Markdown memory를 검토해
project별로 저장하고, MCP host에 연결하며, session 사이의 handoff를 이어갈 수
있습니다. Hosted multi-tenant service가 아니며 provider transcript를 자동으로
수집하지 않습니다.

## 설치와 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ".[mcp]"

# 프로젝트 명령이 항상 같은 local store를 쓰게 합니다.
cd /path/to/your/project
export PROJECT_ROOT="$PWD"
export BRAIN_AI_HOME="$PROJECT_ROOT/.brain-ai"
brain-ai status
```

기본 runtime은 `./.brain-ai/`에만 기록합니다.

| 경로 | 역할 |
|---|---|
| `config.json` | adapter와 observer 설정 |
| `events.jsonl` | native runtime API가 기록한 append-only event |
| `state.sqlite3` | import한 episode, entity, relation, typed memory, exact state, lifecycle record, import ledger/batch |
| `audit.jsonl` | PFC routing, gate, harness, lifecycle trace |
| `checkpoints.jsonl` | 명시적 session checkpoint |
| `workflows/` | 저장된 Markdown audit/review, apply receipt, lock, host config backup |

위와 같이 `BRAIN_AI_HOME`을 한 번 고정하거나 모든 subcommand 앞에 `--home`을
넣어 audit한 store와 연결한 store가 달라지지 않게 합니다. `.brain-ai/`
아래는 일반 local SQLite·JSON·JSONL 파일이며 패키지가 암호화하지
않습니다. 공개 repository에 commit하지 말고, 접근 권한과 backup을
기록의 민감도에 맞게 관리하세요.

## Package가 소유하는 경계

| 경계 | 구현된 책임 |
|---|---|
| memory-management kernel | episode, knowledge, procedural rule, exact state의 명시적 write; entity/relation binding; component별 recall candidate; lifecycle decision record; promotion preview/apply; supersession; checkpoint; audit |
| optional downstream control bridge | 명시적 proposed-action string에 대한 deterministic verdict와 그 verdict를 소비하는 local CLI command/fallback harness |
| integrating host | session에서 event 선택, 자체 token budget에 맞춘 model context 조립·주입, lifecycle 호출 schedule, 선택한 outcome을 event나 state로 기록, MCP verdict 강제, retention과 물리 삭제 |

Memory kernel을 사용하기 위해 Brain-AI가 command를 실행할 필요는 없습니다. 반대로
`run`이나 MCP가 반환한 gate verdict는 host 또는 bundled CLI harness가 소비하기
전까지 enforcement가 아닙니다. Procedural rule의 저장·recall은 kernel 동작이고,
그 rule로 executor를 중단시키는 것은 control bridge의 동작입니다.

## 기존 Markdown memory file 도입하기

도입 workflow는 관찰, 사람의 판단, mutation을 분리합니다.

```text
MEMORY.md -> audit -> review -> apply -> typed, entity-scoped store
                         \-> rollback (logical undo)
```

먼저 audit합니다. 가져온 record가 다른 project scope로 새지 않도록 entity는
필수입니다.

```bash
brain-ai audit "$PROJECT_ROOT/.claude/MEMORY.md" --entity Atlas
# path를 생략하면 ./.claude/MEMORY.md, ./MEMORY.md 순서로 찾습니다.
```

`audit`은 최대 2 MiB, 한 줄 100 kB인 regular UTF-8 Markdown file 하나를 읽고 source hash와 line span을
기록합니다. Heading에 근거한 import candidate, normalization 후 완전히 같은
duplicate, 같은 명시적 `key: value` key에 서로 다른 literal value가 있는 경우를
보고합니다. Markdown을 render하거나 link·HTML을 실행하지 않으며 transcript를
수집하지 않습니다. 어느 문장이 참인지, 어느 값이 현재 값인지도 추론하지
않습니다. Source file과 typed memory record는 바뀌지 않습니다. 기본적으로 audit
plan만 `.brain-ai/workflows/audits/` 아래에 저장하며, runtime도 초기화하지 않는
순수 preview에는 `--no-save`를 사용합니다. Front matter, fenced code, HTML
comment, block quote는 import candidate에서 제외합니다. Default discovery는
symlink path component를 거부하고 선택한 project root 밖을 검색하지 않습니다.

결정을 저장하기 전에 생성된 item ID를 확인합니다.

```bash
brain-ai review audit_0123456789abcdef
```

Choice가 없는 review는 read-only입니다. 실제로 가져올 결정만 저장합니다.

```bash
brain-ai review audit_0123456789abcdef --approve-ready
brain-ai review audit_0123456789abcdef \
  --set item_a1b2c3d4e5f60708=state \
  --set item_b1c2d3e4f5061728=episodic \
  --rule 'item_c1d2e3f405162738=deploy\s+production' --rule-effect block \
  --supersede item_d1e2f30415263748=mem_1234abcd5678
```

`--approve-ready`는 모호하지 않은 semantic/episodic suggestion만 승인하고 exact
duplicate candidate는 `skip`으로 표시합니다. `needs_review` entry는 unresolved로
남습니다. 명시적 `--set` action은 `semantic`, `episodic`, `state`, `skip`입니다.
State decision에는 명시적인 key/value entry가 필요하고, rule에는 operator가
제공한 regex와 effect가 필요하며, supersession에는 active semantic record ID가
필요합니다. Unresolved entry는 import하지 않습니다. Review 저장은 Markdown
source나 memory record를 바꾸지 않습니다.
Terminal의 human display는 긴 entry text를 줄여 보여줍니다. 승인 전 전체 내용은
`--json` 또는 표시된 source line range에서 확인하세요. Project-scoped
supersession은 같은 project에 이미 연결된 fact만 허용하며 global memory나 다른
project의 fact를 바꾸지 않습니다.

Review를 확인한 뒤 저장된 decision만 apply합니다.

```bash
brain-ai apply review_0123456789abcdef --yes
# 대응하는 audit ID도 사용할 수 있으며 가장 최근에 저장한 review를 선택합니다.
```

`apply`는 explicit non-`skip` decision만 하나의 SQLite transaction으로
가져오고 reviewed entity에 binding합니다. Source path, line range, fragment hash,
source hash도 provenance로 저장합니다. Source `MEMORY.md`를 rewrite, compact,
delete하지 않습니다. 완료된 같은 review를 다시 apply하면 source가 나중에
이동하거나 바뀌었더라도 import를 반복하지 않고 `already_applied`를 반환합니다.
이 경우 receipt의 `source_file_changed`가 `true`가 됩니다.

Workflow에는 optimistic conflict guard가 있습니다. Review는 audit한 source
SHA-256과 typed store의 logical revision에 묶입니다. Audit 후 Markdown이
변경되거나, review 후 store가 변경되거나, supersession target이 바뀌거나,
rollback이 이후 memory 작업을 덮어쓸 수 있으면 CLI는 operation을 거부하고 exit
status **3**을 반환합니다. 현재 상태로 `audit`과 `review`를 다시 실행하세요.
일반적인 usage/validation error의 exit status는 2입니다.

적용한 batch는 audit evidence를 유지하면서 논리적으로 되돌릴 수 있습니다.

```bash
brain-ai rollback batch_0123456789ab --yes
# review_0123456789abcdef 같은 review ID도 사용할 수 있습니다.
```

Rollback은 batch가 새로 만든 semantic row를 archive하고, 기존 fact에 batch가
추가한 entity link를 제거하며, rule을 disable하고 episode를 rolled back으로
표시합니다. 이전 exact state와 supersede된 fact도 해당하면 복원합니다.
`MEMORY.md`나 ledger를 지우지 않고 물리 삭제를 주장하지 않습니다. Store가 해당
batch의 post-apply revision과 여전히 같을 때만 허용됩니다. 이후 applied batch가
logical revision을 바꾸지 않은 채 같은 target을 재사용했다면 dependency guard가
그 이후 batch를 먼저 rollback하도록 요구합니다.

Rollback 뒤에는 같은 source를 새로 audit·review하여 다시 import할 수 있습니다.
Ledger에는 rolled-back attempt와 새 active attempt가 모두 남습니다.

모든 workflow command는 machine-readable plan과 receipt를 위한 `--json`을
지원합니다.

## Project-scoped MCP host 연결하기

Connection command는 기본적으로 검토 가능한 host config diff만 보여줍니다.
`--apply`가 있어야 host config를 변경합니다. Entity는 같은
`BRAIN_AI_HOME`에 먼저 있어야 합니다. Adoption `apply`가 성공하면
자동으로 생기며, 그 과정을 생략했다면 연결 전에 한 번 생성합니다.

```bash
brain-ai entity add --name Atlas --type project
```

전체 과정에서 같은 project root와 runtime home을 사용합니다.

```bash
brain-ai connect codex --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai connect codex --entity Atlas --project-root "$PROJECT_ROOT" --apply

brain-ai connect claude-code --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai connect claude-code --entity Atlas --project-root "$PROJECT_ROOT" --apply
```

Project scope는 Codex의 `.codex/config.toml`에 managed block을, Claude Code의
`.mcp.json`에 managed `brain-ai-memory` server를 기록합니다. 생성되는 server
command에는 현재 Python interpreter와 runtime home의 absolute path, `--entity
Atlas`가 들어가며, 이 entity가 MCP server의 default scope가 됩니다. 이 경로는
machine-local이므로 project config를 commit하기 전에 확인해야 합니다.
`connect --apply`에는 기존 entity가 필요하고,
충돌하는 unmanaged setting은 덮어쓰지 않습니다. 비어 있지 않은 config를 바꿀
때는 private backup도 저장합니다. Preview는 managed `brain-ai-memory` entry의
sanitize된 view만 보여줍니다. 예상하지 않은 environment data는 redact하고 관계없는
host config는 출력하지 않습니다. Project config는
`brain-ai doctor --host codex --project-root "$PROJECT_ROOT"` 또는
`brain-ai doctor --host claude-code --project-root "$PROJECT_ROOT"`로 현재
interpreter와 runtime home을 확인할 수 있습니다. Default entity까지 확인하려면
`--entity Atlas`를 추가합니다.

제거도 같은 preview/apply 분리를 따르며 이 command가 소유한다고 표시한 entry만
제거합니다. 같은 scope와 project config에서 같은 Brain-AI home을 사용해야 하고,
`--entity`를 전달했다면 entity도 일치해야 합니다.

```bash
brain-ai disconnect codex --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai disconnect codex --entity Atlas --project-root "$PROJECT_ROOT" --apply

brain-ai disconnect claude-code --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai disconnect claude-code --entity Atlas --project-root "$PROJECT_ROOT" --apply
```

직접 작성한 MCP entry는 unmanaged입니다. `connect`는 이를 덮어쓰지 않고
`disconnect`도 제거하지 않으므로, 해당 host config나 entry를 만든 client에서 직접
수정하거나 제거하세요.

User-level 설정이 의도된 경우에만 `--scope user`를 전달하세요. 기본값은 project
scope입니다. MCP 연결은 tool을 사용할 수 있게 할 뿐 conversation을 수집하거나,
memory tool을 자동 호출하거나, action verdict를 강제하지 않습니다. Tool
contract는 [한국어 MCP guide](07-mcp-server.ko.md)를 참고하세요.

## Memory-kernel workflow

각 failure mode를 소유하는 store에 기록합니다.

```bash
brain-ai entity add --name Atlas --type project --alias A
brain-ai entity add --name "Atlas 2.1" --type release
brain-ai relation add "Atlas 2.1" belongs_to Atlas
brain-ai remember --type episodic --entity "Atlas 2.1" \
  --text "배포일이 목요일로 변경됐다" --promote semantic
brain-ai remember --type semantic --entity "Atlas 2.1" \
  --text "운영 배포 전에는 review가 필요하다"
brain-ai remember --type state --entity "Atlas 2.1" --key open_reviews --value 3
brain-ai remember --type rule --entity "Atlas 2.1" \
  --pattern 'deploy\s+production' --text "승인 필요"
```

모델이나 agent client가 사용할 audit 가능한 candidate bundle을 만듭니다.

```bash
brain-ai run "최근 변경과 남은 review 개수는?" \
  --entity "Atlas 2.1" --action "deploy production"
```

출력에는 선택한 component, 검색 record, proposed-action verdict, latency가
포함됩니다. 숨겨진 model call은 없습니다. Application이 이 JSON에서 필요한
record를 선택해 Claude, Codex, OpenAI, local model 또는 결정론적 worker에 전달할
수 있습니다. Recall은 component별 record limit만 적용합니다. Global token-safe
working-context를 조립하거나 model에 자동 주입하지 않습니다. Entity scope는 다른
project에 묶인 memory, state, rule이 bundle에 섞이는 것을 막습니다. Entity 없이
기록한 항목은 의도적인 global record이므로 모든 entity scope에서 보입니다.
`brain-ai ontology`는
시작할 때 load한 component/channel schema를 검증하고 보여줍니다.

## Project-scoped handoff와 resume

기존 `checkpoint` command는 global summary 용도로 계속 사용할 수 있습니다. 다른
project와 섞이지 않는 handoff에는 기존 entity를 사용합니다.

```bash
brain-ai handoff --entity Atlas \
  --summary "배포 review 완료" \
  --next "staging 검증 실행" \
  --next "production 승인 요청"

brain-ai resume --entity Atlas
```

`handoff`는 summary, `next_actions`, entity-scoped component count, pending
consolidation candidate가 들어간 `entity-handoff` checkpoint를 append합니다.
`resume`은 정확히 그 entity의 최신 handoff만 반환합니다. 다른 project를 merge하거나
checkpoint를 consume·acknowledge하거나 provider transcript를 재구성하지 않습니다.
첫 handoff 전에는 오류 대신 빈 summary와 action list가 포함된 `status: not_found`를
반환합니다. 두 command 모두 `--json`을 지원합니다.

`--home`을 사용하면 출력되는 `Next:` command에도 absolute home이 유지되므로,
copy-paste한 review·apply·connection command가 다른 store로 바뀌지 않습니다.

## Optional downstream control bridge

Proposed-action gate와 command harness를 거쳐 명시적 local command를 실행합니다.

```bash
brain-ai harness --query "package 검증" --entity "Atlas 2.1" -- \
  python -m unittest discover -s tests
```

성공할 때까지 host가 제공한 fallback을 순서대로 실행할 수도 있습니다.

```bash
brain-ai sequence --query "검증" --entity "Atlas 2.1" \
  --step '["python", "missing_check.py"]' \
  --step '["python", "-m", "unittest", "discover", "-s", "tests"]'
```

첫 단계가 실패해도 model의 판단으로 sequence가 중단되지 않고, code가 다음
fallback을 소비합니다.

이 CLI command들은 자신이 시작한 subprocess만 소유합니다. Claude Code나 Codex
hook을 설치하거나 다른 host tool을 가로채지 않습니다. 두 command 모두
`--entity`를 받아 모든 attempt에 일치하는 entity-bound rule을 적용합니다.
`--entity`를 생략하면 entity-bound rule은 의도적으로 scope 밖이므로, 연결하는
host는 command text 안의 이름에 의존하지 말고 active entity를 전달해야 합니다.

## Consolidation, supersession, lifecycle primitive

Consolidation은 기본적으로 candidate만 보여주며, 명시적 apply가 있을 때만
상태를 바꿉니다.

```bash
brain-ai consolidate
brain-ai consolidate --apply
brain-ai handoff --entity Atlas --summary "배포 review 완료"
```

이들은 서로 독립적인 호출이며, 위 순서는 승격 결과를 entity-scoped handoff에 반영할 때의
권장 session-end flow입니다. Host integration은 보존할 event를 선택할 때
`brain_remember`(또는 `brain-ai remember`)를 호출하고, 승격이 필요할 때
consolidation을 preview·apply하며, handoff가 필요할 때 `brain_checkpoint`
또는 `brain-ai handoff`를 호출해야 합니다. Runtime은 provider transcript에서 이
event를 추론하거나 host 대신 호출을 schedule하지 않습니다.

오래된 semantic memory는 이전 row와 source link를 보존하며 supersede합니다.

```bash
brain-ai supersede mem_old_id --text "배포일은 목요일이다" \
  --entity "Atlas 2.1"
```

`--entity`를 사용하면 old fact가 해당 entity에 이미 연결되어 있어야 하며 그
entity의 binding만 교체합니다. 의도적인 global update일 때만 `--entity`를
생략하세요.

일곱 lifecycle decision 중 하나를 기록하고 active-view status를 갱신합니다.

```bash
brain-ai lifecycle episodic evt_old_id archive --reason "해결 후 downstream에 반영됨"
```

이 command는 물리적 file 변환이 아니라 soft-state management입니다. Episodic
entry의 archive/delete/migration decision은 append-only event를 보존하면서 기본
active view에서 숨기고, semantic archive/delete는 row를 보존한 채 status를
바꿉니다. Compact와 split은 host가 수행할 work만 기록합니다. Knowledge/rule
파생에는 consolidation을 사용하고, 검증된 물리 삭제는 별도 host retention
workflow에서 수행해야 합니다.

## Python에서 사용하기

```python
from brain_ai_memory import BrainAIRuntime

runtime = BrainAIRuntime(".brain-ai")
bundle = runtime.process(
    "최근 배포 계획에서 무엇이 바뀌었나?",
    proposed_action="deploy production",
    entity="Atlas 2.1",
)
if bundle["gate"]["allowed"]:
    context_for_your_executor = bundle["memory"]
```

LLM은 교체 가능한 executor로 남습니다. 지속 cognition은 store, rule, harness
step, checkpoint, audit trail에 존재합니다.

어떤 반환 record가 context budget에 들어갈지는 host가 선택해야 하며, 실행,
outcome 기록, checkpoint resume도 명시적으로 연결해야 합니다. Reference runtime은
model의 live working context를 관리하지 않습니다.

## 공개 reference의 경계

- 기본 BM25 adapter는 투명한 local fallback이며 embedding parity 주장이 아닙니다.
- Recall은 component별 record limit만 적용합니다. Global token/byte budget을
  보장하거나 autonomous paging을 수행하거나 working context를 model에 주입하지
  않습니다.
- observer에는 인증이 없고 기본적으로 localhost에만 bind합니다. network에 직접
  노출하면 안 됩니다. `/api/health`는 process liveness이며 status와 event endpoint는
  count와 최근 audit record를 보여줄 뿐 lifecycle-health 또는 alerting engine이
  아닙니다.
- consolidation이 model에게 rule을 임의 생성하게 하지 않습니다. Rule 승격에는
  명시적 regex와 operator가 전달한 apply flag가 필요합니다.
- Markdown audit은 structural candidate만 보고합니다. Duplicate는 normalization 후
  literal equality이고, possible conflict는 같은 explicit key의 서로 다른 value로
  제한됩니다. 어느 쪽도 truth/freshness 판정이 아닙니다.
- runtime은 Claude Code JSONL, Codex rollout 또는 provider transcript를 자동
  보관·ingest하지 않으며, 이 저장소에는 해당 format adapter가 포함되어
  있지 않습니다. 연결하는 host 또는 custom adapter가 선택한 event를 runtime에
  mapping해야 합니다. 명시적 host privacy·retention policy 없이 원시 trace를
  보존하면 안 되며, 보존한다면 제자리에서 덮어쓰지 말고 evidence로
  유지해야 합니다. Backup·access control·encryption·deletion은 host의 책임입니다.
- Lifecycle command는 state와 active-view decision을 기록합니다. Content compact/split,
  archive file 이동, checkpoint consume·acknowledge, verified physical erasure를 자동
  수행하지 않습니다. Markdown 도입은 reviewed record를 import하지만 source file은
  의도적으로 그대로 둡니다.
- `brain-ai harness`와 `brain-ai sequence`는 optional local helper이며 host 전체를
  자동 enforce하지 않습니다. Entity-bound rule이 필요하면 `--entity`를 전달해야
  합니다. MCP는 action verdict를 반환하지만 관련 없는 host tool call을 가로채지
  않습니다.
- production에는 별도의 access control, encryption, backup, concurrency policy,
  model client, 조직별 hook이 필요합니다.
- `connect`와 `disconnect`는 표시된 Codex/Claude project config만 관리합니다. Hook을
  설치하거나 host가 MCP tool을 호출하게 만들지는 않습니다.
- MCP server는 optional install(`pip install ".[mcp]"`)입니다. [한국어 MCP
  guide](07-mcp-server.ko.md)를 참고하세요.
