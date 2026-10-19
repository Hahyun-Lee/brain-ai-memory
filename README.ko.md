[English](README.md) | **한국어** | [简体中文](README.zh-CN.md)

# Brain-AI Memory — AI 에이전트를 위한 로컬 프로젝트 메모리

**새 AI 대화가 프로젝트의 바뀐 결정부터 이어가도록 돕습니다.**

Codex·Claude Code가 사용할 프로젝트 기억을 내 컴퓨터에 저장합니다.
예를 들어 “금요일 배포”를 “목요일 배포”로 교체하면, 이 프로젝트에서는 목요일이
현재 결정이 되고 이전 결정은 이력에 남습니다. MCP로 연결하며, 기존 `MEMORY.md`의
선택한 내용을 원본 변경 없이 가져올 수 있습니다.

**로컬 저장 · 프로젝트 구분 · 수정 이력 · Python 3.10+ · MIT**

[로컬에서 확인하기](#로컬에서-확인하기) · [에이전트 연결](#codex와-claude-code-연결하기) ·
[Companion skill](docs/companion-skill.md) · [검증 근거](#검증-근거)

## 이런 경우에 쓰세요

여러 세션에 걸쳐 작업하고, 오래되거나 다른 프로젝트의 결정을 쓰면 실제 실수가
생기는 경우에 검토할 만합니다.

| 하는 일 | 관리해야 할 기억 |
|---|---|
| Codex·Claude Code로 여러 프로젝트 개발 | 비슷한 프로젝트를 구분하고 해당 작업의 미완료 항목 재개 |
| 오래 이어지는 실험·운영 업무 | 승인된 값과 출처, 이후 교체 이력 |
| 메모리 절차를 명시적으로 설계하는 에이전트 개발 | 대화 밖에서도 확인할 수 있는 사실·수정·세션 인계 기록 |

사람이 쉽게 정리할 수 있는 작은 `MEMORY.md`라면 그것만으로 충분할 수 있습니다.
일회성 대화나 일반 문서 검색에는 별도 메모리 런타임이 불필요할 가능성이 큽니다.

## 결정이 바뀌면 다음 세션도 수정된 내용을 알아야 합니다

아래는 가상의 배포 일정 예시입니다.

| 시점 | 사용자나 에이전트가 하는 일 | 저장소에 남는 것 |
|---|---|---|
| 첫 세션 | Atlas 프로젝트에 “금요일 배포” 저장 | 프로젝트에 연결된 사실. 가져온 문서에는 출처 행과 hash도 보존 |
| 일정 변경 | 해당 사실을 “목요일 배포”로 명시적으로 교체 | 이 프로젝트에서 목요일이 활성화되고 이전 기록은 이력에 유지 |
| 세션 종료 | “검토 완료, 다음은 staging 실행” 인계 | Atlas의 요약과 다음 할 일 |
| 다음 세션 | Atlas를 재개하고 현재 기록 조회 | 같은 범위의 인계와 질문에 맞는 현재 기억 |

에이전트가 실제 저장을 호출해야 합니다. MCP 설치나 문서 읽기만으로 사실이
저장되지는 않습니다. [Companion skill](skills/brain-ai-memory/SKILL.md)은 저장·수정·
확인·인계 절차를 안내하며, 실행 런타임은 별도로 설치합니다.

## 메모리 파일에 더하는 관리 기능

| 필요한 것 | 명시적으로 수행하는 작업 |
|---|---|
| 어느 프로젝트의 기록인지 구분 | 프로젝트 ID를 기록하고 해당 프로젝트에 연결 고정 |
| 이력을 남기며 사실 교체 | 이전 사실을 교체됨으로 표시하고 출처 보존 |
| 정확한 값 보관 | 값에 이름을 붙여 일반 메모와 구분해 저장 |
| 가져온 사실의 근거 변경 감지 | 선택형 loop에서 출처 행의 변경을 확인한 뒤 재검토 |
| 합의한 작업 이어가기 | 프로젝트 요약과 다음 할 일을 저장하고 재개 |

여기서 **메타인지는 기억을 쓰기 전에 점검하는 것**입니다. 에이전트가 어느 프로젝트의
기록인지, 현재 버전은 무엇인지, 출처는 어디인지 확인할 수 있게 합니다. 출처 변경
점검은 선택형 session loop가 담당합니다. 정보가 사실인지와 어떤 수정을 저장할지는
사람이나 에이전트가 판단합니다.
[기억 점검과 수정](docs/memory-self-monitoring.md)에 메커니즘과 한계를 설명했습니다.

## 로컬에서 확인하기

새 설치라면 임시 디렉터리에서 시작하세요. 아래 명령은 Python 3.10+, POSIX shell,
PyPI 접근이 필요합니다. 이미 설치했다면 기존 환경을 사용하세요.

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install "brain-ai-memory==0.7.0"
DEMO_HOME="$(mktemp -d)"
brain-ai --home "$DEMO_HOME" tour
```

가상 자료로 프로젝트 연결, 조회, 정확한 상태, 사실 교체와 인계를 확인하고,
선택형 행동 검사를 보여줍니다. 사용자 파일을 가져오거나 에이전트를 연결하지
않으며, 더 좋은 답변을 입증하는 데모는 아닙니다.

## Codex와 Claude Code 연결하기

| 모드 | 호출하는 주체 | 시작 경로 |
|---|---|---|
| **Tools + companion skill** | 에이전트가 안내 절차에 따라 MCP 도구 호출 | 아래 설정 후 [skill 추가](docs/companion-skill.md) |
| **선택형 session loop** | 지원하는 host hook이 조회·checkpoint 시점 제공 | [자동 세션 메모리](docs/08-autonomous-loop.ko.md) |

새 **tools mode** 연결을 만들 때는 먼저 프로젝트 안에 전용 환경을 만드세요.

```bash
cd /path/to/your/project
umask 077
python3 -m venv .brain-ai/runtime/v0.7.0
source .brain-ai/runtime/v0.7.0/bin/activate
export BRAIN_AI_HOME="$PWD/.brain-ai"
.brain-ai/runtime/v0.7.0/bin/python -m pip install "brain-ai-memory[mcp]==0.7.0"
brain-ai setup codex --entity my-project --mode tools
# Preview를 확인한 뒤 해당 프로젝트 연결에 적용합니다.
brain-ai setup codex --entity my-project --mode tools --apply
```

Claude Code에서는 `codex`를 `claude-code`로 바꾸세요. Setup은 entity를 만들거나
재사용하고 Python 실행 경로와 로컬 home을 host 설정에 고정합니다. Host 승인을
마친 뒤 MCP를 재연결하거나 새 프로젝트 세션을 시작하세요. `.brain-ai/`는 Git에서
제외하고, 기존 런타임이나 loop 설정이 있다면 덮어쓰지 마세요.

[Companion 절차](docs/companion-skill.md#confirm-the-connection)에 따라 실제 저장 결과와
해당 기록의 조회를 확인하세요. Tools mode는 자동 hook을 설치하지 않습니다.
Skill은 지시문을 제공하며 도구 사용을 강제하지 않습니다.

## 기존 MEMORY.md 가져오기

같은 로컬 home과 프로젝트 이름을 계속 사용하세요.

```bash
cd /path/to/your/project
export BRAIN_AI_HOME="$PWD/.brain-ai"
brain-ai audit MEMORY.md --entity my-project
```

반환된 audit와 각 항목의 출처를 확인하고, 실제 반환된 ID를 사용하세요.

```bash
brain-ai review AUDIT_ID
brain-ai review AUDIT_ID --approve-ready
brain-ai apply REVIEW_ID --yes
```

`--approve-ready`는 모호하지 않은 사실·사건을 승인하고 정확한 중복 후보를 건너뜁니다.
상태값·실행 규칙·이전 사실 교체는 명시적으로 검토해야 합니다. 원본 Markdown은
변하지 않습니다. 미해결 항목·출처 충돌·논리적 되돌리기는
[가져오기와 rollback 안내](docs/05-runtime.ko.md)를 참고하세요.

## 호환성과 데이터

이 시작 안내와 companion은 **공개 v0.7.0** 기준입니다. 해당 버전의 정확한 상태
조회에는 [companion](skills/brain-ai-memory/SKILL.md#exact-values-on-v070)의 numeric-hint
경로가 필요합니다. 로컬 개발의 저장·범위·조회 수정, 상태 projection과 cue delivery는
이 wheel에 포함되지 않습니다. [배포 경계](docs/release-and-operating-boundary.md)를
확인하세요.

기억은 로컬 SQLite·JSON·JSONL에 저장합니다. 기본 BM25 검색은 embedding model을
내려받지 않으며 메모리 서비스 계정이나 API key가 필요하지 않습니다. 파일은
**암호화되지 않습니다**. 모델 인증과 모델 제공사에 전달하는 문맥은 agent host가
관리합니다. 기관 포털, 메일 자동화, 비공개 거버넌스 시스템은 패키지에 포함되지
않습니다. [보안 안내](SECURITY.md)를 참고하세요.

## 검증 근거

**에이전트 기본 메모리 대비 추가 답변 품질 효용은 아직 입증되지 않았습니다.**
현재 근거는 우월성이나 SOTA 주장을 뒷받침하지 않습니다.

| 근거 | 확인 범위 |
|---|---|
| [Runtime 안내](docs/05-runtime.ko.md), tests와 [CI](.github/workflows/ci.yml) | 소프트웨어 계약과 설정된 검사. 새로운 실제 host 인증은 아님 |
| [Component 계약 보고서](benchmarks/pilots/component-ablation-20260715/README.md) | 작성된 결정론적 책임의 동작. LLM 답변 정확도가 아님 |
| [LongMemEval-S 검색 pilot](benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md) | 압축 keyword pointer가 전체 session BM25보다 recall을 잃음. Reader LLM 평가는 없음 |
| [비공개 시스템 운영 기록](evidence/operational-evidence.md) | 별도 시스템의 설계 경험. 공개 패키지 검증이 아님 |
| [비교 프로토콜](benchmarks/README.md) | 평가 설계. 기본 메모리 대비 효용 결론은 없음 |

## 문서와 지원

| 목적 | 안내 |
|---|---|
| 에이전트 저장·조회 절차 | [Companion skill](docs/companion-skill.md) |
| 기억 점검과 수정 이해 | [Self-monitoring](docs/memory-self-monitoring.md) |
| CLI·Python API 사용 | [Runtime](docs/05-runtime.ko.md) |
| 다른 MCP host 연결·연결 제거 | [MCP 안내](docs/07-mcp-server.ko.md) |
| 선택형 세션 자동화 | [Session loop](docs/08-autonomous-loop.ko.md) |
| 기억 수명주기와 뇌 기능 비유 | [Lifecycle](docs/02-memory-lifecycle.ko.md), [mapping](docs/01-the-mapping.md) |
| 고급 adapter와 로컬 관찰 화면 | [Adapters and observer](docs/06-adapters-and-observer.ko.md) |
| 설계 참조와 배포 이력 | [Governance](docs/03-governance-tiers.md), [principles](docs/04-principles.md), [schema](schema/), [templates](templates/), [examples](examples/), [changelog](CHANGELOG.md) |
| 근거 확인·기여·문제 보고 | [Evidence](evidence/README.md), [contributing](CONTRIBUTING.md), [issues](https://github.com/Hahyun-Lee/brain-ai-memory/issues) |

관리자: [Hahyun Lee](https://github.com/Hahyun-Lee). 인용 정보는 [CITATION.cff](CITATION.cff)에
있습니다. 코드와 companion은 MIT 라이선스이며 레포 사용에 marketplace 구매는 필요하지 않습니다.
