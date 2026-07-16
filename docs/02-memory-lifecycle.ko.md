# 02 — Memory Lifecycle

[English](02-memory-lifecycle.md)

> 계속 커지기만 하는 memory store는 결국 실패합니다. Agent memory의 어려운
> 점은 기록 자체가 아니라, 시간이 지나며 각 항목이 무엇이 되어야 하는지
> 결정하고 store가 부패하기 전에 옮기는 것입니다. 이 문서는 모든 항목에
> 적용할 구체적인 판단 규칙과 시스템 저하를 감지할 health metric을 설명합니다.

이 문서는 [`01-the-mapping.md`](01-the-mapping.md)를 이어갑니다. 앞 문서가
store를 구분했다면, 여기서는 그 사이의 이동을 관리합니다.

## Lifecycle이 필요한 이유

대부분의 agent memory는 한 방향으로만 커집니다. 사실을 계속 추가하고, context
file은 길어지며, note는 누적됩니다. 언제 승격하고 압축하거나 제거할지 정한
규칙이 없으므로 아무것도 정리되지 않습니다. 그러면 반대 방향의 두 실패가
동시에 발생합니다.

- **Bloat.** 항상 load되는 memory가 agent가 다룰 수 있는 범위를 넘고 중요한
  항목이 오래된 항목에 묻힙니다. Recall할 것이 많아져서 오히려 recall이
  나빠집니다.
- **Loss.** Bloat를 피하려고 내용을 통째로 삭제하면, 몇 달 뒤 필요해진 중요한
  결정도 흔적 없이 사라집니다.

생물학적 memory는 representation이 단순히 축적되는 것이 아니라 시간에 따라
재조직되고 변환되며 강화 또는 약화될 수 있다는 발상에 동기를 줍니다. 아래
lifecycle은 생물학적 simulation이 아니라 의도적인 software translation입니다.
즉, 명시적이고 audit 가능한 operation과 그 선택 규칙입니다.

## 일곱 가지 operation

Memory 항목을 다시 검토할 때 다음 중 정확히 하나를 선택합니다.

| Operation | 적용 조건 | Reference runtime의 효과 |
|---|---|---|
| **keep** | 여전히 active하거나 reference되고, supersede되었다는 신호가 없음 | 결정을 기록하고 항목은 active·unchanged 상태로 유지 |
| **compact** | 핵심은 남아 있지만 detail이 차지하는 공간만큼 가치가 없음 | Host가 pointer를 만들 후보로 기록하며 source를 자동 축약하지 않음 |
| **archive** | 해결됐고 오래됐으며 rule, commit, downstream document 등에 이미 반영됨 | 기본 active view에서 숨기되 audit을 위해 source를 유지 |
| **migrate-to-knowledge-base** | 한 context를 넘어 재사용할 원칙이나 방법임 | Episodic source를 기본 view에서 숨기며 실제 파생은 명시적 consolidation preview/apply가 필요 |
| **migrate-to-rules** | enforce 가능한 rule 또는 실행 step으로 표현할 수 있는 반복 procedure임 | Episodic source를 기본 view에서 숨기며 실제 rule은 명시적 pattern을 포함한 승인 consolidation이 필요 |
| **delete** | 잘못됐거나 이후 결정에 의해 supersede됐고 보존 가치가 없음 | 논리적 tombstone/inactive status를 만들며 source byte를 물리 삭제하지 않음 |
| **split** | 하나의 항목이 서로 다른 여러 topic을 포함할 정도로 커짐 | Host가 linked topic entry를 만들 action으로 기록하며 file을 자동 분할하지 않음 |

이 표는 installable alpha가 실제로 하는 일을 설명합니다. Episodic entry의
`archive`, `delete`, 두 migration decision은 기본 active view에서 entry를 숨기지만
append-only event는 `include_inactive`로 남습니다. Semantic entry에서는
`archive`와 `delete`만 row를 보존한 채 status를 바꾸고, 다른 lifecycle decision은
그 status를 바꾸지 않은 채 audit state를 추가합니다. `compact`와 `split`은
host가 소비해야 할 audited decision이지 file rewrite engine이 아닙니다. Secure
erasure, archive file 이동, retention enforcement는 host 책임입니다.

