[English](README.md) | **한국어**

# Brain-AI Memory

> **여러 세션에 걸쳐 올바른 맥락을 기억하고, 규칙을 강제하고, 정확한 상태를
> 보존하고, 절차를 끝까지 수행해야 하는 에이전트를 위한 local-first
> memory/control runtime입니다.**

**지금 설치 가능:** public alpha `v0.2`. Local demo에는 API key, model call,
database server, 외부 service가 필요하지 않습니다.

인간의 기억과 행동 조절은 하나의 저장소가 아니라 서로 구분되면서 상호작용하는
여러 기능에 의존합니다. Brain-AI Memory는 **뇌의 해부학을 그대로 모사하지
않고 기능적 분화라는 설계 원칙**을 가져와 store, routing, deterministic
guard, executable fallback sequence, lifecycle operation이라는 검사 가능한
software contract로 번역합니다.

![Graphical abstract: 혼란스러운 agent의 뒤섞인 history가 input gate를 거쳐 event, knowledge, rule, exact state, executable sequence가 분리된 brain-inspired software runtime으로 들어가고, lifecycle loop가 memory를 versioning·archive한 뒤 같은 agent가 compact하고 승인된 context bundle을 받는 과정](docs/assets/graphical-abstract.png)

| 뇌에서 착안한 원리 | AI 구현 | 관찰 가능한 결과 |
|---|---|---|
| 사건·지식·행동·수량 기능을 분리 | episodic/semantic store, exact state, traced routing | 모든 실패를 ‘retrieval 문제’로 뭉개지 않고 담당 subsystem까지 추적 |
| 행동을 gate하고 숙련된 sequence를 조정 | deterministic guard와 executable fallback | 금지 행동은 차단되고 등록된 fallback은 성공 또는 소진까지 진행 |
| 재사용 과정에서 변화나 충돌이 드러난 기억을 갱신 | 승인된 consolidation, conflict-triggered reconsolidation, 7가지 lifecycle operation | provenance를 보존하며 승격·대체·압축·보관·망각 가능 |

*뇌 영역 이름은 기능을 기억하기 위한 표지이며, 각 영역이 해당 기능을 단독
수행한다는 해부학적 주장이 아닙니다.* 이 runtime은 기존 model, retriever,
workflow engine 주변에서 작동하며 이를 대체하지 않습니다. [뇌 기능에서
software contract로의 mapping과 한계](docs/01-the-mapping.md)를 함께 공개합니다.

