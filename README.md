**English** | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

# Brain-AI Memory

**Project memory you can inspect, correct, and carry into the next session.**

Keep decisions, exact values, corrections, and next actions in a local store
that Codex or Claude Code can query. Bind records to a project, replace an old
fact with an explicit correction, and retain the source history. Import
selected entries from an existing `MEMORY.md` without rewriting it.

**Local Python runtime · SQLite and BM25 · Python 3.10+ · MIT**

[![CI](https://github.com/Hahyun-Lee/brain-ai-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/Hahyun-Lee/brain-ai-memory/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Hahyun-Lee/brain-ai-memory)](https://github.com/Hahyun-Lee/brain-ai-memory/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Try it locally](#try-it-locally) · [Connect your agent](#connect-codex-or-claude-code) ·
[Companion skill](docs/companion-skill.md) · [Evidence](#evidence-status)

## Is it for you?

Consider it when work spans sessions and using an old or wrong-project decision
can cause a real mistake:

| Your work | The memory you need to manage |
|---|---|
| Coding across several projects in Codex or Claude Code | Keep similar project names separate and resume the right unfinished task. |
| A long-running experiment or operational workflow | Keep an approved value, its source and its replacement history. |
| Building an agent with an explicit memory workflow | Inspect stored facts, updates and handoffs outside the model's conversation. |

A small `MEMORY.md` that you can maintain by hand may be enough. One-off chats
and ordinary document search usually do not need another memory runtime.

## A decision changes. The next session needs the correction.

Synthetic example:

| Moment | What you or the agent do | What the store preserves |
|---|---|---|
| Session 1 | Save “Atlas releases Friday” in the Atlas project. | A project-bound fact. Imported notes also carry source lines and hashes. |
| Decision changes | Explicitly supersede it with “Atlas releases Thursday.” | Thursday becomes active for that project; the old row remains traceable. |
| Session ends | Save a handoff: “Review complete; run staging next.” | A summary and next actions for Atlas. |
| Session 2 | Resume Atlas and query its current records. | The scoped handoff and matching current memory. |

The agent must perform the writes. Installing an MCP server or reading a file
does not save its facts. The [companion skill](skills/brain-ai-memory/SKILL.md)
teaches capture, correction, verification and handoff; it uses a separately
installed MCP runtime.

## What this adds to a memory file

| Need | Explicit operation |
|---|---|
| Know which project owns a record | Entity bindings and a project-locked connection. |
| Replace a fact without losing its history | Explicit supersession and source provenance. |
| Preserve an exact value | A scoped state key, separate from prose. |
| Notice changed support for an imported fact | Source-fragment checks in the optional session loop and a review path. |
| Continue the agreed work | Project-scoped checkpoint and resume. |

These operations support **metacognition: checking the memory being used and
recording an authorized correction**. The runtime provides scope and stored
status; the optional loop checks supported source changes. The user or
integrating agent still decides what is true and what should replace it. See
[memory self-monitoring](docs/memory-self-monitoring.md) for the mechanism and
its limits.

## Try it locally

For a new installation, use a disposable directory. These commands require
Python 3.10+, a POSIX shell and access to PyPI. Reuse your existing environment
if the runtime is already set up.

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install "brain-ai-memory==0.7.0"
DEMO_HOME="$(mktemp -d)"
brain-ai --home "$DEMO_HOME" tour
```

The synthetic tour exercises project binding, recall, exact state, a corrected
fact and a handoff, followed by optional action checks. It does not import your
files, connect an agent or demonstrate better answers.

## Connect Codex or Claude Code

| Mode | What invokes it | Start here |
|---|---|---|
| **Tools + companion skill** | The agent follows explicit instructions and calls MCP tools. | Setup below, then [add the companion](docs/companion-skill.md). |
| **Optional session loop** | Supported host hooks supply recall and checkpoint events. | [Automatic session memory](docs/08-autonomous-loop.md). |

For a new **tools-mode** connection, first create a project-local environment:

```bash
cd /path/to/your/project
umask 077
python3 -m venv .brain-ai/runtime/v0.7.0
source .brain-ai/runtime/v0.7.0/bin/activate
export BRAIN_AI_HOME="$PWD/.brain-ai"
.brain-ai/runtime/v0.7.0/bin/python -m pip install "brain-ai-memory[mcp]==0.7.0"
brain-ai setup codex --entity my-project --mode tools
# Inspect the preview, then apply that project-local connection:
brain-ai setup codex --entity my-project --mode tools --apply
```

Use `claude-code` in place of `codex` for Claude Code. Setup creates or reuses
the entity and pins the Python interpreter and local home in host configuration.
Complete host approval and reconnect the MCP server or start a fresh project
session. Keep `.brain-ai/` out of source control. Preserve an existing runtime
or loop configuration instead of overwriting it.

Use the [companion's save-and-recall routine](docs/companion-skill.md#confirm-the-connection)
to inspect a write result and retrieve the saved record before treating it as
available next session. Tools mode installs no automatic hooks. The skill
supplies instructions; it does not enforce tool use.

## Adopt an existing MEMORY.md

Use one local home and a stable project name throughout the workflow:

```bash
cd /path/to/your/project
export BRAIN_AI_HOME="$PWD/.brain-ai"
brain-ai audit MEMORY.md --entity my-project
```

Inspect the returned audit and its source-addressed entries. Substitute the
IDs actually returned by your commands:

```bash
brain-ai review AUDIT_ID
brain-ai review AUDIT_ID --approve-ready
brain-ai apply REVIEW_ID --yes
```

`--approve-ready` accepts unambiguous semantic/event entries and skips exact
duplicate candidates. State, executable rules and replacements require explicit
review choices. The original Markdown file is unchanged. See the
[adoption and rollback guide](docs/05-runtime.md#adopt-an-existing-markdown-memory-file)
for unresolved entries, source conflicts and logical undo.

## Compatibility and data

This quickstart and companion target **published v0.7.0**. Exact-state queries
need the numeric-hint route in the
[companion](skills/brain-ai-memory/SKILL.md#exact-values-on-v070). Local
capture/scope/recall changes, status projections and cue delivery are not part
of that wheel. See [release boundaries](docs/release-and-operating-boundary.md).

Memory is stored locally in SQLite, JSON and JSONL. The default retriever uses
BM25; it downloads no embedding model and needs no memory-service account or
API key. The files are **not encrypted**. Your agent host still controls model
authentication and any context sent to its model provider. The package does
not include institutional portals, email automation or private governance
systems. See [security and disclosure](SECURITY.md).

## Evidence status

**Added answer-quality benefit over native agent memory is not established.**
Use the software for the explicit controls you need; current evidence does
not justify a superiority or SOTA claim.

| Evidence | What it supports |
|---|---|
| [Runtime reference](docs/05-runtime.md), tests and [CI](.github/workflows/ci.yml) | Software contracts and configured checks; not a new live-host certification. |
| [Component contract report](benchmarks/pilots/component-ablation-20260715/README.md) | Authored deterministic responsibilities; not LLM answer accuracy. |
| [LongMemEval-S retrieval pilot](benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md) | Compact keyword pointers lost recall versus full-session BM25. No reader LLM was evaluated. |
| [Private-system operating record](evidence/operational-evidence.md) | Experience from a separate system; not validation of this package. |
| [Comparison protocol](benchmarks/README.md) | Evaluation design; no completed matched native-memory advantage. |

## Documentation and help

| Goal | Guide |
|---|---|
| Give an agent a save/recall procedure | [Companion skill](docs/companion-skill.md) |
| Understand memory checking and correction | [Self-monitoring](docs/memory-self-monitoring.md) |
| Use the CLI or Python API | [Runtime reference](docs/05-runtime.md) |
| Configure another MCP host or remove a connection | [MCP integration](docs/07-mcp-server.md) |
| Add optional session automation | [Session loop](docs/08-autonomous-loop.md) |
| Understand lifecycle and brain-inspired responsibilities | [Lifecycle](docs/02-memory-lifecycle.md), [mapping](docs/01-the-mapping.md) |
| Use advanced adapters and the local observer | [Adapters and observer](docs/06-adapters-and-observer.md) |
| Browse design references and release history | [Governance](docs/03-governance-tiers.md), [principles](docs/04-principles.md), [schema](schema/), [templates](templates/), [examples](examples/), [changelog](CHANGELOG.md) |
| Inspect evidence or contribute | [Evidence](evidence/README.md), [contributing](CONTRIBUTING.md), [issues](https://github.com/Hahyun-Lee/brain-ai-memory/issues) |

Maintained by [Hahyun Lee](https://github.com/Hahyun-Lee). Research citation
metadata is in [CITATION.cff](CITATION.cff). Code and this companion are MIT
licensed; no marketplace purchase is required to use the repository.
