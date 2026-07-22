# 세션 메모리 자동화하기(선택 기능)

오늘 하던 프로젝트를 내일 다시 열면 Brain-AI Memory가 최근 인계 내용과 관련 있는
프로젝트 기억을 새 세션에 자동으로 전달할 수 있습니다. 매번 recall과 checkpoint
도구를 호출하라고 AI에게 지시할 필요가 없습니다.

여러 Codex·Claude Code 세션에 걸쳐 작업하고, 인계 누락·오래된 사실·프로젝트 혼동이
실제 문제로 이어질 때 유용합니다. 한 번 끝나는 대화, 짧은 작업, 작은
`MEMORY.md`를 사람이 쉽게 관리할 수 있는 저장소라면 보통 필요하지 않습니다.

이 기능은 **기본으로 켜지지 않습니다.** 프로젝트 하나에 `--mode loop`를 지정해
활성화합니다. 사용자 전체에 설치하는 loop는 의도적으로 허용하지 않습니다. 모든
hook은 프로젝트 경로 하나와 memory entity 하나에 명확히 묶여야 합니다.

## 자동으로 처리하는 일

| 시점 | Brain-AI Memory가 하는 일 |
|---|---|
| 세션 시작 | 중단된 checkpoint를 복구하고, 승인해 가져온 프로젝트 내부 원본을 확인한 뒤 최신 handoff와 현재 프로젝트 기록을 정해진 byte 한도 안에서 전달 |
| 사용자 요청 입력 | 같은 프로젝트에서 관련 기록을 찾아 출처가 있는 데이터로 전달. 기억 속 문장을 지시로 실행하지 않음 |
| 지원하는 명령 실행 직전 | 현재 프로젝트에 연결된 block rule을 검사 |
| 지원하는 파일 수정 또는 memory write 완료 | 제한된 변경 metadata를 기록하고, 승인한 원본을 다시 확인하며, 중복 hook 호출을 제거한 뒤 session을 변경 상태로 표시 |
| 문맥 압축 또는 turn/session 종료 | memory 관련 변경이 있을 때만 중복 없는 checkpoint 기록 |
| 다음 세션 시작 | 최신 handoff를 전달됨으로 표시하고 첫 요청에서 전달 확인 상태를 기록 |

자동으로 주입하는 문맥의 기본 상한은 safety envelope와 source ID를 포함해
6,000 byte입니다. 한도에 들어가지 않는 기록은 제외하므로 hook이 문맥을 끝없이
늘리지 않습니다.

이는 lifecycle 자동화이지 진실 판단 자동화가 아닙니다. 승인한 source fragment가
바뀌거나 사라졌다는 사실은 확인할 수 있지만, 새 문장이 참인지 판단하거나 정확한
상태값·새 rule로 승격하거나 이전 사실을 자동 교체하지는 않습니다. 이런 변경은
명시적인 memory tool이나 review workflow로 처리합니다.

## 원본 변경 감지와 기억 재통합

승인해 가져온 Markdown은 그 기록의 근거로 남습니다. Loop는 세션 시작 때와 지원하는
프로젝트 파일 수정 뒤에 현재 프로젝트 내부 원본을 apply 당시 fragment와 비교합니다.

- 바뀌지 않은 fragment의 기록은 계속 사용합니다.
- 사라진 fragment에서 가져온 기록은 자동 recall에서 제외합니다.
- import rule의 원본이 바뀌면 자동 action gate는 fail-closed review hold로 전환합니다.
  Source text 변경만으로 승인한 guard를 조용히 해제할 수 없습니다.
- 바뀐 원본은 기존 review·apply workflow에서 확인할 수 있도록 일반 audit으로
  준비하며, 어떤 항목도 자동 승격하지 않습니다.
- 원본이 없거나 읽을 수 없거나 프로젝트 밖에 있거나 제한을 넘으면 unavailable로
  보고, 파생 기록은 이력에 남기되 자동 사용하지 않습니다.

이는 불일치를 감지하고 근거가 사라진 기억이나 행동을 억제한 뒤 검토를 거쳐 재통합하는
제한된 prediction-error/reconsolidation 단계입니다. 생물학적 뇌를 그대로 재현하거나
진실을 판별한다는 뜻은 아닙니다. 확인 범위는 entity당 승인 원본 32개, 원본당
2 MiB입니다. 완료한 확인 결과를 cache하므로 prompt recall과 실행 직전 rule 검사는
지연에 민감한 경계에서 원본 파일을 다시 읽지 않습니다.

`brain-ai doctor --host ... --mode loop`는 확인이 필요한 원본과 생성된 review audit을
표시합니다. 수동 tools-only recall에는 이 loop cache가 적용되지 않으므로, 자동 mode
밖에서 쓰기 전에는 바뀐 원본을 review·apply해야 합니다.

## 설치하고 프로젝트 identity 만들기

전용 environment에 package를 설치합니다.

```bash
git clone https://github.com/Hahyun-Lee/brain-ai-memory.git
cd brain-ai-memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ".[mcp]"
```

Memory를 사용할 프로젝트로 이동해 stable entity를 하나 만듭니다. 같은 entity로
이미 `MEMORY.md`를 가져왔다면 마지막 command는 생략합니다.

```bash
cd /path/to/your/project
export PROJECT_ROOT="$PWD"
export BRAIN_AI_HOME="$PROJECT_ROOT/.brain-ai"
brain-ai init
brain-ai entity add --name my-project --type project
```