> **근거의 경계.** 공개 runtime은 이 contract들을 설치하고 실행할 수 있음을,
> 운영 기록은 지속적으로 사용했음을 보여줍니다. Retrieval test와 contract
> 비교는 각각 명시한 대상만 측정합니다. 이것만으로 brain-inspired mapping이
> 단순한 memory보다 end-to-end LLM 정확도를 높였다고 주장하지 않습니다.
> [근거와 한계](#근거-현황)

## 전체 local loop 설치하고 실행하기

API key, model call, database server, 외부 service가 필요하지 않습니다.

```bash
git clone https://github.com/Hahyun-Lee/brain-ai-memory.git
cd brain-ai-memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

brain-ai init
brain-ai demo
brain-ai status
```

Demo는 episodic·semantic memory, exact numerical state, procedural rule을
기록합니다. 이어서 한 query를 관련 component로 routing하고, action gate를
적용하고, audit trace와 checkpoint를 생성합니다. 모든 상태는
`./.brain-ai/`에만 저장됩니다.

```bash
brain-ai remember --type episodic --text "배포일이 목요일로 변경됐다" --promote semantic
brain-ai remember --type state --key open_reviews --value 3
brain-ai run "최근 무엇이 바뀌었고 review가 몇 개 남았나?"
brain-ai consolidate          # preview
brain-ai consolidate --apply  # 명시적 승격
brain-ai serve                # http://127.0.0.1:8765
```

[한국어 runtime guide](docs/05-runtime.ko.md), [adapter와 observer
guide](docs/06-adapters-and-observer.ko.md), 기존 [single-component
example](examples/README.md)을 참고하세요.

## 이미 겪고 있는 실패부터 진단하세요

여러 세션에 걸쳐 동작하는 코딩, 연구, 운영, 비서 에이전트를 만들고 있으며
다음 중 하나라도 익숙하다면 살펴볼 가치가 있습니다.

- "이미 기록했는데 왜 에이전트가 다시 묻지?"
- "검색된 메모는 관련은 있지만 이제 사실이 아닌데?"
- "prompt에 규칙이 있는데도 왜 위반했지?"
- "fallback 절차를 알고 있었는데 첫 단계만 시도하고 멈췄다."
- "context와 vector store를 더했지만 실패 원인은 여전히 진단하기 어렵다."
- "메모리 파일만 계속 커지고 무엇을 compact하거나 지워야 할지 모르겠다."

지속 상태가 없는 단일 턴 챗봇에는 이 아키텍처가 필요하지 않을 가능성이
큽니다. 문제가 일반적인 문서 검색뿐인 워크플로에도 필요하지 않습니다. 이미
겪고 있는 실패부터 시작하세요. 전체 아키텍처를 한꺼번에 채택할 필요는 없습니다.

| 관찰한 문제 | 먼저 진단할 대상 | 가장 작은 유효한 변화 |
|---|---|---|
| 확정된 문맥이 사라지거나 잘못된 사건에 연결됨 | 일화 기억(HC) | timestamp가 있는 event/entity binding 추가 |
| 검색 결과는 관련 있지만 오래됨 | 의미 기억(ATL) | freshness를 확인하고 충돌 시 reconsolidation |
| 에이전트가 규칙을 알지만 무시함 | 절차 규칙(BG) | 반복 위반을 prose에서 guard로 승격 |
| 여러 단계의 fallback이 중간에 멈춤 | 절차 실행(CB) | sequence를 실행 가능한 harness로 이동 |
| 정확히 알 수 있는 수치를 추측함 | 수치 상태(IPS) | 추정 대신 exact store 조회 |
| 작업이 잘못된 store나 tool로 전달됨 | 오케스트레이션(PFC) | routing 결정을 추적하고 수정 |
| 항상 로드되는 index가 계속 커짐 | 메모리 생명주기 | 짧은 pointer만 유지하고 detail은 archive 또는 migrate |

이 기능들은 그림을 만들기 위해 고안한 것이 아닙니다. 지속적이고 다중
프로젝트인 에이전트 시스템을 실제 운영하면서 memory, semantic retrieval,
guard, executable workflow의 실패를 디버깅하는 과정에서 분리됐습니다. 아래
근거에서는 이 운영 기록을 인과 주장 및 benchmark 주장과 구분합니다.

## RAG, hook, harness, loop와 어떻게 다른가요?

**모두 사용하지만 어느 하나를 새 이름으로 부르는 것은 아닙니다.** 이들은
구현 메커니즘입니다. Brain-AI Memory는 각 메커니즘에 역할, 실패 조건,
feedback loop가 실제로 닫혔는지 확인하는 검사를 부여하는 진단·생명주기
계층입니다.

| 기존 방법 | 답하는 질문 | 그 자체만으로 답하지 못하는 질문 |
|---|---|---|
| long context 또는 memory file | 모델이 지금 무엇을 읽을 수 있는가? | 이후 무엇을 이동, 만료, 분리하거나 계속 접근 가능하게 둘 것인가? |
| RAG 또는 vector store | 어떤 저장 text가 query와 유사한가? | 최신인가, 어느 memory type이 소유하는가, rule로 바뀌어야 하는가? |
| hook | 언제 code가 event를 검사하거나 가로챌 수 있는가? | 어떤 policy가 들어가야 하며 여러 단계의 결과가 끝까지 완료됐는가? |
| guard | 이 한 행동을 허용해야 하는가? | fallback sequence를 어떻게 끝까지 실행할 것인가? |
| harness 또는 workflow engine | 이 절차를 어떻게 실행할 것인가? | 이후 어떤 지식을 recall, update, consolidate할 것인가? |
| evaluator 또는 retry loop | 한 번 더 실행해야 하는가? | 무엇이 세션 간 지속되며 반복 실패가 시스템을 어떻게 바꾸는가? |
| Brain-AI Memory | 어느 subsystem이 실패했고 어떤 mechanism과 lifecycle operation이 맞는가? | public alpha가 local reference runtime을 제공하며 production scale, model client, 조직 policy는 사용자가 연결 |

Hook은 연결 지점입니다. Guard는 그 지점에 연결된 허용/차단 판단입니다.
Harness는 sequence를 소유하고, loop는 verdict를 다시 그 sequence에
반영합니다. 서로 관련은 있지만 대체 가능하지 않으며, 어느 하나도 완전한
메모리 아키텍처는 아닙니다.

### 기여: 원시 요소의 발명이 아니라 구분된 통합

정확한 주장은 **원시 요소의 발명이 아니라 구분된 통합**입니다. Working,
episodic, semantic, procedural memory 범주는 이미 확립된 개념이고, RAG,
hook, workflow harness, evaluator, compaction도 기존 기술입니다.

이 저장소의 기여는 이들을 연결하는 운영 계약입니다.

- 모든 component는 서로 다른 failure mode와 diagnostic을 명시해야 합니다.
- 절차 **규칙**(BG)과 절차 **실행**(CB)을 분리합니다. 한 행동을 막는 것과
  fallback sequence를 완료하는 것은 서로 다른 mechanism이 필요합니다.
- exact numerical state(IPS)와 preventive input gating(TH)을 일반적인
  'memory' 안에 숨기지 않고 명시적으로 모델링합니다.
- consolidation과 reconsolidation은 episode가 재사용 가능한 knowledge가
  되거나 stale knowledge가 갱신되는 방법을 규정합니다.
- 모든 memory entry에는 keep, compact, archive, migrate to knowledge,
  migrate to rules, delete, split 중 하나의 lifecycle operation을 부여합니다.
- component의 존재와 **loop closure**를 따로 감사합니다. rule file, hook,
  vector index가 존재한다는 사실만으로 결과가 end-to-end로 소비된다고 볼 수
  없습니다.

Brain mapping은 이 failure class들을 섞지 않기 위한 engineering analogy입니다.
여러분의 stack에서 진단을 개선하지 못한다면 analogy는 버리고 contract만
사용해도 됩니다. 이런 점에서 hook library, retriever, workflow engine과
범위가 다르지만, 통합 시스템이 더 단순한 대안보다 end-to-end로 우월하다는
사실은 아직 입증하지 않았습니다.

## 적용 경로 선택하기

Clean-room public runtime을 실제로 설치할 수 있습니다. 통합 local loop에서
시작하거나, 현재 failure와 맞는 component만 채택하세요.

| 목표 | 시작점 | 첫 성공 기준 |
|---|---|---|
| differentiated lifecycle 전체 실행 | [`brain-ai` runtime](docs/05-runtime.ko.md) | local에서 install, run, checkpoint 후 routed trace 확인 |
| Obsidian / Smart Connections 연결 | [semantic adapter](docs/06-adapters-and-observer.ko.md) | MCP와 vault fallback result가 backend를 명시 |
| 비공개 인프라 없이 loop 관찰 | [clean-room observer](docs/06-adapters-and-observer.ko.md#clean-room-command-center) | localhost에서 component count와 audit event 확인 |
| 반복되는 결정론적 위반 하나 차단 | [behavioral guard](templates/hooks/behavioral-guard.py) | 위험한 pattern은 차단되고 유사한 안전 행동은 통과 |
| 차단 없이 판단 검사를 표면화 | [self-check trigger](templates/hooks/self-check-trigger.py) | 의도한 context에서만 warning 발생 |
| index가 두 번째 database가 되는 것 방지 | [memory skeleton](templates/memory/MEMORY.skeleton.md) | topic당 한 줄짜리 link만 항상 로드됨 |
| 무엇을 유지하거나 이동할지 결정 | [seven-operation helper](templates/memory/7-op-decision.md) | 검토한 모든 entry가 정확히 하나의 operation을 받음 |
| 채택 전에 아키텍처 평가 | [mapping](docs/01-the-mapping.md)과 [evidence](evidence/README.md) | 실제 failure를 component에 mapping하거나 맞지 않는 지점을 식별 |

Hook은 Python 표준 라이브러리만으로 self-test할 수 있습니다.

```bash
python3 templates/hooks/behavioral-guard.py --selftest
python3 templates/hooks/self-check-trigger.py --selftest
```

## 아키텍처 동작 방식

핵심 map은 일곱 개의 기능 component와 두 개의 transfer channel로 구성됩니다.
전체 근거와 한계는 [상세 mapping](docs/01-the-mapping.md)을 참고하세요.

| Component | 에이전트 역할 | 진단하려는 실패 |
|---|---|---|
| PFC | orchestrator와 routing | 올바른 capability가 잘못된 store나 tool로 전달됨 |
| HC | episodic event와 relationship | event가 잘못된 person, time, thread에 binding됨 |
| ATL | semantic knowledge | 검색 결과가 오래됐거나 출처가 잘못됨 |
| BG | procedural allow/deny rule | rule은 있지만 작동하지 않음 |
| CB | executable multi-step harness | procedure가 완료 전에 중단됨 |
| IPS | exact numerical state | 정확히 알 수 있는 quantity를 추측함 |
| TH | preventive input gate | 위험한 input이 execution에 도달함 |

![Memory lifecycle: recall, 세션 중 tagging, consolidation, 일곱 가지 lifecycle operation](docs/assets/memory-lifecycle.svg)

## 근거 현황

Brain-AI Memory에는 longitudinal operation, within-system retrieval test,
reproducible public-data evaluation이라는 서로 다른 세 가지 근거 계층이
있습니다. 이들은 서로 다른 질문에 답하며 하나의 headline으로 합치면 안 됩니다.

| 질문 | 현재 근거 |
|---|---|
| 실제로 구현해 사용했는가? | **예. 2026-04-20부터 13개 project memory index에서 운영** |
| 충분한 운영 노출이 있었는가? | **예. 2026-06-10부터 2026-07-14까지 계측 세션 419개, 63.6M tokens** |
| 내부 pointer에서 semantic retrieval이 live grep control보다 나은가? | **시사적 결과 있음. HIT@10 69.0% → 88.8%, n=116** |
| 동일 budget에서 graph augmentation이 semantic store를 개선하는가? | **시사적 결과 있음. HIT@10 86.2% → 91.9%, n=690 sources** |
| 공개 benchmark에서 stack-aligned retrieval을 비교했는가? | **예. LoCoMo retrieval HIT@10: GTE 62.1%, BM25 57.0%, graph-lite 51.9%; answerable questions n=1,531** |
| compact pointer index가 full append-only entry보다 더 많이 들어가는가? | **예. 결정론적 capacity simulation** |
| 단순 compact pointer가 공개 데이터에서 retrieval quality를 보존하는가? | **아니요. 현재 keyword pointer는 recall과 size를 교환함** |
| 공개 runtime의 각 component가 서로 다른 contract를 실행하는가? | **Deterministic ablation: 전체 runtime 20/20, flat retrieval control 1/20. Flat control도 memory query 6/6에서 예상 top text를 찾았으며, 이는 conformance이지 LLM efficacy가 아님** |
| lifecycle이 실제 LLM agent의 answer accuracy를 개선하는가? | **아직 측정하지 않음** |
| 전체 아키텍처가 RAG, long context 또는 다른 memory system보다 나은가? | **아직 측정하지 않음** |
| latency, token cost, conflict resolution, abstention이 개선되는가? | **아직 측정하지 않음** |
| single-owner multi-project deployment가 얼마나 일반화되는가? | **알 수 없음. 다기관 반복 검증 없음** |

### 공개 runtime component ablation

설치 가능한 package를 20개의 deterministic contract case와 21개 condition에서
평가했습니다. 조건은 flat retrieval control, 10개의 누적 addition, 10개의
leave-one-out removal입니다. LLM, 외부 API, 비공개 data, 외부 judge는 사용하지
않았습니다.

![누적 component-contract ablation: flat control은 20개 중 1개, 전체 public runtime은 20개 contract 모두 충족](docs/assets/component-ablation.png)

전체 runtime은 작성된 contract 20/20을 충족했고 flat control은 1/20을
충족했습니다. 중요한 점은 flat control도 memory query 6/6에서 예상 top text를
모두 찾았다는 것입니다. 낮은 전체 점수는 text retrieval 실패가 아니라 typed
routing, exact state, gate, fallback sequence, lifecycle contract의 부재를
반영합니다. 각 component를 누적했을 때 지정된 case가 복구됐고, 전체에서 하나를
제거했을 때 해당 case가 실패했습니다. 이는 공개 component들이 서로 다른
software responsibility를 실행한다는 근거이며, 뇌에서 영감을 받았다는 사실
자체가 answer quality를 높인다거나 전체 아키텍처가 RAG보다 우월하다는 근거는
아닙니다. [Report, raw record 420개, summary,
manifest](benchmarks/pilots/component-ablation-20260715/README.md)를 확인하세요.

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

## 다음 외부 검증

다음 release-grade QA 비교에서는 reader model, prompt, context budget, dataset
split, scoring procedure를 고정하고 다음 조건을 비교합니다.

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
| [docs/02-memory-lifecycle.md](docs/02-memory-lifecycle.md) | 일곱 operation, session transfer, health metric |
| [docs/03-governance-tiers.md](docs/03-governance-tiers.md) | advisory, guarded, enforced tier |
| [docs/04-principles.md](docs/04-principles.md) | 판단과 연결된 짧은 운영 원칙 |
| [docs/05-runtime.ko.md](docs/05-runtime.ko.md) | 설치 가능한 CLI, store, routing, harness, lifecycle |
| [docs/06-adapters-and-observer.ko.md](docs/06-adapters-and-observer.ko.md) | Smart Connections 호환과 clean-room Command Center |
| [src/brain_ai_memory/](src/brain_ai_memory/) | 공개 Python runtime implementation |
| [tests/](tests/) | end-to-end runtime과 adapter test |
| [CHANGELOG.md](CHANGELOG.md) | release change와 evidence boundary |
| [schema/brain_components.yaml](schema/brain_components.yaml) | machine-readable component ontology |
| [templates/](templates/) | 복사해 쓸 수 있는 memory, rule, hook skeleton |
| [examples/](examples/) | synthetic data를 사용하는 작은 실행 예제 |
| [evidence/](evidence/) | 운영 snapshot, 내부 A/B summary, capacity simulation |
| [benchmarks/](benchmarks/) | contract A/B, external-data retrieval pilot, release gate |

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
