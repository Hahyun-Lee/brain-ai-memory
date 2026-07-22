# Automatic session memory (opt in)

When you reopen a project tomorrow, Brain-AI Memory can bring the latest
handoff and relevant project memory into the new session automatically. You do
not have to remember to call recall and checkpoint tools on every turn.

This mode is useful when work spans many Codex or Claude Code sessions and a
missed handoff, stale fact, or project mix-up would cost real work. It is
usually unnecessary for a one-off chat, a short task, or a repository where a
small `MEMORY.md` is easy to maintain by hand.

The loop is **off by default**. Enable it for one project with `--mode loop`.
User-wide loop installation is deliberately rejected: every hook must have one
explicit project root and one explicit memory entity.

## What happens automatically

| Moment | Brain-AI Memory does |
|---|---|
| A session starts | Recovers any interrupted checkpoint, checks approved project-local import sources, resumes the latest handoff, and supplies a byte-bounded set of current project records. |
| You send a prompt | Recalls relevant records from the same project and supplies them as sourced data, not instructions. |
| A supported command is about to run | Checks project-scoped block rules at the wired boundary. |
| A supported edit or memory write finishes | Records bounded change metadata, rechecks approved import sources, deduplicates repeated hook delivery, and marks the session as changed. |
| Context is compacted or a turn/session ends | Writes an idempotent checkpoint only when something memory-relevant changed. |
| The next session starts | Marks the latest handoff as delivered, then acknowledges delivery bookkeeping on the first prompt. |

The default injected context has a hard 6,000-byte ceiling, including a safety
envelope and source identifiers. Records that do not fit are omitted instead
of allowing the hook to grow the context without a bound.

This is lifecycle automation, not automatic truth inference. The loop can tell
that an exact approved source fragment changed or disappeared. It cannot tell
whether the replacement text is true, turn prose into exact state, promote a
new rule, or replace an old fact on its own. Those changes still use explicit
memory tools or the review workflow.

## Source freshness and reconsolidation

An approved Markdown import remains the evidence behind its derived records.
At session start, and after a supported project edit, the loop compares the
current project-local source with the fragments recorded at apply time.

- Unchanged fragments stay available.
- Records whose source fragment disappeared are withheld from automatic recall.
- A stale imported rule puts the automatic action gate into a fail-closed
  review hold; changing source text cannot silently remove an approved guard.
- A changed source receives an ordinary audit for the existing review and
  apply workflow. Nothing in that audit is promoted automatically.
- A missing, unreadable, out-of-project, or over-limit source is treated as
  unavailable; its derived records remain in history but are withheld.

This is a bounded prediction-error and reconsolidation step: detect a mismatch,
inhibit unsupported memory or action, then require a reviewed update. It is not a claim
that the software reproduces a biological brain or can judge truth. The check
is limited to 32 approved sources per entity and 2 MiB per source. Its cached
result makes prompt recall and pre-action checks use the latest completed
snapshot without reading source files at those latency-sensitive boundaries.

`brain-ai doctor --host ... --mode loop` reports a source that needs attention
and points to the generated review audit. Manual tools-only recall is not
filtered by this loop cache; review and apply the changed source before relying
on it outside automatic mode.

## Install and create one project identity

Install the package in a dedicated environment:

```bash
git clone https://github.com/Hahyun-Lee/brain-ai-memory.git
cd brain-ai-memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ".[mcp]"
```

Then move to the project that will own the memory and create one stable entity.
If you already imported a `MEMORY.md` for this entity, skip the last command.

```bash
cd /path/to/your/project
export PROJECT_ROOT="$PWD"
export BRAIN_AI_HOME="$PROJECT_ROOT/.brain-ai"
brain-ai init
brain-ai entity add --name my-project --type project
```

Keep using the same `PROJECT_ROOT`, `BRAIN_AI_HOME`, and entity name for this
project. The runtime directory contains unencrypted local data; keep
`.brain-ai/` out of version control.

## Connect Codex

First preview the managed changes. Nothing is written without `--apply`.

```bash
brain-ai connect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
brain-ai connect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT" --apply
```

This adds the project tool connection and lifecycle hooks to the project. Codex
requires trust for the exact hook definitions; review them in Codex when
prompted (or with `/hooks`), then start a new session so `SessionStart` can run.
The managed lifecycle file is `.codex/hooks.json`.

Codex currently has no `SessionEnd` hook. Brain-AI Memory therefore checkpoints
dirty work on `Stop` and before compaction, then resumes it at the next
`SessionStart`. `Stop` is a turn boundary, so clean turns do not create extra
checkpoints.

Check both installation and observed activity:

```bash
brain-ai doctor --host codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
```

`configured` means the managed connection and hooks are present. `active`
means a real host session has delivered the expected lifecycle events. A newly
applied setup can therefore be configured but not active until you trust the
hooks and use a fresh session.

## Connect Claude Code

The same preview-then-apply workflow is available for Claude Code:

```bash
brain-ai connect claude-code --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
brain-ai connect claude-code --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT" --apply

brain-ai doctor --host claude-code --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
```

Claude Code receives the same start, prompt, tool, compaction, and stop
handling, plus `SessionEnd` when the host emits it. The local lifecycle settings
are written to `.claude/settings.local.json`. Review any host request to approve
the project connection, then open a new session before expecting `active`.

See the official host documentation for the exact trust and hook UI:
[Codex hooks](https://learn.chatgpt.com/docs/hooks) and
[Claude Code hooks](https://code.claude.com/docs/en/hooks).

## Privacy boundary

The hook uses the prompt transiently, only while selecting relevant records.
By default, the loop does **not** persist:

- raw prompts or conversation transcripts;
- raw tool output or the assistant's final message;
- edited file contents; or
- inferred facts, rules, decisions, or exact state.

It keeps hashes and lengths needed for idempotency and audit, tool names and
input-key names, one-way hashes of host session and turn identifiers, selected
memory IDs, relative paths for supported project file edits, and the source
paths, hashes, status, and affected record IDs needed for the freshness cache.
The freshness check reads approved Markdown locally; it does not add raw source
text to the cache. A changed source uses the same local audit artifacts as a
manual `brain-ai audit`. Explicit calls to memory-writing tools still store the
content you asked them to store. The typed memory, audit ledger, audits, and
checkpoints are local plaintext files, not encrypted storage.

The v0.6 audit, episode, and checkpoint JSONL histories are append-only. Loop
coordination receipts and current delivery state live in SQLite. Neither store
prunes itself. Monitor the size of `.brain-ai/` for long-running projects and
apply the local retention or backup policy you intend. Disconnecting the loop
does not erase that directory.

If a hook cannot run, it reports a short degraded/unavailable message rather
than terminating the host. A successfully matched project rule is different:
its explicit block verdict is returned as a denial at the supported pre-tool
boundary.

After an upgrade, a legacy rule that no longer meets the bounded pattern
contract is not evaluated as a regular expression. It is registered for
operator review and the action gate stays fail-closed for that project until
you create a safe replacement or acknowledge the old rule with
`brain-ai rule disable RULE_ID --yes`. `brain-ai rule list` and
`brain-ai doctor` show the required review.

## Disconnect without deleting memory

Preview removal first, then apply it:

```bash
brain-ai disconnect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT"
brain-ai disconnect codex --entity my-project --mode loop \
  --project-root "$PROJECT_ROOT" --apply
```

For Claude Code, replace `codex` with `claude-code`. Disconnect removes only
the tool connection and hook definitions managed by Brain-AI Memory. It refuses
to remove a managed definition that was modified unexpectedly, preserves
unrelated host settings, and leaves every record under `.brain-ai/` intact.