이 프로젝트에서는 같은 `PROJECT_ROOT`, `BRAIN_AI_HOME`, entity 이름을 계속
사용하세요. Runtime directory에는 암호화되지 않은 local data가 있으므로
`.brain-ai/`를 version control에 올리지 마세요.

## Codex 연결

먼저 managed 변경 사항을 미리 봅니다. `--apply` 없이는 아무것도 기록하지 않습니다.

```bash
brain-ai connect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
brain-ai connect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT" --apply
```

프로젝트용 tool connection과 lifecycle hook을 함께 추가합니다. Codex에서는 정확한
hook 정의를 신뢰할지 확인해야 합니다. 안내가 나오면 정의를 검토하거나 `/hooks`로
확인한 뒤 새 session을 열어 `SessionStart`가 실행되게 하세요. Managed lifecycle
file은 `.codex/hooks.json`입니다.

현재 Codex에는 `SessionEnd` hook이 없습니다. 따라서 변경이 있는 작업은 `Stop`과
문맥 압축 전에 checkpoint하고, 다음 `SessionStart`에서 이어받습니다. `Stop`은 turn
경계이므로 변경이 없는 turn마다 checkpoint를 추가하지 않습니다.

설치 여부와 실제 작동 여부를 함께 확인합니다.

```bash
brain-ai doctor --host codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
```

`configured`는 managed connection과 hook이 존재한다는 뜻입니다. `active`는 실제 host
session에서 필요한 lifecycle event가 관찰됐다는 뜻입니다. 따라서 방금 적용한
설정은 hook을 신뢰하고 새 session을 사용하기 전까지 configured이지만 active가
아닐 수 있습니다.

## Claude Code 연결

Claude Code도 먼저 미리 보고 적용합니다.

```bash
brain-ai connect claude-code --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
brain-ai connect claude-code --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT" --apply

brain-ai doctor --host claude-code --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
```

Claude Code는 같은 start, prompt, tool, compaction, stop 처리를 받고, host가
제공하는 경우 `SessionEnd`도 처리합니다. Local lifecycle 설정은
`.claude/settings.local.json`에 기록됩니다. Project connection 승인 요청이 나오면
내용을 확인하고, `active`를 기대하기 전에 새 session을 여세요.

Host의 정확한 trust와 hook 화면은 공식 문서를 확인하세요:
[Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Claude Code hooks](https://code.claude.com/docs/en/hooks).

## 개인정보와 저장 범위

Hook은 관련 기록을 고르는 동안에만 prompt를 일시적으로 사용합니다. 기본 설정에서
loop는 다음 내용을 저장하지 않습니다.

- prompt 원문이나 대화 transcript
- tool output 원문이나 assistant의 마지막 message
- 수정한 file의 내용
- 추론으로 만든 사실, rule, 결정, exact state

대신 중복 방지와 audit에 필요한 hash·길이, tool 이름과 input key 이름, host의
session·turn 식별자를 단방향 변환한 hash, 선택한 memory ID, 지원하는 프로젝트 파일
수정의 상대 경로, freshness cache에 필요한 원본 경로·hash·상태·영향받은 record ID를
남깁니다. Freshness 확인은 승인한 Markdown을 local에서 읽지만 원문을 cache에 추가로
저장하지 않습니다. 원본이 바뀌면 수동 `brain-ai audit`과 같은 local audit artifact가
생성됩니다. Memory write tool을 명시적으로 호출하면 사용자가 저장하라고 요청한
내용은 기록됩니다. Typed memory, audit ledger, audit, checkpoint는 local plaintext
file이며 암호화 저장소가 아닙니다.

v0.6의 audit·episode·checkpoint JSONL history는 append-only입니다. Loop 조정 receipt와
현재 delivery 상태는 SQLite에 저장합니다. 어느 쪽도 자동으로 정리되지 않으므로
장기간 운영하는 프로젝트는 `.brain-ai/` 크기를 확인하고 의도한 local retention·backup
정책을 적용하세요. Loop 연결을 끊어도 이 directory는 지워지지 않습니다.

Hook이 실행되지 못하면 host를 종료하지 않고 짧은 degraded/unavailable message를
반환합니다. 반면 프로젝트 rule이 정상적으로 일치해 block verdict를 냈다면, 지원하는
pre-tool 경계에서 실제 거부 결과로 전달합니다.

업그레이드 후 현재의 제한된 pattern 규칙을 만족하지 못하는 기존 rule은 정규식으로
실행하지 않고 관리자 검토 대상으로 등록합니다. 안전한 대체 rule을 만들거나
`brain-ai rule disable RULE_ID --yes`로 기존 rule을 확인·비활성화할 때까지
해당 프로젝트의 행동 검사는 지원되는 실행 경계에서 모든 작업을 차단합니다.
`brain-ai rule list`와
`brain-ai doctor`가 검토할 항목을 보여 줍니다.

## Memory는 남기고 연결만 끊기

먼저 제거 내용을 미리 보고 적용합니다.

```bash
brain-ai disconnect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
brain-ai disconnect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT" --apply
```

Claude Code는 `codex`를 `claude-code`로 바꾸면 됩니다. Disconnect는 Brain-AI
Memory가 관리하는 tool connection과 hook 정의만 제거합니다. Managed 정의가 예상과
다르게 수정되어 있으면 제거하지 않고, 관계없는 host 설정과 `.brain-ai/`의 모든
기록은 그대로 둡니다.
