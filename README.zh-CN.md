[English](README.md) | [한국어](README.ko.md) | **简体中文**

# Brain-AI Memory — AI 代理的本地项目记忆

**帮助下一次 AI 对话从项目的当前决策继续。**

把 Codex 和 Claude Code 使用的项目记忆保存在你的电脑上。
例如，把“周五发布”替换为“周四发布”后，周四成为该项目的当前决策，旧决策仍保留在历史中。
通过 MCP 连接，也可以从现有 `MEMORY.md` 中导入选定事实，而不改写原文件。

**本地存储 · 项目范围 · 修改历史 · Python 3.10+ · MIT**

[本地试用](#本地试用) · [连接代理](#连接-codex-或-claude-code) ·
[配套 skill](docs/companion-skill.md) · [证据](#证据与限制)

## 适合谁？

如果工作跨越多个会话，而使用过时或属于其他项目的决策会造成实际错误，可以考虑使用：

| 工作场景 | 需要管理的记忆 |
|---|---|
| 用 Codex 或 Claude Code 开发多个项目 | 区分名称相近的项目，继续正确的未完成任务 |
| 长期实验或运营流程 | 已确认的值、来源及后续替换历史 |
| 构建有明确记忆流程的代理 | 在对话之外检查事实、更新和交接记录 |

如果手动维护一个小型 `MEMORY.md` 已经足够，就未必需要另一个运行时。
一次性聊天和普通文档搜索通常也不需要。

## 决策变了，下一个会话需要修正后的内容

以下为虚构的发布计划示例：

| 时间 | 用户或代理的操作 | 保留的记录 |
|---|---|---|
| 会话 1 | 在 Atlas 项目保存“周五发布” | 绑定项目的事实；导入内容还带有来源行号和 hash |
| 决策改变 | 明确用“周四发布”替换旧事实 | 周四成为该项目的当前事实，旧记录保留在历史中 |
| 会话结束 | 保存交接：“审查完成，下一步运行 staging” | Atlas 的摘要和下一步行动 |
| 会话 2 | 恢复 Atlas 并查询当前记录 | 同一范围内的交接和匹配的当前记忆 |

代理必须实际调用写入工具。安装 MCP 或阅读文件不会自动保存事实。
[配套 skill](skills/brain-ai-memory/SKILL.md) 提供保存、修正、验证和交接流程；
可执行运行时另行安装。

## 在记忆文件之外增加什么？

| 需求 | 显式操作 |
|---|---|
| 确认记录属于哪个项目 | 保存项目 ID，并将连接锁定到该项目 |
| 修正事实并保留历史 | 将旧事实标记为已替换，并保留来源 |
| 保存精确值 | 给值命名，与普通笔记分开保存 |
| 发现导入事实的依据发生变化 | 在可选循环中检查来源行是否改变，再重新审查 |
| 继续约定的工作 | 保存项目摘要和下一步行动，供下次继续 |

这里的**元认知是使用记忆之前先检查它**。代理可以查看所属项目、当前版本和来源。
来源变更检查由可选会话循环执行。信息是否真实、应保存哪项修正，仍由人或代理判断。
[记忆自我监测说明](docs/memory-self-monitoring.md) 解释了机制与限制。

## 本地试用

新安装请从临时目录开始。以下命令需要 Python 3.10+、POSIX shell 和 PyPI 访问权限。
已有运行时请复用现有环境。

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install "brain-ai-memory==0.7.0"
DEMO_HOME="$(mktemp -d)"
brain-ai --home "$DEMO_HOME" tour
```

该虚构演示涵盖项目绑定、查询、精确状态、事实替换、交接和可选动作检查。
它不会导入用户文件或连接代理，也不是答案质量提升的证据。

## 连接 Codex 或 Claude Code

| 模式 | 调用方 | 入口 |
|---|---|---|
| **Tools + 配套 skill** | 代理按显式流程调用 MCP 工具 | 下方设置，再[添加 skill](docs/companion-skill.md) |
| **可选会话循环** | 支持的 host hook 提供查询和 checkpoint 事件 | [自动会话记忆](docs/08-autonomous-loop.md) |

新建 **tools mode** 连接时，先创建项目内环境：

```bash
cd /path/to/your/project
umask 077
python3 -m venv .brain-ai/runtime/v0.7.0
source .brain-ai/runtime/v0.7.0/bin/activate
export BRAIN_AI_HOME="$PWD/.brain-ai"
.brain-ai/runtime/v0.7.0/bin/python -m pip install "brain-ai-memory[mcp]==0.7.0"
brain-ai setup codex --entity my-project --mode tools
# 检查预览后，再应用项目连接：
brain-ai setup codex --entity my-project --mode tools --apply
```

Claude Code 用户把 `codex` 换成 `claude-code`。Setup 创建或复用实体，并在 host 配置中
固定 Python 路径和本地 home。完成 host 审批后重新连接 MCP 或启动新项目会话。
将 `.brain-ai/` 排除在版本控制之外；保留现有运行时或循环配置，不要直接覆盖。

按[配套流程](docs/companion-skill.md#confirm-the-connection)检查真实写入结果并找回记录。
Tools mode 不安装自动 hook；skill 提供指令，但不强制代理调用工具。

## 导入现有 MEMORY.md

持续使用同一个本地 home 和项目名称：

```bash
cd /path/to/your/project
export BRAIN_AI_HOME="$PWD/.brain-ai"
brain-ai audit MEMORY.md --entity my-project
```

检查返回的 audit 及来源条目，然后使用命令实际返回的 ID：

```bash
brain-ai review AUDIT_ID
brain-ai review AUDIT_ID --approve-ready
brain-ai apply REVIEW_ID --yes
```

`--approve-ready` 接受无歧义的事实和事件，并跳过精确重复候选。
状态、可执行规则和替换必须显式审查。原 Markdown 文件保持不变。
未决条目、来源冲突和逻辑撤销请参阅[运行时指南](docs/05-runtime.md)。

## 兼容性与数据

本快速入门和配套 skill 针对**已发布的 v0.7.0**。该版本的精确状态查询需要
[skill 中的 numeric-hint 路径](skills/brain-ai-memory/SKILL.md#exact-values-on-v070)。
本地开发中的保存、范围和查询修正，以及状态投影和 cue delivery，不包含在该 wheel 中。
参阅[发布边界](docs/release-and-operating-boundary.md)。

记忆保存在本地 SQLite、JSON 和 JSONL 文件中。默认 BM25 不下载 embedding 模型，
不需要记忆服务账号或 API key。文件**未加密**。模型认证及发送给模型提供商的上下文
仍由代理 host 管理。软件包不包含机构门户、邮件自动化或私有治理系统。
参阅[安全说明](SECURITY.md)。

## 证据与限制

**尚未证实相比代理原生记忆能进一步提高答案质量，也没有 SOTA 结论。**

| 证据 | 支持的范围 |
|---|---|
| [运行时](docs/05-runtime.md)、测试和 [CI](.github/workflows/ci.yml) | 软件契约和配置的检查；不是新的真实 host 认证 |
| [组件契约报告](benchmarks/pilots/component-ablation-20260715/README.md) | 预先编写的确定性职责；不是 LLM 答案准确率 |
| [LongMemEval-S 检索 pilot](benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md) | 压缩关键词指针比完整会话 BM25 丢失更多 recall；未评估 reader LLM |
| [私有系统运行记录](evidence/operational-evidence.md) | 独立系统的设计经验；不是公开软件包验证 |
| [比较协议](benchmarks/README.md) | 评估设计；没有已完成的原生记忆优势结论 |

## 文档与帮助

- [配套 skill](docs/companion-skill.md) · [记忆检查与修正](docs/memory-self-monitoring.md)
- [CLI / Python API](docs/05-runtime.md) · [MCP 配置与移除](docs/07-mcp-server.md)
- [可选会话循环](docs/08-autonomous-loop.md) · [生命周期](docs/02-memory-lifecycle.md) · [脑功能映射](docs/01-the-mapping.md)
- [适配器与本地观察器](docs/06-adapters-and-observer.md) · [治理](docs/03-governance-tiers.md) · [设计原则](docs/04-principles.md)
- [Schema](schema/) · [模板](templates/) · [示例](examples/) · [更新记录](CHANGELOG.md)
- [证据](evidence/README.md) · [贡献指南](CONTRIBUTING.md) · [问题反馈](https://github.com/Hahyun-Lee/brain-ai-memory/issues)

维护者：[Hahyun Lee](https://github.com/Hahyun-Lee)。引用信息见 [CITATION.cff](CITATION.cff)。
代码和配套 skill 采用 MIT 许可证；使用本仓库不需要购买 marketplace 商品。
