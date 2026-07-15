[English](README.md) | **한국어**

# Brain-AI Memory — 장기 실행 에이전트를 위한 메모리 관리

> **검색은 text를 찾습니다. Memory management는 무엇을 유지하고, 갱신하고,
> 다음 session에 전달할지 결정합니다.**

Brain-AI Memory는 여러 session에 걸쳐 작동하는 agent를 위한 설치 가능하고
local·provider-neutral한 **typed operational memory reference kernel**입니다.
Host가 선택한 record를 episodic event, semantic knowledge, procedural rule,
exact state로 저장하고, stable entity와 source label에 연결하며, scoped recall,
consolidation, supersession, lifecycle decision, handoff primitive를 제공합니다.

기존 model, RAG, vector store, tool, workflow engine은 그대로 사용하세요.
Brain-AI Memory는 retrieval만으로 결정할 수 없는 것, 즉 record의 memory type,
소속, 현재 active 여부, 다음에 어떤 형태가 되어야 하는지를 관리합니다.

Optional **memory-to-action bridge**는 proposed action을 검사하고 host-supplied
fallback sequence를 실행할 수 있습니다. 이 bridge는 managed memory를 소비하지만
memory manager 자체는 아닙니다.

**핵심 문제는 memory continuity입니다.** 모든 오래된 trace를 똑같이 현재로
취급하지 않으면서 다음 session이 올바른 entity, 현재 knowledge, exact state,
적용 가능한 procedure, source, 미해결 작업을 재구성할 수 있어야 합니다.

> **Public alpha의 범위.** 이 package는 structured local store, entity-scoped
> candidate recall bundle, 저장 entry의 lifecycle state, audit, checkpoint를
> 담당합니다. Transcript 수집, 선택과 ingestion, token budget에 맞춘 model
> context 구성, autonomous scheduling, 물리적 보존·삭제, production action
> enforcement는 여전히 host가 담당합니다.

## 1분 만에 managed lifecycle 확인하기

API key, model call, database server, 외부 service가 필요하지 않습니다.

```bash
git clone https://github.com/Hahyun-Lee/brain-ai-memory.git
cd brain-ai-memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

brain-ai tour
```

```text
Brain-AI Memory · managed memory → optional control → durable handoff
1  BIND     Atlas 2.1 → belongs_to → Atlas
2  RECALL   Atlas 2.1 release day is Thursday.
3  STATE    open_reviews = 3
4  GUARD    blocked — release approval is required before production deployment
5  FALLBACK completed after 2 attempts
6  UPDATE   old fact → superseded by → new fact
✓  HANDOFF  checkpoint <id>
```

Memory-management 경로는 `BIND → RECALL/STATE → UPDATE → HANDOFF`입니다.
Entity-scoped episode를 recall하고, stale knowledge를 supersede하고, exact state를
보존하며, 다음 session을 위한 durable checkpoint를 만듭니다. `GUARD → FALLBACK`은
optional memory-to-action bridge를 보여줍니다. 두 경로의 결과는 모두
`./.brain-ai/`에서 확인할 수 있습니다.

## 누가 사용해야 하나?

| 대상 | 적합성 |
|---|---|
| agent·workflow·연구 도구 개발자 | **가장 핵심적인 사용자** — session 간 typed memory, entity scope, source trail, lifecycle, handoff가 필요할 때 |
| 감사 가능한 local agent를 운영하는 팀 | **적합** — memory 변경과 source를 inspect해야 할 때. production hardening은 별도 필요 |
| Codex·Claude Code 고급 사용자 | **적합** — recall, remember, consolidation, checkpoint 호출을 명시적으로 구성할 수 있을 때. built-in memory의 drop-in replacement는 아님 |
| RAG·Obsidian·vector-store 사용자 | **적합** — retrieval은 되지만 scope, staleness, consolidation, session continuity가 해결되지 않을 때 |
| 더 나은 일회성 대화를 원하는 일반 ChatGPT·Claude 사용자 | **직접 사용할 필요 없음** — 이 기술을 사용한 application을 통해 간접적으로 이용 |
| one-shot agent 또는 단순 문서 검색 | **대체로 불필요** — 먼저 context나 RAG로 충분한지 확인 |

Lifecycle 없이 memory만 계속 커지거나, project identity가 섞이거나, stale
fact가 active로 남거나, exact state가 prose 속에 묻히거나, 반복 episode가
knowledge로 바뀌지 않거나, 다음 session이 이전 결정과 source를 복구하지 못할 때
사용합니다. 이것은 agent를 설정하는 사람을 위한 infrastructure이지 일반
소비자용 chat application이 아닙니다.

Codex/Claude의 session resume와 built-in memory도 유용합니다. 그것만으로
문제가 해결된다면 교체하지 마세요. Brain-AI Memory는 operational memory를
provider-neutral하고 typed·inspectable·source-labeled·lifecycle-managed한
상태로 agent나 workflow 사이에 의도적으로 전달해야 하는 더 좁은 경우를 위한
것입니다.

