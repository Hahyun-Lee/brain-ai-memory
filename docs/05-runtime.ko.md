# 설치 가능한 memory kernel과 optional control bridge

공개 저장소에는 이제 component contract를 실제로 실행하는 local-first reference
implementation이 포함됩니다. 작고 provider-neutral하게 유지합니다.
실제로 사용할 수 있는 코드지만 drop-in agent memory service나 hosted multi-tenant
system이 아니라 alpha reference kernel입니다.

## 설치와 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

brain-ai tour
brain-ai status
```

기본 runtime은 `./.brain-ai/`에만 기록합니다.

| 경로 | 역할 |
|---|---|
| `config.json` | adapter와 observer 설정 |
| `events.jsonl` | append-only episodic memory(HC) |
| `state.sqlite3` | entity, relation, semantic memory, rule, exact state, lifecycle record |
| `audit.jsonl` | PFC routing, gate, harness, lifecycle trace |
| `checkpoints.jsonl` | 명시적 session checkpoint |

다른 경로를 쓰려면 `BRAIN_AI_HOME` 또는 `--home`을 지정합니다.

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
working-context를 조립하거나 model에 자동 주입하지 않습니다. Entity scope는 이름이
같은 다른 project의 local state나 rule이 bundle에 섞이는 것을 막습니다.
`brain-ai ontology`는
시작할 때 load한 component/channel schema를 검증하고 보여줍니다.

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
brain-ai checkpoint --summary "배포 review 완료"
```

이들은 서로 독립적인 호출이며, 위 순서는 승격 결과를 handoff에 반영할 때의
권장 session-end flow입니다. Host integration은 보존할 event를 선택할 때
`brain_remember`(또는 `brain-ai remember`)를 호출하고, 승격이 필요할 때
consolidation을 preview·apply하며, handoff가 필요할 때 `brain_checkpoint`
(또는 `brain-ai checkpoint`)를 호출해야 합니다. Runtime은 provider transcript에서
이 event를 추론하거나 host 대신 호출을 schedule하지 않습니다.

오래된 semantic memory는 이전 row와 source link를 보존하며 supersede합니다.

```bash
brain-ai supersede mem_old_id --text "배포일은 목요일이다"
```

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
- runtime은 Claude Code JSONL, Codex rollout 또는 provider transcript를 자동
  보관·ingest하지 않으며, 이 저장소에는 해당 format adapter가 포함되어
  있지 않습니다. 연결하는 host 또는 custom adapter가 선택한 event를 runtime에
  mapping해야 합니다. 명시적 host privacy·retention policy 없이 원시 trace를
  보존하면 안 되며, 보존한다면 제자리에서 덮어쓰지 말고 evidence로
  유지해야 합니다. Backup·access control·encryption·deletion은 host의 책임입니다.
- Lifecycle command는 state와 active-view decision을 기록합니다. Content compact/split,
  archive file 이동, retrieval conflict 감지, checkpoint 소비, verified physical
  erasure를 자동 수행하지 않습니다.
- `brain-ai harness`와 `brain-ai sequence`는 optional local helper이며 host 전체를
  자동 enforce하지 않습니다. Entity-bound rule이 필요하면 `--entity`를 전달해야
  합니다. MCP는 action verdict를 반환하지만 관련 없는 host tool call을 가로채지
  않습니다.
- production에는 별도의 access control, encryption, backup, concurrency policy,
  model client, 조직별 hook이 필요합니다.
- MCP server는 optional install(`pip install ".[mcp]"`)입니다. [한국어 MCP
  guide](07-mcp-server.ko.md)를 참고하세요.
