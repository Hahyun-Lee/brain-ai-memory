[English](README.md) | [한국어](README.ko.md) | **简体中文**

# Brain-AI Memory — 不要每次重新解释你的项目

**打开新的 Codex 或 Claude Code 会话，也能从上一次工作继续。**

Brain-AI Memory 把你选择保留的事实、决定、精确数值和下一步行动，按项目
分别存放在本地，避免不同项目的记忆混在一起。开启会话自动化后，下一次会话
会收到相关记忆和上一次的交接内容。事实发生变化时，旧版本及其来源仍然可追溯。
现有的 `MEMORY.md` 不会被修改。

**本地运行 · 不需要 API 密钥 · 不需要账号 · 不需要单独安装数据库**

[![CI](https://github.com/Hahyun-Lee/brain-ai-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/Hahyun-Lee/brain-ai-memory/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Hahyun-Lee/brain-ai-memory)](https://github.com/Hahyun-Lee/brain-ai-memory/releases/latest)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**[60 秒体验](#60-秒体验)** · [使用现有的 MEMORY.md](#导入现有的-memorymd) ·
[连接 Codex 或 Claude Code](#连接-codex-或-claude-code) · [查看证据](#证据状态)

<p align="center">
  <img src="docs/assets/graphical-abstract.png" width="920" alt="把过去会话中混杂的记录整理到正确项目记忆中，让下一次 AI 会话继续工作；下方是可选的安全检查。">
</p>

<p align="center">
  过去的会话 → 当前项目的记忆 → 下一次会话继续工作。<br>
  可选：命令违反已批准规则时，在执行前拦截它。
</p>

> 搜索可以找到相似的旧笔记。Brain-AI Memory 还会记录它属于哪个项目、是否
> 已被更新的事实替代，以及下一次会话应该继续做什么。

## 60 秒体验

先从 PyPI 安装软件包，再在临时目录中运行 tour，不会触碰真实的记忆文件：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install brain-ai-memory
```

如需从源码安装，请 clone 本仓库，并在仓库内运行 `python -m pip install .`。

```bash
DEMO_HOME="$(mktemp -d)"
brain-ai --home "$DEMO_HOME" tour
```

```text
Brain-AI Memory: current memory and a session handoff
1  BIND     Atlas 2.1 → belongs_to → Atlas
2  RECALL   Atlas 2.1 release day is Thursday.
3  STATE    open_reviews = 3
4  UPDATE   Friday → superseded by → Thursday
5  HANDOFF  checkpoint handoff_...
Optional action checks
6  GUARD    blocked: release approval is required before production deployment
7  FALLBACK completed after 2 attempts
```

这个 tour 只证明本地软件可以运行；它不会导入你的文件，也不代表代理已经
开始自动使用记忆。

**已验证内容：**完整的 137 个测试在 Python 3.12 上运行；核心 runtime 和
adoption workflow 也在 Python 3.10、3.11 上运行。clean wheel 测试覆盖真实的
进程重启与恢复、子进程 host hook 设置、自动 checkpoint/resume，以及 20/20
component contracts。这是安装与集成证据，不是“能让 LLM 回答得更好”的声明。

## 适合谁？

以下三个条件同时成立时，Brain-AI Memory 才真正有用：

1. 工作会跨越多个会话继续进行。
2. 事实、规则或精确状态会不断变化。
3. 使用过时记忆或其他项目的记忆，可能造成实际错误。

典型场景包括：在多个项目间工作的 coding agent、持续数月的研究工作流、
跟踪工单/审批/部署状态的运维 agent，以及同时使用 Codex、Claude Code 和
多个子 agent 的编排系统。

一次性聊天、一个仓库里的短任务、普通文档搜索，或者手动整理 `MEMORY.md`
已经足够的工作，不一定需要它。

默认检索使用 SQLite 上透明的本地多语言 BM25，不会下载 embedding model。
Vault 和 Smart Connections 后端是可选的。tools-only 模式等待 host 主动调用。
可选的自动模式只暂时使用当前 prompt 来选择同一项目的记录，提供有大小上限的
上下文，并记录观察到的变化；它不会保存原始对话。

## 导入现有的 MEMORY.md

如果没有先运行 tour，可以直接安装基础包：

```bash
python -m pip install brain-ai-memory
```

在拥有该记忆文件的项目中固定项目根目录和本地 runtime home，然后给这些记录
一个稳定的项目范围：

```bash
cd /path/to/your/project
export PROJECT_ROOT="$PWD"
export BRAIN_AI_HOME="$PROJECT_ROOT/.brain-ai"
brain-ai audit MEMORY.md --entity my-project
```

```text
Audited /path/to/MEMORY.md
Entity: my-project
Entries: 84

Ready to import:       63
Needs review:          13
Duplicate candidates:  8
Possible conflicts:     3

Review plan: /path/to/your/project/.brain-ai/workflows/audits/audit_0123456789abcdef.json
Source file and memory store unchanged.
Next: brain-ai --home /path/to/your/project/.brain-ai review audit_0123456789abcdef
```

检查带有来源地址的条目，批准没有歧义的条目，然后应用保存的 review：

```bash
brain-ai review audit_0123456789abcdef
brain-ai review audit_0123456789abcdef --approve-ready
brain-ai apply review_0123456789abcdef --yes
```

`--approve-ready` 会批准普通 semantic/episodic 条目，并跳过完全重复的候选。
状态值和可执行规则候选会保持未解决。Audit 不会猜测一个事实是否替代另一个
事实；如果这正是你的意图，请对该条目明确使用 `--supersede`。项目范围的
supersession 只能连接同一项目中的旧记录，不会停用全局记录或其他项目的记忆。
Apply 只写入选定的 Brain-AI home，不会修改 `MEMORY.md`。

如果当前目录中有 `.claude/MEMORY.md` 或 `MEMORY.md`，可以省略路径。Discovery
不会遍历 home 目录或 provider 日志。只想预览、连 audit plan 都不保存时，使用
`brain-ai audit ... --no-save`。

runtime home 只包含普通的 SQLite、JSON 和 JSONL 文件，软件不会加密它们。请
把 `.brain-ai/` 保持私有，不要提交到源代码仓库，并根据记录的敏感程度安排
权限和备份。

## Audit 会判断什么，不会判断什么

Audit 把不可执行的 Markdown 解析成带有原始路径、行号范围和内容 hash 的条目。
它会报告规范化后的完全重复项，以及同一显式 key 对应不同 literal value 的
潜在冲突。这些只是复核提示，不是对哪句话真实或当前有效的判断。

| 复核选择 | 授权方式 |
|---|---|
| 普通事实或事件 | `--approve-ready`，或明确使用 `--set ITEM=semantic\|episodic` |
| 精确状态 | 对 `key: value` 条目明确使用 `--set ITEM=state` |
| 程序规则 | 明确使用 `--rule ITEM=SAFE_PATTERN` 和 `--rule-effect warn\|block` |
| 替代旧事实 | 明确使用 `--supersede ITEM=MEMORY_ID` |
| 不导入 | 明确使用 `--set ITEM=skip`，或由完全重复候选自动 skip |

Audit 不会根据日期、措辞或文件顺序推断真伪或过时。第一次成功 apply 之前，
只要源文件或类型化存储发生变化，操作就会停止并要求重新 audit。完成后再次
应用同一个 review 是幂等空操作，receipt 会报告源文件之后是否发生变化。

应用后的 batch 可以明确回滚：

```bash
brain-ai rollback batch_0123456789ab --yes
```

Rollback 会在安全范围内恢复之前的 active view。这是逻辑回滚，不是物理删除：
源文件、导入 receipt 和 provenance 证据都会保留。

## 连接 Codex 或 Claude Code

如果希望新会话自动回忆同一项目，并在有变化时留下 checkpoint，可以使用自动
模式。任何写入前都会先显示预览。

```bash
# 安装一次 agent 连接支持
python -m pip install "brain-ai-memory[mcp]"

# 在使用这份记忆的项目中执行
cd /path/to/your/project
brain-ai setup codex --entity my-project
brain-ai setup codex --entity my-project --apply
```

如需从源码安装，请在仓库内运行 `python -m pip install ".[mcp]"`，替代上面的安装
命令。

使用 Claude Code 时，把 `codex` 替换成 `claude-code`。如果已经导入
`MEMORY.md`，setup 会复用已有的项目 entity，不会自行导入或批准 memory。第一条
命令只是预览，不会写入任何内容。`--apply` 只在需要时创建空的项目 entity，应用
同一份已检查的 config diff，并运行 `doctor`。Codex 会要求你信任准确的项目
hooks；请先用 `/hooks` 检查，再开始新的会话。安装后 `doctor` 会显示
`configured`；只有观察到一次真实的 start → prompt → stop 循环后才会显示
`active`。

自动模式严格绑定到项目。会话开始时，它提供最新 handoff 和有字节上限的当前
记录。每个 prompt 只会临时用于同一项目的相关记录检索。它不会保存原始 prompt、
原始 tool output、assistant 消息或编辑过的文件内容，也不会自行把一句话提升为
事实、规则或精确状态。完整的事件流、隐私边界、host 差异和卸载命令见
[Automatic session memory](docs/08-autonomous-loop.md)。

如果已经批准并导入的 `MEMORY.md` 发生变化，loop 会在会话开始时和支持的文件编辑后
重新核对 source fragment。当前文件已不再支持的事实、状态和规则仍保留在审计历史中，但不会进入
自动 recall。如果导入规则的源文件失效，支持的操作会进入 fail-closed review hold，
不会因为文本变化而悄悄移除已批准的 guard。修改后的文件会生成普通 audit；新的或替换的条目仍需走
现有 review 与 reconsolidation 流程，没有变化的 fragment 可以继续使用。这样能
阻止旧记忆冒充当前事实，也不会让程序自行判断一句话是否为真。

如果只需要按需调用 memory tools，请明确选择 tools 模式：

```bash
brain-ai setup codex --entity my-project --mode tools
brain-ai setup codex --entity my-project --mode tools --apply
```

tools-only 模式由 Codex 或 Claude Code 决定何时 recall、save 和 checkpoint。
需要高级配置时仍可使用底层 `connect` 命令；它的 `--scope user` 只适用于有意
配置的 tools-only 连接。`disconnect` 同样先显示预览，只有加上 `--apply` 才会
修改 host 配置。

生成的项目连接会用绝对路径固定当前 Python 解释器和 Brain-AI home，即使 shell
不再处于虚拟环境中也能启动。它是机器本地配置，提交或分享 host 配置前请检查
这些路径。生成的连接会把每次 memory 调用锁定到选定项目；试图读写其他项目
会被拒绝，而不是悄悄切换范围。

tools-only 模式可以在项目的 `AGENTS.md` 或 `CLAUDE.md` 中加入同等说明：

```text
For cross-session work, call brain_resume first and brain_context before using
project facts. Save only durable decisions, events, or changed state with
brain_remember. Before handing work to another session, call brain_checkpoint
with a short summary and concrete next_actions.
```

## 交接与恢复

在会话结束时记录已经确定的总结和具体的下一步行动。下一次会话可以读取同一
entity 的最新 handoff：

```bash
brain-ai handoff --entity my-project \
  --summary "Release review completed; Thursday is the approved date" \
  --next "Run the staging deploy"
brain-ai resume --entity my-project
```

连接后的 agent 也可以用 `brain_checkpoint` 和 `brain_resume` 做同样的事；项目
连接会提供默认 entity。第一次 handoff 之前，`resume`/`brain_resume` 返回
`status: not_found`、空 summary 和空 next_actions，这是正常的首次运行结果。

## 使用它之后会有什么不同？

| 你遇到的失败 | Brain-AI Memory 增加的内容 |
|---|---|
| `MEMORY.md` 把事实、事件、规则和状态混在一起 | 带来源地址的 audit、显式 review 和导入 receipt |
| 一个项目的记忆泄漏到另一个项目 | 记录绑定到 entity，recall 只在该范围内进行 |
| 已复核的事实替代旧事实 | 从当前项目的 active view 移除旧版本，同时保留来源历史 |
| 模型从文字描述中估算本来已知的数值 | 把精确状态保存在类型化存储中 |
| 重复发生的经验一直埋在会话日志里 | 先 review，再决定是否提升为知识或规则 |
| 新旧事实同时处于有效状态 | reconsolidation 生成带来源的替代版本 |
| 下一次会话没有上次的决定 | 按项目隔离的 handoff，带总结和未完成工作 |

如果你正在构建跨会话工作的 coding、research、operations 或 assistant agent，
可以从这里开始。普通文档搜索或一次性聊天通常只用 RAG 就够了。

## 它管理哪些内容？

| 记忆管理职责 | 当前实现 |
|---|---|
| 现有 Markdown memory | audit、review 并导入批准的条目，保留逐行来源且不改原文件 |
| 选中的证据 | 保存明确的 memory write；自动模式只可保存有界的相对编辑目标元数据，不保存文件内容或原始 transcript |
| working context | 重建按 entity 隔离的上下文；自动模式提供硬性 6,000 字节上限和来源标识 |
| episodic memory | 保存带 ingest 时间的事件、entity binding 和导入证据 |
| semantic memory | 保存带来源的可复用知识，只有显式 supersession 才会更新事实 |
| procedural memory | 保存规则；episode 到 rule 的提升必须经过预览和批准 |
| exact state | 用类型化存储保存可直接查询的数值，不让模型从文字描述中估算 |
| lifecycle 与 handoff | 记录 consolidation、reconsolidation、active/inactive、rollback、handoff/resume 和幂等 checkpoint |
| host connection | 预览并写入 project-locked connection；可选 hook 自动处理 recall、action check、acknowledgement 和 checkpoint |

所有 store 都使用 entity link、source label 和 component schema。tools-only 模式
不会收集 provider session，也不会自行把 memory 放进模型上下文。文件压缩、拆分、
物理删除、加密和备份仍由 host 或使用者负责。

## 为什么借鉴大脑的功能分工？

这里的“大脑”只是设计辅助，不是生物学等价声明。它帮助我们把 episode、事实、
规则、精确状态和 action check 分开，让每类失败都能单独调试。你也可以只使用
这些软件约定，不采用脑区名称。详见 [mapping 及其边界](docs/01-the-mapping.md)。

当前测试包括 44 个 adoption-workflow、27 个 runtime、5 个 ablation、1 个 packaged
restart/resume、23 个 host-integration、33 个 automatic-loop，以及 4 个 storage
durability/concurrency 测试，共 137 个。它们还没有证明真实 LLM agent 的端到端答案
优于 RAG 或更简单的 memory system。

## 从你已经遇到的问题开始

这些问题常出现在跨多个会话工作的 coding、research、operations 和 assistant agent：

- “明明记录过这个决定，为什么下一次会话还原不出来？”
- “检索到的笔记相关，但已经被新事实替代了。”
- “这个事件属于另一个项目或 entity。”
- “同样的经验重复发生，却从未变成可复用的知识。”
- “精确数值明明存在，模型却从 prose 里估算。”
- “记忆索引不断变大，却没人知道该 consolidation、archive 还是保留什么。”

从你已经看到的失败开始，不必一次采用全部架构：

| 观察到的现象 | 先检查 | 最小的有用改动 |
|---|---|---|
| 已确定的上下文丢失或绑定到错误事件 | episodic memory (HC) | 加入 ingest-time event/entity binding |
| 一个项目的记忆泄漏到另一个项目 | entity scope 与 relation | 绑定稳定 entity，只在该范围查询 |
| 检索相关但内容过时 | semantic memory (ATL) | 检查新鲜度，冲突时 reconsolidate |
| 重复 episode 从未变成知识或 procedure | consolidation | 提升前必须 review |
| 新旧事实同时 active | reconsolidation | supersede 旧记录，同时保留旧行与来源 |
| 模型猜测本可直接读取的值 | exact state (IPS) | 查询类型化状态存储 |
| 永久加载的索引越来越大 | memory lifecycle | 保留有界索引并记录 archive/migration 决定 |
| 下一次会话无法继续之前的决定 | checkpoint/handoff | 保存按项目隔离的总结和待处理的生命周期候选 |

## 它和 RAG、hook、harness 有什么不同？

它们可以一起使用，但负责的事情不同：

| 方式 | 主要问题 | Brain-AI Memory 的补充 |
|---|---|---|
| RAG | 找到相似文本 | 项目范围、来源、版本、精确状态和 handoff |
| hook | 在事件边界运行代码 | 把 recall、action check、receipt 和 checkpoint 连接起来 |
| harness | 约束工具执行流程 | 只作为可选的 action boundary，不替代事实审核 |
| Brain-AI Memory | 管理跨会话的类型化记忆及其生命周期 | audit、scope、supersession、consolidation、handoff 和可检查证据 |

它不是把 RAG、hook 或 harness 换一个名字，而是把这些边界放到记忆类型和
lifecycle 中，并明确哪些变化需要人或 host 审核。

## 架构如何工作？

规范映射是七个 component 和两个 lifecycle channel：五个 memory role（PFC working/
executive、HC episodic、ATL semantic、BG procedural-rule、CB procedural-execution），
以及两个 supporting role（TH gating、IPS exact numerical state）。Consolidation 和
reconsolidation 是 transfer channel，不是额外 component。当前公开实现的核心是类型化记忆
和 lifecycle；控制面不会把它变成 harness library。

| 层 | Component | 当前公开实现负责什么 | 它帮助诊断的失败 |
|---|---|---|---|
| memory | PFC | 将查询路由到候选 store，重建按范围隔离的 working-memory 候选 | 选错 store 或 entity scope |
| memory | HC | episodic event、stable entity、alias、relation、binding | 事件缺失或绑定错误 |
| memory | ATL | 带来源和替代版本的当前 semantic knowledge | 检索相关但过时或来源错误 |
| memory | BG | 存储 procedural rule，批准 episode-to-rule promotion | 可复用规则没有被捕获或选择 |
| memory | CB | 可执行 procedure 表示；步骤由 host 提供 | procedure 仍停留在 prose 或 fallback 中途停止 |
| computation | IPS | 按 entity 隔离的精确数值状态 | 模型从文字描述中猜数量 |
| control | TH | 在公开 runtime 中检查 host 提议的 action | 不安全 action 到达 tool boundary |
| lifecycle | consolidation | 预览 episode → knowledge/rule promotion，只在请求时应用 | 重复经验没有变成可复用 memory |
| lifecycle | reconsolidation | 生成带来源的 semantic 替代版本 | 旧知识和当前知识同时处于有效状态 |

脑启发的 TH 是更广义的 input gating；clean-room runtime 只实现并测试了狭义的
proposed-action check，不声称过滤模型全部 prompt 或 provider input。

### 自动运行什么？什么仍需审核？

tools-only 模式把 recall、保存和 handoff 时机交给 host。可选的自动模式会在确定的
session edge 执行：启动和 prompt 时的有界 project recall、支持的 Bash action check、
成功编辑后的有界目标元数据、dirty-only checkpoint、resume 和 acknowledgement。

带判断的 memory 变化仍然明确可审：导入前 review `MEMORY.md`；事实、规则、精确状态
或替代版本必须通过明确 memory operation 写入；host 仍负责决定和执行工作；promotion、
supersession、archive、split、compact、migration 和 logical deletion 都是可审的
lifecycle 决定。Provider transcript、物理文件保留、加密、备份和验证删除由 host 或
使用者负责。

详见 [Automatic session memory](docs/08-autonomous-loop.md) 和 [memory lifecycle](docs/02-memory-lifecycle.md)。

## 证据状态

不同证据回答不同问题：实际运行记录、memory retrieval 测试、软件行为测试，以及
仍未获得的结果不能混为一谈。

| 问题 | 当前证据 |
|---|---|
| 架构是否真的实现并使用过？ | **是。自 2026-04-20 起，在 13 个项目 memory index 上运行** |
| 是否有持续的运行暴露？ | **是。2026-06-10 至 2026-07-14 有 419 个 instrumented session、6,360 万 tokens** |
| semantic retrieval 是否优于 live grep control？ | **提示性 aggregate 结果：HIT@10 69.0% → 88.8%，n=116** |
| equal-budget graph augmentation 是否有帮助？ | **提示性 aggregate 结果：HIT@10 86.2% → 91.9%，n=690 sources** |
| 是否在公开 benchmark 上比较过？ | **公开 LoCoMo 数据的 aggregate 结果：GTE 62.1%、BM25 57.0%、graph-lite 51.9%，n=1,531** |
| 压缩 pointer index 是否容纳更多条目？ | **是。确定性 capacity simulation** |
| 简单 compact pointer 是否保持检索质量？ | **否。当前 keyword pointer 用体积换取 recall** |
| packaged workflow 是否能经受 MCP process restart？ | **是。CI 覆盖 review → apply → 配置 → stdio 调用 → checkpoint → 新进程 resume；这是集成证据，不是答案质量证据** |
| 已安装的自动 loop 是否能 recall、checkpoint、resume？ | **是。在 clean-wheel subprocess fixture 中验证；真实 host 的长期现场研究仍缺失** |
| lifecycle 是否提高真实 LLM agent 的答案准确率？ | **尚未测量** |
| 完整架构是否优于 RAG、long context 或其他 memory system？ | **尚未测量** |
| latency、token cost、冲突处理和 abstention 是否改善？ | **尚未测量** |
| 是否能推广到多个组织？ | **未知。还没有多组织复现** |
| 十个机制是否执行各自的 contract？ | **只证明契约符合性：all-ten 20/20，flat retrieval control 1/20；不代表答案质量更高** |

### 公开检索实验的负面结果

在 500 个清理后的 LongMemEval-S 问题上，用相同 top-3 预算比较 recent sessions、
full-session BM25 和 compact keyword pointer：

| 条件 | answer-session recall@3 | 平均索引源文本 |
|---|---:|---:|
| 最近 3 个 session | 7.5% | 无 search index |
| full-session BM25 | **86.1%** | 493,948 chars |
| 48-keyword pointer BM25 | 66.2% | 17,691 chars |
| 96-keyword pointer BM25 | 71.0% | 34,368 chars |

96-keyword pointer 少索引了 93.0% 的源文本，但 recall 下降了 15.0 个百分点。
这说明朴素的 keyword compression 不够。该实验没有 reader LLM，因此不支持 QA、
reasoning 或完整架构的结论。详见 [实验记录](benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md)。

### 还需要测试什么？

最缺少的是受控的端到端 memory-management QA 比较：在相同 reader 和预算下，agent
能否更可靠地保留、检索、更新、隔离、拒答和恢复？下一次 release-grade 运行会固定
reader model、prompt、context budget、dataset split 和 scoring procedure，比较：

1. 不使用外部 memory；
2. append-only 或 full-history memory；
3. summarization/compaction；
4. 标准 retrieval baseline；
5. Brain-AI lifecycle reference implementation。

主 benchmark 是 [LongMemEval](https://github.com/xiaowu0162/LongMemEval)；后续会用
[MemoryAgentBench](https://github.com/HUST-AI-HYZ/MemoryAgentBench) 检查 retrieval、
test-time learning、long-range understanding 和 conflict resolution。
在受控 reader-model 协议完成前，不会加入新的 top-line performance claim。

## 路线图

当前版本是可安装的本地类型化 memory kernel，以及面向 Codex 和 Claude Code 的可选
项目级 session loop。它自动安排 recall 和 checkpoint 时机，但不是后台服务，
也不会从 transcript 自动推断真相。计划包括：

1. 增加长期 latency、contention、retry 和真实 host 兼容性测试；
2. 提供更清楚的 lifecycle review queue 和选择/省略原因；
3. 在当前字节上限之外增加 token-aware budget，并在相同预算下测量 retrieval 与 reader accuracy；
4. 只在 project identity、event semantics 和 ownership 能保持明确时扩展 host adapter；
5. 提供 compact、split、archive 和 verified-delete adapter，并测试 retention workflow。

共享部署的认证、领域 ontology 推理和 entity merge/versioning 属于后续加固工作。
当前范围是**可安装、先审核的本地 memory system，带受监督的自动会话 loop**，不是
自动真相引擎，也不是多用户 memory service。

## 相关工作

- **CoALA：**提供 working、episodic、semantic 和 procedural taxonomy，本仓库大体采用这套分类。
- **MemGPT：**提供受限主上下文与外部上下文之间的自主 paging；本仓库尚未实现 autonomous paging。
- **Generative Agents：**使用 memory stream 和 reflection process，与这里的 consolidation channel 有相似之处。
- **Complementary Learning Systems：**以及 working-memory 研究，为快速 episodic / 较慢 semantic 的区分提供动机。

这些是定性比较。现有运行记录、内部 A/B 结果和公开 retrieval pilot 都没有证明完整架构
优于这些系统。

## 文件导航

| 路径 | 内容 |
|---|---|
| [docs/01-the-mapping.md](docs/01-the-mapping.md) | 七个 component 与两个 channel |
| [docs/02-memory-lifecycle.md](docs/02-memory-lifecycle.md) | 四种表示、七个操作、handoff 与 health metrics |
| [docs/03-governance-tiers.md](docs/03-governance-tiers.md) | advisory、guarded、enforced tiers |
| [docs/05-runtime.md](docs/05-runtime.md) | 可安装 kernel、store、routing、lifecycle 和 action bridge |
| [docs/06-adapters-and-observer.md](docs/06-adapters-and-observer.md) | Smart Connections compatibility 与 clean-room observer |
| [docs/07-mcp-server.md](docs/07-mcp-server.md) | 不绑定特定 provider 的 setup 与 security boundary |
| [docs/08-autonomous-loop.md](docs/08-autonomous-loop.md) | 自动 recall、action check、checkpoint、host setup 和 privacy |
| [src/brain_ai_memory/](src/brain_ai_memory/) | Python runtime 实现 |
| [tests/](tests/) | kernel、adapter 和 contract tests |
| [CHANGELOG.md](CHANGELOG.md) | release 变更与证据边界 |
| [templates/](templates/) | memory、rule、hook skeleton |
| [examples/](examples/) | 使用合成数据的最小示例 |
| [evidence/](evidence/) | 运行快照、内部 A/B 摘要和 capacity simulation |
| [benchmarks/](benchmarks/) | memory evaluation protocol 与 pilots |

## 在真实 agent 上试用

告诉我们你使用哪一个 host，以及希望解决哪一种反复出现的 memory failure。
如果记忆仍然过时、跨项目混用或无法恢复，请提交 [issue](https://github.com/Hahyun-Lee/brain-ai-memory/issues)。
如果它解决了你一直遇到的问题，给个 star 能帮助更多人找到它。

## 贡献

唯一的硬规则是 clean-room（洁净室）：真实个人数据和敏感数据不得进入仓库。详见
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全

请通过 GitHub 的 private vulnerability reporting 报告漏洞，不要公开提交 issue。
详见 [SECURITY.md](SECURITY.md)。

## 引用

如果这个架构或评估协议对你的工作有帮助，请使用 [CITATION.cff](CITATION.cff) 中的 metadata。