![Graphical abstract: host가 뒤섞인 원시 session evidence에서 일부 record만 선택해 episode, knowledge, relationship, procedure, exact state compartment로 mapping하고 agent는 scoped context를 받으며, 별도의 아래쪽 경로에서는 proposed action만 gate를 거친 뒤 executable sequence가 tool에 도달하는 과정](docs/assets/graphical-abstract.png)

**주 경로:** host-selected evidence → managed memory → scoped context.
**Optional bridge:** proposed action → gate → executable sequence.

## 시스템이 관리하는 것

| Memory-management 책임 | Public alpha가 하는 일 |
|---|---|
| selected evidence | host가 명시적으로 보낸 event만 기록. provider transcript는 host-owned raw evidence로 유지 |
| working-context candidate | entity-scoped, record-count-limited bundle을 재구성하고 host가 자체 token budget 안에 배치 |
| episodic memory | timestamp event와 entity binding을 append-only source에 보존 |
| semantic memory | source가 있는 reusable knowledge를 저장하고 stale fact를 supersession으로 versioning |
| procedural memory | explicit rule을 저장하고 preview·approval 후에만 episode candidate를 승격 |
| exact state | model이 추정하지 않도록 알 수 있는 값을 typed store에 보존 |
| lifecycle과 handoff | consolidation, reconsolidation, logical active/inactive decision, audit, checkpoint primitive를 기록 |

Entity relation, source label, 검증된 component ontology는 이 store들을
가로지릅니다. Runtime은 provider session을 자동 수집하거나, memory를 model
context에 paging하거나, file을 실제로 compact·split하거나, source byte를
물리적으로 삭제하지 **않습니다**. `limit`은 token이 아니라 record 수를
제한합니다. Host integration과 retention의 경계는 아래에 명시합니다.

## Local에서 memory 관리하기

이름이 비슷한 event, fact, value가 다른 scope로 새지 않도록 memory를 project,
release, person 같은 stable entity에 연결합니다.

```bash
brain-ai entity add --name "Atlas" --type project --alias A
brain-ai remember --type episodic --entity Atlas \
  --text "배포일이 목요일로 변경됐다" --promote semantic
brain-ai remember --type state --entity Atlas --key open_reviews --value 3
brain-ai run --entity Atlas \
  "최근 무엇이 바뀌었고 review가 몇 개 남았나?"
brain-ai consolidate          # preview
brain-ai consolidate --apply  # 명시적 승격
brain-ai checkpoint --summary "release review 완료"
```

Runtime은 시작할 때 component ontology를 검증합니다. `brain-ai ontology`로
확인할 수 있으며 canonical schema는
[`schema/brain_components.yaml`](schema/brain_components.yaml)입니다.

## Optional: managed memory를 에이전트에 연결하기

Optional MCP surface를 설치합니다.

```bash
python -m pip install ".[mcp]"
brain-ai-mcp --home /absolute/path/to/.brain-ai
```

MCP client에는 다음과 같은 server 설정을 추가합니다.

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

Codex CLI·desktop·IDE와 Claude Code는 local MCP server를 지원합니다. 구성된
host integration은 scoped recall에 `brain_context`, 선택한 event나 exact state에
`brain_remember`, handoff에 `brain_checkpoint`를 호출합니다. 승격이 필요하면
`brain-ai consolidate`를 별도로 preview하고 apply합니다. 이 호출들은
background에서 자동 실행되지 않습니다.

Public runtime은 provider의 native 대화 transcript를 자동 수집·보관하지 않으며,
이 저장소에는 Claude Code JSONL이나 Codex rollout adapter가 포함되어 있지
않습니다. 이런 trace는 그 자체로 working memory가 아닌 원시 evidence입니다.
연결하는 host 또는 custom adapter가 명시적 privacy·retention policy에 따라 보존
여부와 HC에 mapping할 event를 선택해야 합니다. 원시 trace를 보존한다면
제자리에서 덮어쓰지 말고 evidence로 유지해야 합니다. Backup, access control,
encryption, deletion은 host의 책임입니다.

### Optional memory-to-action enforcement

같은 MCP surface가 `brain_check_action`도 노출하지만 임의 shell execution은
의도적으로 제공하지 않습니다. 허용된 action의 실행은 host 책임입니다. MCP
연결만으로 enforcement가 되지 않으며, host가 `gate.allowed = false`를 실제 중단
조건으로 소비해야 합니다. 결정론적 차단이 필요하면 실행을 `brain-ai harness`로
통과시키거나 verdict를 host pre-action hook에 연결하세요. Entity-bound rule을
적용해야 할 때는 `--entity`를 전달합니다. [Codex·Claude Code
설정과 integration boundary](docs/07-mcp-server.ko.md)를 참고하세요.

## 왜 뇌의 기능 분화에서 착안했나?

