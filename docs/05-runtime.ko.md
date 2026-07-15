# 설치 가능한 reference runtime

공개 저장소에는 이제 component contract를 실제로 실행하는 local-first reference
implementation이 포함됩니다. 작고 provider-neutral하며 외부 dependency가 없습니다.
실제로 사용할 수 있는 코드지만 hosted multi-tenant service가 아니라 alpha
reference입니다.

## 설치와 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

brain-ai init
brain-ai demo
brain-ai status
```

기본 runtime은 `./.brain-ai/`에만 기록합니다.

| 경로 | 역할 |
|---|---|
| `config.json` | adapter와 observer 설정 |
| `events.jsonl` | append-only episodic memory(HC) |
| `state.sqlite3` | semantic memory, rule, numerical state, lifecycle record |
| `audit.jsonl` | PFC routing, gate, harness, lifecycle trace |
| `checkpoints.jsonl` | 명시적 session checkpoint |

다른 경로를 쓰려면 `BRAIN_AI_HOME` 또는 `--home`을 지정합니다.

## 전체 local loop

각 failure mode를 소유하는 store에 기록합니다.

```bash
brain-ai remember --type episodic --text "배포일이 목요일로 변경됐다" --promote semantic
brain-ai remember --type semantic --text "운영 배포 전에는 review가 필요하다"
brain-ai remember --type state --key open_reviews --value 3
brain-ai remember --type rule --pattern 'deploy\s+production' --text "승인 필요"
```

모델이나 agent client가 사용할 audit 가능한 context bundle을 만듭니다.

```bash
brain-ai run "최근 변경과 남은 review 개수는?" --action "deploy production"
```

출력에는 선택한 component, 검색 record, gate decision, latency가 포함됩니다.
숨겨진 model call은 없습니다. 이 JSON을 Claude, Codex, OpenAI, local model 또는
결정론적 worker에 전달할 수 있습니다.

TH/BG gate를 거쳐 CB harness로 명시적 command를 실행합니다.

```bash
brain-ai harness --query "package 검증" -- python -m unittest discover -s tests
```

성공할 때까지 등록된 fallback을 순서대로 실행할 수도 있습니다.

```bash
brain-ai sequence --query "검증" \
  --step '["python", "missing_check.py"]' \
  --step '["python", "-m", "unittest", "discover", "-s", "tests"]'
```

첫 단계가 실패해도 model의 판단으로 sequence가 중단되지 않고, code가 다음
fallback을 소비합니다.

## Consolidation, reconsolidation, lifecycle

Consolidation은 기본적으로 candidate만 보여주며, 명시적 apply가 있을 때만
상태를 바꿉니다.

```bash
brain-ai checkpoint --summary "배포 review 완료"
brain-ai consolidate
brain-ai consolidate --apply
```

오래된 semantic memory는 provenance를 보존하며 supersede합니다.

```bash
brain-ai supersede mem_old_id --text "배포일은 목요일이다"
```

일곱 lifecycle operation 중 하나를 적용합니다.

```bash
brain-ai lifecycle episodic evt_old_id archive --reason "해결 후 downstream에 반영됨"
```

## Python에서 사용하기

```python
from brain_ai_memory import BrainAIRuntime

runtime = BrainAIRuntime(".brain-ai")
bundle = runtime.process(
    "최근 배포 계획에서 무엇이 바뀌었나?",
    proposed_action="deploy production",
)
if bundle["gate"]["allowed"]:
    context_for_your_executor = bundle["memory"]
```

LLM은 교체 가능한 executor로 남습니다. 지속 cognition은 store, rule, harness
step, checkpoint, audit trail에 존재합니다.

## 공개 reference의 경계

- 기본 BM25 adapter는 투명한 local fallback이며 embedding parity 주장이 아닙니다.
- observer에는 인증이 없고 기본적으로 localhost에만 bind합니다. network에 직접
  노출하면 안 됩니다.
- consolidation이 model에게 rule을 임의 생성하게 하지 않습니다. rule 승격에는
  명시적 regex와 사람의 apply가 필요합니다.
- production에는 별도의 access control, encryption, backup, concurrency policy,
  model client, 조직별 hook이 필요합니다.