아키텍처 수준에서는 두 decision이 [`01`](01-the-mapping.md#the-two-channels)의
consolidation-inspired software channel을 지시합니다.
**migrate-to-knowledge-base**는 재사용 knowledge로 파생할 episodic evidence를,
**migrate-to-rules**는 enforce 가능한 rule 또는 실행 step으로 만들 승인된 반복
lesson을 식별합니다. `lifecycle` command만으로 파생 artifact가 생기지는 않으며,
명시적인 `consolidate` preview/apply flow를 사용해야 합니다. 어느 operation도
생물학적 consolidation 재현을 주장하지 않습니다.

### Operation 선택 순서

여러 operation이 동시에 가능하면 다음 순서로 판단합니다.

1. 항목이 index anchor이거나 아직 active하거나 supersede 신호가 없으면
   **keep**합니다.
2. 너무 길고 여러 topic을 다루면 **split**합니다.
3. 실제로 잘못된 경우에만 **delete**합니다. 확신이 없으면 archive를
   우선합니다.
4. 재사용할 원칙이나 방법이면 **migrate-to-knowledge-base**합니다.
5. 형식화할 가치가 있는 procedure이면 **migrate-to-rules**합니다.
6. 해결됐고 오래됐으며 downstream artifact에 반영됐으면 **archive**합니다.
7. 일부 detail만 가치가 없어졌으면 **compact**합니다.

순서가 중요한 이유는 archive와 compact가 쉽지만 손실을 일으킬 수 있기
때문입니다. Migration 여부를 먼저 판단해야 재사용 가능한 lesson이 조용히
archive되기 전에 knowledge base나 rule로 승격됩니다.

설계 수준에서 **delete**는 향후 destruction을 승인할 수 있는 유일한
decision이므로 강하게 제한합니다. “더 이상 관련 없다”는 delete가 아니라
archive 사유이며, 기준은 “거짓이거나 이후 결정으로 무효가 됐다”입니다. 그러나
이 reference runtime의 delete는 복구 가능한 logical tombstone이지 privacy erasure의
증명이 아닙니다. 물리 삭제가 필요하면 host가 별도의 retention-policy operation을
수행하고 검증해야 합니다.

## 하나의 memory file이 아닌 네 가지 representation

장기 실행 agent는 모든 representation을 같은 종류의 memory로 취급하면 안
됩니다.

| Representation | 목적 | 기본 policy |
|---|---|---|
| **raw host trace** | Provider-native transcript 또는 tool-event evidence | 명시적인 host privacy·retention policy가 허용할 때만 보존하며, 보존한 evidence를 제자리에서 덮어쓰지 않음 |
| **working memory** | Host가 소유하고 token budget을 적용하는 현재 task context | 지금 필요한 scoped candidate record만으로 조립 |
| **episodic memory** | entity binding, ingest time, text, source label을 포함한 구조화 event | 가능한 경우 host가 raw evidence link를 별도로 보존 |
| **consolidated memory** | episode에서 파생한 재사용 knowledge 또는 승인된 procedure | version과 source를 기록하고 승격을 명시적으로 수행 |

Disk에 transcript가 있다는 사실만으로 working memory가 되지 않으며, summary도
자동으로 신뢰할 수 있는 사실이 되지 않습니다. Retrieval은 record 개수로
제한된 candidate view를 반환하고, host가 model의 token budget과 working context에
실제로 넣을 항목을 결정합니다. Consolidation은 새로운 representation을
파생하며 evidence를 지우면 안 됩니다. Public runtime은 명시적으로 기록된
`events.jsonl`과 checkpoint를 소유하지만 Claude Code, Codex 또는 다른 host
transcript를 scrape하지 않습니다. 이 저장소에는 Claude Code JSONL이나 Codex
rollout adapter가 없습니다. 연결하는 host 또는 custom adapter가 policy상
허용된 raw trace의 retention을 담당하고 선택한 event만 runtime에 mapping합니다.

## Session과 long-term memory 사이의 이동

위 lifecycle은 저장된 항목을 관리합니다. Session을 통과하는 software flow도
있지만, 같은 mnemonic label을 쓴다는 이유로 생물학적 transfer mechanism을
주장하지는 않습니다.

- **Session 시작(recall).** Host가 long-term memory를 명시적으로 query하고,
  recent event, 적용 가능한 rule, exact state처럼 범위가 제한된 결과를 현재
  working context에 제공합니다. Runtime은 이 context를 model에 자동 inject하지
  않습니다. 이것이 long-term-to-working 방향입니다.
- **Session 중(tagging).** Host가 선택한 decision, issue, 외부 agreement가 생길
  때 `brain_remember` 또는 `brain-ai remember`를 명시적으로 호출합니다.
  의도적으로 기록하지 않은 내용은 structured episodic store 밖에 남으며,
  runtime이 provider transcript에서 이를 추론하지 않습니다.
- **Session 종료(consolidation과 handoff).** Host가 `brain-ai consolidate`를
  preview하고 승인 후에만 apply하며, durable handoff를 위해
  explicit/default entity가 있는 `brain_checkpoint` 또는
  `brain-ai handoff --entity ...`를 호출합니다. 기존 `brain-ai checkpoint`는 global summary만
  기록합니다. 이는 working
  memory 전체가 자동 이동하는 것이 아니라 명시적인 integration sequence입니다.

흔한 실패는 explicit write를 건너뛰고 session 종료 시 내용을 재구성하려는
것입니다. 그때는 context가 이미 압축되어 초기 작업이 사라졌을 수 있습니다.
`brain_remember`를 structured write로 취급하고, consolidation과 checkpoint를
각각 별도의 명시적 operation으로 다뤄야 합니다.

두 방향은 background loop가 아닌 **host integration contract**입니다. Core
memory path에서는 host가 현재 goal을 query와 entity scope로 바꾸고, PFC가 관련
store에서 candidate record를 반환하며, host가 실제 working context를
조립합니다. Bottom-up에서는 host가 선택한 outcome을 `brain_remember`로
기록하고 consolidation을 preview·apply한 뒤 checkpoint를 생성합니다. Optional
action path에서는 host가 제안한 action에 TH/BG verdict를 받을 수 있고, CB는
host가 `brain-ai harness` 또는 `brain-ai sequence`를 호출할 때만 사용됩니다.
File이나 MCP connection이 존재하는 것만으로 loop가 닫히지 않습니다. 각
producer에는 consumer가 있어야 하고, integration check로 handoff가 실제
소비됐는지 검증해야 합니다.

## Health metric

Memory system의 health는 눈으로만 판단할 수 없습니다. 다음 세 signal은 저하를
일찍 발견하며, 각 threshold는 사용하는 stack에 맞게 정합니다.

- **Index budget.** 항상 load되는 index에는 모든 session에서 비용을 지불하므로
  hard size ceiling이 필요합니다. Ceiling을 넘으면 조용히 truncate될 수
  있습니다. Index는 entry별 한 줄(title과 hook)로 유지하고 detail은 연결된
  topic file로 옮깁니다. Ceiling에 가까워지면 lifecycle을 실행해야지 ceiling을
  높여서는 안 됩니다.
- **Orphan rate.** 존재하지만 index에서 연결되지 않은 entry는 agent가 찾을
  경로가 없어 실질적으로 recall할 수 없습니다. Inbound link가 없는 entry의
  비율은 store가 write-only memory로 변하는지를 가장 명확히 보여주며, 0을
  향해야 합니다.
- **Recall cap.** Relevance에 따라 memory file을 자동 retrieve할 때는 앞부분의
  제한된 slice만 inject될 수 있습니다. Cap보다 긴 file은 disk에 있어도 뒤쪽이
  recall 시 보이지 않습니다. Topic file을 cap 아래로 유지하거나 중요한 내용이
  잘린 이후에 놓이지 않게 해야 합니다.

세 metric의 공통점은 **disk에 저장된 것과 recall된 것은 같지 않다**는
것입니다. 건강한 lifecycle은 저장된 내용과 retrieved view(index, link, 각
file의 앞부분)의 차이가 커져 agent가 불완전한 정보로 확신하는 상황을
방지합니다.

## 저장소에서의 위치

이 문서의 decision table은 [`templates/memory/`](../templates/memory/)의 memory
file skeleton 및 decision helper와 함께 사용합니다. Procedure를 언제 enforced
rule로 승격할지는 [`03-governance-tiers.md`](03-governance-tiers.md)의 governance
discipline을 따릅니다.