인간의 기억과 행동 조절은 하나의 저장소가 아니라 서로 구분되면서 상호작용하는
여러 기능에 의존합니다. Brain-AI Memory는 **뇌 해부학의 복제가 아니라 기능적
분화라는 설계 원리**를 검사 가능한 software responsibility로 번역합니다.
뇌 영역 이름은 기억을 돕는 표지이며 일대일 국재화나 생물학적 simulation
주장이 아닙니다. 비유가 유용하지 않다면 label을 버리고 contract만 사용해도
됩니다. [mapping과 그 한계](docs/01-the-mapping.md)를 함께 공개합니다.

> **근거의 경계.** Runtime test는 package의 일부 동작을 검증하고,
> deterministic ablation은 테스트한 열 가지 lifecycle/control mechanism의
> authored contract만 분리해 검증합니다. 모든 package surface를 ablation했다거나,
> brain inspiration이 더 좋은 LLM 답변의 원인이라거나, 이 시스템이 RAG를
> end-to-end로 능가한다는 증거는 아닙니다. [근거와 한계](#근거-현황)

## Memory-management failure부터 진단하기

여러 세션에 걸쳐 동작하는 코딩, 연구, 운영, 비서 에이전트를 만들고 있으며
다음 중 하나라도 익숙하다면 살펴볼 가치가 있습니다.

- "그 결정을 기록했는데 왜 다음 session이 재구성하지 못하지?"
- "검색된 note는 관련 있지만 이미 supersede됐다."
- "이 event는 다른 project나 entity에 속한다."
- "같은 lesson이 반복됐지만 reusable knowledge가 되지 않았다."
- "exact value가 있는데도 model이 prose에서 추정했다."
- "memory index만 계속 커지고 무엇을 consolidate·archive·retain할지 모른다."

지속 상태가 없는 단일 턴 챗봇에는 이 아키텍처가 필요하지 않을 가능성이
큽니다. 문제가 일반적인 문서 검색뿐인 워크플로에도 필요하지 않습니다. 이미
겪고 있는 실패부터 시작하세요. 전체 아키텍처를 한꺼번에 채택할 필요는 없습니다.

| 관찰한 문제 | 먼저 진단할 대상 | 가장 작은 유효한 변화 |
|---|---|---|
| 확정된 문맥이 사라지거나 잘못된 사건에 연결됨 | 일화 기억(HC) | timestamp가 있는 event/entity binding 추가 |
| 한 project의 memory가 다른 project로 샘 | entity scope와 relation | record를 stable entity에 bind하고 해당 scope 안에서 query |
| 검색 결과는 관련 있지만 오래됨 | 의미 기억(ATL) | freshness를 확인하고 충돌 시 reconsolidation |
| 반복 episode가 reusable knowledge나 procedure가 되지 않음 | consolidation | explicit preview/approval promotion 경로 추가 |
| old fact와 new fact가 동시에 active로 남음 | reconsolidation | old row와 source link를 유지하며 stale record를 supersede |
| 정확히 알 수 있는 수치를 추측함 | 수치 상태(IPS) | 추정 대신 exact store 조회 |
| 항상 로드되는 index가 계속 커짐 | memory lifecycle | bounded index를 유지하고 archive/migration decision을 기록 |
| 다음 session이 이전 결정을 이어가지 못함 | checkpoint와 handoff | scoped summary와 pending lifecycle candidate를 보존 |

이 기능들은 그림을 만들기 위해 고안한 것이 아닙니다. 지속적이고 다중
프로젝트인 에이전트 시스템을 실제 운영하면서 memory, retrieval, lifecycle,
session handoff의 실패를 디버깅하는 과정에서 분리됐습니다. 아래
근거에서는 이 운영 기록을 인과 주장 및 benchmark 주장과 구분합니다.

### Optional downstream failure

Memory의 scope와 current state를 먼저 바로잡은 뒤에는 memory-to-action bridge가
다른 종류의 failure를 다룰 수 있습니다.

| 관찰한 문제 | Bridge component | 가장 작은 유효한 변화 |
|---|---|---|
| recall한 rule이 execution에서 무시됨 | procedural rule consumption(BG) | 저장 rule을 deterministic action check에 연결 |
| fallback sequence가 첫 실패 후 중단됨 | procedural execution(CB) | sequence를 executable harness로 이동 |
| 올바른 memory bundle이 unsafe action으로 이어짐 | routing과 proposed-action gate(PFC/TH) | host execution boundary에서 gate verdict를 소비 |

## 이것이 단순 RAG나 harness가 아니라 memory management인 이유

관련 text를 찾는 일은 필요하지만 memory system 안의 operation 하나일 뿐입니다.
Session을 넘는 더 어려운 질문은 *이 record는 무엇인지, 어디에 속하는지, 아직
current인지, reusable knowledge나 rule이 될 수 있는지, 다음 session에 무엇을
전달해야 하는지*입니다. Brain-AI Memory는 이 decision을 명시적이고 inspectable하게
만듭니다.

| 기존 방법 | 제공하는 것 | Memory management에 여전히 필요한 것 |
|---|---|---|
| long context 또는 memory file | model이 지금 읽을 수 있는 text | type, scope, active version, promotion, retention decision, handoff |
| RAG 또는 vector store | query와 유사한 candidate text | entity binding, freshness, exact state, consolidation, supersession, source/version link |
| entity model, ontology, relational/graph DB | identity와 structured relationship | 어느 record가 episode·knowledge·rule·state로 동작하며 session 간 어떻게 변하는지 |
| hook, guard, harness, retry loop | interception, action policy, sequence execution, 재시도 | 이 mechanism이 소비·생성하는 memory의 ownership과 lifecycle |
| Brain-AI Memory | typed local store, entity scope, active-view recall, explicit promotion/update decision, audit, handoff | raw evidence, model-context assembly, scheduling, physical retention, production policy는 host가 제공 |

따라서 entity와 relation 지원은 core의 일부지만 local identity-and-scope
layer이며, domain ontology reasoner나 production database의 대체제가 아닙니다.
RAG는 semantic retrieval backend로 유지할 수 있고, hook은 이 kernel을 호출할 수
있으며, harness는 procedural memory를 소비할 수 있습니다. 이 mechanism 중 어느
하나도 그 자체로 전체 memory lifecycle을 소유하지 않습니다.

### Optional control bridge

Hook은 attachment point이고, guard는 allow/warn/block decision을 반환하며,
harness는 sequence를 소유하고, loop는 outcome을 다음 attempt에 반영합니다.
Public package는 저장 rule과 host-supplied procedure step이 action에 영향을 줄
수 있도록 작은 guard와 fallback implementation도 포함하지만, 실제 enforcement와
execution은 **memory management의 downstream**이며 host가 결과를 소비해야
합니다. 이것이 project 이름이 Brain-AI Memory인 이유는 아닙니다.

### 기여: 원시 요소 발명이 아닌 구분된 memory contract

Working, episodic, semantic, procedural memory category와 RAG, entity model,
hook, workflow harness, evaluator, compaction은 기존 개념과 기술입니다. 이
저장소의 기여는 failure mode를 뭉개지 않으면서 이들을 연결하는 설치 가능한
contract입니다.

- PFC는 scoped working-memory candidate를 재구성하고, HC는 episode와 relation을
  기록하며, ATL은 source가 있는 reusable knowledge를 저장하고, BG는 procedural
  rule을, IPS는 exact state를 보존합니다.
- CB는 executable procedure를 rule과 분리합니다. 운영 architecture는 이런
  harness를 등록할 수 있지만 public alpha는 현재 sequence registry를 소유하는
  대신 host-supplied fallback step을 받습니다.
- Consolidation은 episode의 knowledge/rule 승격을 preview하며,
  reconsolidation은 stale knowledge를 조용히 덮어쓰는 대신 source가 있는
  superseding version을 만듭니다.
- 저장 entry에는 keep, compact, archive, migrate to knowledge, migrate to rules,
  delete, split 중 하나의 explicit lifecycle decision을 줄 수 있습니다. Alpha는
  host source를 실제로 변환·삭제했다고 가장하지 않고 이 decision과 logical active
  view를 기록합니다.
- Checkpoint는 count, pending consolidation candidate, host-written summary를 다음
  session으로 전달합니다.
- Optional TH/BG/CB action 경로는 core memory 경로와 별도로 test하여 software
  conformance를 memory-quality evidence로 잘못 표시하지 않습니다.

Brain mapping은 functional engineering analogy입니다. 진단에 도움이 되면
유지하고 그렇지 않으면 label을 버리세요. 현재 근거는 실제 운영, 검증한 retrieval
tradeoff, 서로 다른 software contract를 보여주지만 brain inspiration이나 통합
system이 더 단순한 memory system을 end-to-end로 능가함을 보여주지는 않습니다.

## 적용 경로 선택하기

Clean-room public kernel을 실제로 설치할 수 있습니다. Memory failure 하나에서
시작하고 필요한 경우에만 optional action path를 추가하세요.

| 목표 | 시작점 | 첫 성공 기준 |
|---|---|---|
| package를 local에서 확인 | `brain-ai tour` | `.brain-ai/`에서 entity binding, current fact, exact state, update, checkpoint 확인 |
| agent에 typed memory 추가 | [`brain-ai` runtime](docs/05-runtime.ko.md)의 `entity`, `remember`, `run` | 이름이 비슷한 두 project가 각자의 active memory만 반환 |
| 기존 memory file에 lifecycle 추가 | `consolidate`, `supersede`, `lifecycle`, `checkpoint` | promotion을 preview하고 stale knowledge를 versioning하며 handoff 기록 |
| Obsidian / Smart Connections 연결 | [semantic adapter](docs/06-adapters-and-observer.ko.md) | v1·v2 response를 처리하고 v2 hybrid ranking을 BM25 중복 없이 보존 |
| local state와 handoff inspect | [clean-room observer](docs/06-adapters-and-observer.ko.md#read-only-reference-observer) | localhost에서 store count, recent audit event, latest checkpoint 확인 |
| Codex·Claude Code·다른 host에 scoped memory 전달 | [한국어 MCP server](docs/07-mcp-server.ko.md) | host가 `brain_context`를 명시적으로 호출하고 selected record를 주입하며 outcome·checkpoint 기록 |
| action 시점에 저장 procedure enforce | `brain-ai harness --entity ...` 또는 [behavioral guard](templates/hooks/behavioral-guard.py) | entity-scoped unsafe pattern이 실제 execution boundary에서 차단 |
| host-supplied fallback sequence 실행 | `brain-ai sequence --entity ...` | 성공·차단·소진까지 attempt가 계속되고 trace가 audit됨 |
| index가 두 번째 database가 되는 것 방지 | [memory skeleton](templates/memory/MEMORY.skeleton.md) | topic당 한 줄짜리 link만 항상 로드됨 |
| 무엇을 유지하거나 이동할지 결정 | [seven-operation helper](templates/memory/7-op-decision.md) | 모든 review entry가 하나의 recorded decision을 받고 host transformation 경계가 명확함 |
| 채택 전에 아키텍처 평가 | [mapping](docs/01-the-mapping.md)과 [evidence](evidence/README.md) | 실제 failure를 component에 mapping하거나 맞지 않는 지점을 식별 |

Hook은 Python 표준 라이브러리만으로 self-test할 수 있습니다.

```bash
python3 templates/hooks/behavioral-guard.py --selftest
python3 templates/hooks/self-check-trigger.py --selftest
```

## Memory architecture 동작 방식

Canonical map은 일곱 component의 **cognitive architecture**입니다. 다섯 memory
role(PFC working/executive, HC episodic, ATL semantic, BG procedural-rule, CB
procedural-execution)과 두 supporting control/computation role(TH gating, IPS exact
numerical state)로 구성됩니다. Consolidation과 reconsolidation은 extra component가
아니라 transfer channel입니다. Public product는 typed memory와 lifecycle을 주로
다루므로 memory-management kernel이며, supporting control surface가 이를 harness
library로 바꾸지는 않습니다. Neuroscience 근거와 한계는 [상세
mapping](docs/01-the-mapping.md)을 참고하세요.

| Layer | Component | Public package의 책임 | 진단하려는 실패 |
|---|---|---|---|
| memory role | PFC | query를 candidate store로 routing하고 scoped working-memory candidate 재구성 | 잘못된 store 또는 entity scope 선택 |
| memory role | HC | episodic event, stable entity, alias, relation, binding | event 누락 또는 잘못된 context에 binding |
| memory role | ATL | source와 superseding version이 있는 active semantic knowledge | retrieval은 관련 있지만 stale이거나 source가 잘못됨 |
| memory role | BG | stored procedural rule과 승인된 episode-to-rule promotion | reusable rule을 기록·선택하지 못함 |
| memory role | CB | executable procedure representation. alpha는 explicit host-supplied step을 실행 | procedure가 prose로 남거나 fallback 완료 전에 중단 |
| supporting computation | IPS | entity-scoped exact numerical state | 알 수 있는 수치를 prose에서 추측 |
| supporting control | TH | public runtime에서 execution 전 host-proposed action 검사 | unsafe proposed action이 tool boundary에 도달 |
| lifecycle channel | consolidation | episode → knowledge/rule promotion을 preview하고 명시적으로 apply | 반복 experience가 reusable memory가 되지 않음 |
| lifecycle channel | reconsolidation | source가 있는 superseding semantic version 생성 | stale·current knowledge가 동시에 active로 남음 |

Mapping에서 TH inspiration은 더 넓은 input gating입니다. Clean-room runtime은
실제로 test하는 더 좁고 관찰 가능한 형태, 즉 proposed-action check를 구현합니다.
Model의 전체 prompt나 provider input을 filter한다고 주장하지 않습니다.

### Host-owned closed loop

Public package는 kernel operation을 제공하지만 이 loop를 background에서 실행하지
않습니다. 완전한 host integration은 다음 단계를 명시적으로 수행합니다.

1. **선택:** native transcript를 host-owned evidence로 보존하고 durable
   operational memory로 만들 record만 선택합니다.
2. **Bind·write:** memory type, entity, source label, 필요한 exact value와 함께
   `brain_remember`/`brain-ai remember`를 호출합니다.
3. **Recall·assemble:** `brain_context`/`brain-ai run`을 호출하고 host가 반환된
   candidate bundle을 자체 token budget과 model context에 맞춥니다.
4. **행동:** host policy로 실행하고 필요하면 entity-scoped gate 또는
   `harness`/`sequence` bridge를 소비합니다.
5. **Outcome 기록:** 선택한 결과를 episode나 exact state로 기록합니다.
6. **Lifecycle 검토:** promotion preview/apply, stale knowledge supersession,
   archive·split·compact·migration·logical-delete decision을 기록합니다.
7. **Handoff:** checkpoint를 기록하고 다음 session이 이를 소비하게 합니다.

현재 package는 호출되는 primitive와 audit trail을 구현하지만 automatic transcript
adapter, scheduler, token-budget assembler, physical archive/delete engine,
checkpoint acknowledgement protocol은 구현하지 않습니다. 따라서 MCP server를
연결한 것만으로 loop가 닫히지 않습니다. Raw trace를 찾는 것, episode를 선택하는
것, candidate memory를 assemble하는 것, consolidate하는 것은 서로 다른
operation입니다. Representation과 handoff contract는 [memory
lifecycle](docs/02-memory-lifecycle.ko.md)을 참고하세요.

![Memory lifecycle: recall, 세션 중 tagging, consolidation, 일곱 가지 lifecycle operation](docs/assets/memory-lifecycle.svg)

## 근거 현황

Brain-AI Memory는 운영 노출, primary memory-management evaluation, supporting
software conformance, 아직 없는 evidence라는 네 가지 근거 계층을 구분합니다.
이들은 서로 다른 질문에 답하며 하나의 headline으로 합치면 안 됩니다.

| 질문 | 현재 근거 |
|---|---|
| 실제로 구현해 사용했는가? | **예. 2026-04-20부터 13개 project memory index에서 운영** |
| 충분한 운영 노출이 있었는가? | **예. 2026-06-10부터 2026-07-14까지 계측 세션 419개, 63.6M tokens** |
| 내부 pointer에서 semantic retrieval이 live grep control보다 나은가? | **시사적 결과 있음. HIT@10 69.0% → 88.8%, n=116** |
| 동일 budget에서 graph augmentation이 semantic store를 개선하는가? | **시사적 결과 있음. HIT@10 86.2% → 91.9%, n=690 sources** |
| 공개 benchmark에서 stack-aligned retrieval을 비교했는가? | **예. LoCoMo retrieval HIT@10: GTE 62.1%, BM25 57.0%, graph-lite 51.9%; answerable questions n=1,531** |
| compact pointer index가 full append-only entry보다 더 많이 들어가는가? | **예. 결정론적 capacity simulation** |
| 단순 compact pointer가 공개 데이터에서 retrieval quality를 보존하는가? | **아니요. 현재 keyword pointer는 recall과 size를 교환함** |
| lifecycle이 실제 LLM agent의 answer accuracy를 개선하는가? | **아직 측정하지 않음** |
| 전체 아키텍처가 RAG, long context 또는 다른 memory system보다 나은가? | **아직 측정하지 않음** |
| latency, token cost, conflict resolution, abstention이 개선되는가? | **아직 측정하지 않음** |
| single-owner multi-project deployment가 얼마나 일반화되는가? | **알 수 없음. 다기관 반복 검증 없음** |
| Ablation한 열 가지 memory/lifecycle·optional-control mechanism이 작성된 contract를 실행하는가? | **Supporting conformance만 해당. all-ten condition 20/20, flat retrieval control 1/20. Flat control도 memory query 6/6에서 예상 top text를 찾음** |

### 실제 운영 배포

2026-07-14 sanitized snapshot은 약 12주간의 시스템 진화를 포함합니다. 실제
운영 환경에는 project memory index 13개, memory file 134개, semantic note
783개, decision/issue ledger record 455개, 계측된 policy event 3,286개가
있습니다. 예약된 recall snapshot 9회에서 각각 18~21개의 stable probe를
실행했습니다. Any-store pass rate는 100%였지만 vector-only probe rate는
33.3%에서 100% 사이로 변동했습니다.

이 수치는 실제 사용, 규모, 모니터링, 반복된 개입을 보여줍니다. 그러나 memory가
419개 session을 유발했다거나, 모든 policy event가 harm을 막았다거나, curated
probe 성공이 end-to-end answer quality와 같다는 뜻은 아닙니다.
[운영 근거와 한계](evidence/operational-evidence.md)를 읽거나
[machine-readable aggregate snapshot](evidence/operational-snapshot-2026-07-14.json)을
직접 확인할 수 있습니다.

### 내부 및 stack-aligned retrieval 평가

운영 stack의 component를 사용해 같은 corpus에서 두 가지 비교를 수행했습니다.

| 평가 | Control | Test condition | 결과 |
|---|---:|---:|---|
| auto-memory pointer retrieval, n=116 | grep HIT@10 69.0% | production embedding HIT@10 88.8% | grep miss 36개 중 25개 복구 |
| semantic-note retrieval, n=690 sources | embedding HIT@10 86.2%, recall@10 41.0% | equal-budget graph hybrid HIT@10 91.9%, recall@10 48.8% | HIT +5.7 pp, recall +7.8 pp |

이것은 독립적인 공개 benchmark가 아니라 같은 시스템 안에서의 유용한 A/B
signal입니다. Pointer gold set은 양쪽 조건의 절대 점수를 부풀릴 수 있고,
graph 평가는 relevance label과 같은 relationship family를 사용합니다. 투명성을
위해 aggregate result만 공개하며 private source record는 의도적으로 제외했습니다.

이전의 stack-aligned 평가에서는 공개 LoCoMo 10개 sample의 answerable question
1,531개 전체에 대해 retrieval을 실행했습니다. HIT@10에서 parallel/legacy
768-dimensional GTE index는 62.12%, BM25는 56.96%, lightweight graph-PPR은
51.93%였습니다. 이것은 긍정 결과와 부정 결과를 함께 보여줍니다. k=10에서는
embedding baseline이 도움이 됐지만 해당 graph approximation은 그렇지
않았습니다. 측정 대상은 gold-evidence retrieval이지 answer accuracy가 아니며,
raw per-item bundle은 private evaluation environment에서 아직 clean-room 공개되지
않았습니다.

### 공개 데이터 retrieval pilot

정제된 LongMemEval-S 500문항 전체에서 동일한 top-3 budget으로 최근 session,
full-session BM25, compact keyword pointer를 비교한 retrieval-only pilot을
실행했습니다.

![LongMemEval-S retrieval pilot: compact keyword pointer는 indexed source text를 줄이지만 answer-session recall도 잃음](docs/assets/benchmark-compression-recall.png)

| 조건 | Answer-session recall@3 | 평균 indexed source text |
|---|---:|---:|
| 가장 최근 3개 session | 7.5% | search index 없음 |
| full-session BM25 | **86.1%** | 493,948 chars |
| 48-keyword pointer BM25 | 66.2% | 17,691 chars |
| 96-keyword pointer BM25 | 71.0% | 34,368 chars |

96-keyword pointer는 indexed source text를 93.0% 줄였지만 recall은 15.0
percentage points 낮아졌습니다. 단순 keyword compression만으로는 충분하지
않다는 유용한 negative result입니다. Reader LLM을 사용하지 않았으므로 QA,
reasoning, 전체 아키텍처 성능을 주장하지 않습니다.
[method, 전체 ablation, manifest, raw retrieval record](benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md)를
확인할 수 있습니다.

### Capacity simulation: LLM benchmark가 아닙니다

![고정 index budget의 capacity simulation: append-only와 one-line-pointer lifecycle memory 비교](docs/assets/recall-under-budget.svg)

[Capacity simulation](evidence/lifecycle_under_budget.py)은 고정 character budget에서
exact string lookup을 수행합니다. 공개된 default에서는 full append-only entry는
session 5에서, one-line pointer는 session 21에서 처음 recall이 감소합니다. 이는
storage-budget mechanism을 보여줄 뿐 semantic retrieval, reasoning quality,
real-agent performance를 측정하지 않습니다.

    python3 evidence/lifecycle_under_budget.py

Falsifier와 한계는 [evidence note](evidence/README.md)를 참고하세요. Release-grade
외부 검증을 위한 사전 등록 비교 protocol은 [benchmarks/](benchmarks/README.md)에
있습니다. Controlled reader-model protocol이 실행되기 전에는 end-to-end QA
result table을 추가하지 않습니다.

### Secondary: memory-to-action contract verification

Memory-performance scoreboard와 별도로 설치 가능한 package를 20개의
deterministic contract case와 21개 condition에서 평가했습니다. 조건은 flat
retrieval control, 10개의 cumulative addition, 10개의 leave-one-out
removal입니다. LLM, 외부 API, 비공개 data, 외부 judge는 사용하지 않았습니다.

![누적 mechanism-contract ablation: flat control은 작성된 contract 20개 중 1개, 테스트한 열 가지 mechanism을 모두 켠 condition은 20개 모두 충족](docs/assets/component-ablation.png)

All-ten condition은 작성된 contract 20/20을, flat control은 1/20을
충족했습니다. 중요한 점은 flat control도 memory query 6/6에서 예상 top text를
모두 찾았다는 것입니다. 낮은 총점은 text retrieval 실패가 아니라 typed routing,
exact state, gate, fallback sequence, lifecycle contract의 부재를 반영합니다. 각
cumulative addition은 지정된 case를 복구했고, 각 leave-one-out removal은 해당
case를 실패하게 했습니다.

이는 테스트한 열 가지 software responsibility가 서로 구분되고 실행 가능함을
검증합니다. Answer quality, autonomous lifecycle management, RAG 대비 우월성을
측정하지는 않습니다. [Report, raw record 420개, summary,
manifest](benchmarks/pilots/component-ablation-20260715/README.md)를 확인하세요.

## 다음 외부 검증

가장 중요한 미확보 evidence는 controlled end-to-end memory-management QA
비교입니다. 같은 reader와 budget에서 agent가 더 안정적으로 retain, retrieve,
update, scope, abstain, resume할 수 있는지를 확인해야 합니다. 다음 release-grade
run은 reader model, prompt, context budget, dataset split, scoring procedure를
고정하고 다음 조건을 비교합니다.

1. external memory 없음
2. append-only 또는 full-history memory
3. summarization/compaction
4. standard retrieval baseline
5. Brain-AI lifecycle reference implementation

주 benchmark는 information extraction, multi-session reasoning, knowledge
update, temporal reasoning, abstention을 검사하는
[LongMemEval](https://github.com/xiaowu0162/LongMemEval)입니다. 후속 평가에서는
retrieval, test-time learning, long-range understanding, conflict resolution을
위해 [MemoryAgentBench](https://github.com/HUST-AI-HYZ/MemoryAgentBench)를
사용할 예정입니다. 더 무거운 workflow/environment memory 평가는
[LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2)에 남겨 둡니다.

완전한 per-item output, cost와 latency report, controlled baseline,
reproducible run manifest 없이는 top-line performance claim을 추가하지 않습니다.

## Capability roadmap

Public alpha는 작동하는 kernel이지만 아직 autonomous closed-loop memory service는
아닙니다. 구현 순서는 다음과 같습니다.

1. session/message identity, event time, outcome, evidence URI/hash,
   deduplication을 포함한 provider-neutral ingestion envelope 추가
2. private provider log를 core에 포함하지 않는 opt-in transcript adapter 하나 제공
3. 실제 token/byte budget 안에서 candidate memory를 assemble하고 각 record의
   선택 이유 공개
4. checkpoint consume/acknowledge/resume와 lifecycle backlog·health metric 추가
5. explicit compact, split, archive, verified-delete adapter를 제공한 뒤 완전한 host
   loop를 end-to-end로 test

Production multi-writer locking, authentication, domain-ontology reasoning,
entity merge/versioning은 이후 hardening 과제입니다. 이들이 구현·검증되기 전의
정확한 product boundary는 완전 autonomous memory platform이 아니라 **설치 가능한
memory-management reference kernel**입니다.

## 기존 연구와의 관계

- **CoALA** — *Cognitive Architectures for Language Agents*
  ([arXiv:2309.02427](https://arxiv.org/abs/2309.02427))는 이 저장소와 상당 부분
  공유하는 working, episodic, semantic, procedural taxonomy를 제공합니다.
- **MemGPT** ([arXiv:2310.08560](https://arxiv.org/abs/2310.08560))는 제한된 main
  context와 external context 사이의 self-directed paging을 제공합니다. 이
  저장소에는 아직 autonomous paging이 없습니다.
- **Generative Agents**
  ([DOI](https://doi.org/10.1145/3586183.3606763))는 여기의 consolidation
  channel과 유사한 memory stream 및 reflection process를 사용합니다.
- **Complementary Learning Systems**
  ([DOI](https://doi.org/10.1037/0033-295X.102.3.419))와 working-memory 연구는
  빠른 episodic / 느린 semantic 구분에 동기를 제공합니다.

이 비교는 정성적입니다. 실제 운영 시스템, 내부 A/B 결과, 공개 retrieval
pilot만으로 전체 아키텍처가 이 시스템들보다 우월하다고 볼 수 없습니다.

## 저장소 안내

| 경로 | 내용 |
|---|---|
| [docs/01-the-mapping.md](docs/01-the-mapping.md) | 일곱 component와 두 channel |
| [docs/02-memory-lifecycle.ko.md](docs/02-memory-lifecycle.ko.md) | 네 representation, 일곱 operation, host handoff, health metric |
| [docs/03-governance-tiers.md](docs/03-governance-tiers.md) | advisory, guarded, enforced tier |
| [docs/04-principles.md](docs/04-principles.md) | 판단과 연결된 짧은 운영 원칙 |
| [docs/05-runtime.ko.md](docs/05-runtime.ko.md) | 설치 가능한 memory kernel, store, routing, lifecycle, optional action bridge |
| [docs/06-adapters-and-observer.ko.md](docs/06-adapters-and-observer.ko.md) | Smart Connections 호환과 clean-room Command Center |
| [docs/07-mcp-server.ko.md](docs/07-mcp-server.ko.md) | provider-neutral MCP tool, resource, 설정, security boundary |
| [src/brain_ai_memory/](src/brain_ai_memory/) | 공개 Python runtime implementation |
| [tests/](tests/) | kernel integration, adapter, supporting contract test |
| [CHANGELOG.md](CHANGELOG.md) | release change와 evidence boundary |
| [schema/brain_components.yaml](schema/brain_components.yaml) | machine-readable component ontology |
| [templates/](templates/) | 복사해 쓸 수 있는 memory, rule, hook skeleton |
| [examples/](examples/) | synthetic data를 사용하는 작은 실행 예제 |
| [evidence/](evidence/) | 운영 snapshot, 내부 A/B summary, capacity simulation |
| [benchmarks/](benchmarks/) | memory evaluation protocol·pilot과 supporting contract verification |

## 기여

한 가지 절대 규칙은 clean-room입니다. 실제 개인 정보나 민감한 데이터를
저장소에 넣지 마세요. 자세한 내용은 [CONTRIBUTING.md](CONTRIBUTING.md)를
참고하세요.

## 보안

취약점은 public issue 대신 GitHub의 private vulnerability reporting으로
신고해 주세요. [SECURITY.md](SECURITY.md)를 참고하세요.

## 인용

이 아키텍처나 평가 protocol을 연구 또는 시스템에 사용한다면
[CITATION.cff](CITATION.cff)의 metadata를 이용해 인용해 주세요.

## 라이선스

MIT. [LICENSE](LICENSE)를 참고하세요.
