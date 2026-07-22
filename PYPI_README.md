# Brain-AI Memory — Stop Re-explaining Your Project

**Open a new Codex or Claude Code session and continue from the last one.**

Brain-AI Memory keeps the facts, decisions, exact values, and next steps you
choose on your computer. Records stay separated by project, changed facts keep
their source history, and the next session can receive a bounded handoff from
the previous one.

**Runs locally · No API key · No account · No database server**

[Source and full documentation](https://github.com/Hahyun-Lee/brain-ai-memory) ·
[한국어](https://github.com/Hahyun-Lee/brain-ai-memory/blob/main/README.ko.md) ·
[简体中文](https://github.com/Hahyun-Lee/brain-ai-memory/blob/main/README.zh-CN.md) ·
[Report a real use case or problem](https://github.com/Hahyun-Lee/brain-ai-memory/issues/new/choose)

![Past sessions are organized into the right project memory so the next AI session can continue.](https://raw.githubusercontent.com/Hahyun-Lee/brain-ai-memory/main/docs/assets/graphical-abstract.png)

## Try the local tour

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install brain-ai-memory

DEMO_HOME="$(mktemp -d)"
brain-ai --home "$DEMO_HOME" tour
```

The tour uses synthetic data in a disposable directory. It does not inspect or
import your files.

## Connect a real project

Install the agent-connection support once:

```bash
python -m pip install "brain-ai-memory[mcp]"
```

Then run setup from the project you want to continue across sessions:

```bash
cd /path/to/your/project
brain-ai setup codex --entity my-project
brain-ai setup codex --entity my-project --apply
```

Use `claude-code` instead of `codex` for Claude Code. The first command is a
pure preview. `--apply` creates one empty project entity when needed or reuses
an existing project entity, applies the shown project-scoped configuration,
and runs diagnostics. It does not import or approve a `MEMORY.md` file.

By default, setup enables automatic session recall and checkpoints. Choose
`--mode tools` when you want the host to decide when to call memory operations.

## When it is useful

Brain-AI Memory is meant for work where all three conditions hold:

1. The work continues across many sessions.
2. Facts, rules, or exact state change over time.
3. A stale or cross-project memory can cause a real mistake.

Examples include multi-project coding agents, months-long research workflows,
operations agents that track approvals and deployments, and teams that use both
Codex and Claude Code. A one-off chat, a short single-repository task, ordinary
document search, or a small `MEMORY.md` you can prune by hand usually does not
need this package.

## What it manages

- typed episodic and semantic records, exact state, rules, and session handoffs;
- stable project/entity scope so two similar projects do not share records by
  accident;
- source and lifecycle history when a newer fact replaces an older one;
- automatic source-drift checks that withhold stale imported records and prepare
  a review audit instead of silently treating them as current, while a stale
  procedural source places supported actions in a fail-closed review hold;
- local multilingual BM25 recall without downloading an embedding model; and
- optional project hooks for bounded recall, action checks, and checkpoints.

The automatic loop does not save raw prompts, raw tool output, assistant
messages, or edited file contents. The local store is not encrypted, so keep
`.brain-ai/` private and out of source control. See the
[security policy](https://github.com/Hahyun-Lee/brain-ai-memory/blob/main/SECURITY.md)
and
[automatic-session privacy boundary](https://github.com/Hahyun-Lee/brain-ai-memory/blob/main/docs/08-autonomous-loop.md)
before using sensitive records.

## Bring an existing MEMORY.md

Audit is preview-first and leaves the source file unchanged:

```bash
cd /path/to/your/project
brain-ai audit MEMORY.md --entity my-project
```

It identifies source-addressed entries, exact duplicates, and possible literal
conflicts. State, executable rules, and replacements stay unresolved until you
make an explicit review decision. The complete workflow is documented in the
[GitHub README](https://github.com/Hahyun-Lee/brain-ai-memory#readme).

## Evidence and limits

The public suite contains 135 deterministic tests covering the runtime,
adoption workflow, host connections, automatic loop, packaged restart/resume,
component contracts, and storage concurrency. Wheel and source distributions
are built and smoke-tested before publication.

Those checks establish packaging and integration behavior. They do not yet
show that Brain-AI Memory improves end-to-end LLM answers over RAG or a simpler
memory file. Reproducible results, including negative findings, are available
in the
[evidence section](https://github.com/Hahyun-Lee/brain-ai-memory#evidence-status).
