# 02 — The Memory Lifecycle

[한국어](02-memory-lifecycle.ko.md)

> A memory store that only grows is a memory store that fails. The hard part of agent memory is not
> writing things down; it is deciding what each entry should *become* over time, and moving it there
> before the store rots. This document gives a concrete decision rule for every entry, and the few
> health metrics that tell you when the system is degrading.

Builds on [`01-the-mapping.md`](01-the-mapping.md): there we named the stores; here we govern what
flows between them.

## Why a lifecycle at all

Most agent memory grows in one direction. Facts get appended, a context file gets longer, a notes
document accumulates. Nothing is ever promoted, compacted, or removed, because no rule says when to
do so. Two failures follow, and they pull in opposite directions:

- **Bloat.** The always-loaded memory grows past the point where the agent can hold it, and the
  important entries drown in stale ones. Recall gets worse precisely because there is more to recall.
- **Loss.** To fight bloat, things get deleted wholesale, and a decision that mattered six months
  later is gone with no trace.

Biological memory motivates the idea that representations can be reorganized,
transformed, strengthened, or weakened over time rather than merely accumulated.
The lifecycle below is a deliberate software translation—not a biological
simulation: a small set of explicit, auditable operations and a rule for
choosing among them.

## The seven operations

Every memory entry, when you next look at it, gets exactly one of these:

| Operation | When it applies | Reference-runtime effect |
|---|---|---|
| **keep** | Still active, still referenced, or carries no signal that it has been superseded | Records the decision; the entry stays active and unchanged |
| **compact** | The point survives but the detail no longer earns its space | Records a candidate for a host-created pointer; it does not rewrite the source |
| **archive** | Resolved, old, and captured elsewhere (a rule, a commit, a downstream doc) | Marks the entry inactive in default views while retaining the source for audit |
| **migrate-to-knowledge-base** | A reusable principle or method, useful beyond this one context | Hides an episodic source from default views; actual derivation requires explicit consolidation preview and apply |
| **migrate-to-rules** | A repeatable procedure that can be expressed as an enforceable rule or executable step | Hides an episodic source from default views; an actual rule requires approved consolidation with an explicit pattern |
| **delete** | Wrong or superseded by a later decision, with nothing worth keeping | Creates a logical tombstone/inactive status; it does **not** physically erase source bytes |
| **split** | One entry has grown to cover several distinct topics | Records a host action to create linked topic entries; it does not split files automatically |

The table states what the installable alpha actually does. For episodic
entries, `archive`, `delete`, and both migration decisions hide the entry from
default active views but leave the append-only event available through
`include_inactive`; for semantic entries, only `archive` and `delete` update
status while retaining the row, and other lifecycle decisions add audit state
without changing that status. `compact` and `split` are audited decisions for
the host, not file-rewrite engines. Secure erasure, archive-file movement, and
retention enforcement remain host responsibilities.

At the architecture level, two decisions direct the consolidation-inspired
software channel from [`01`](01-the-mapping.md#the-two-channels):
**migrate-to-knowledge-base** identifies episodic evidence worth deriving into
reusable knowledge, and **migrate-to-rules** identifies an approved repeated
lesson worth turning into an enforceable rule or executable step. The
`lifecycle` command alone creates neither artifact; use an explicit
`consolidate` preview/apply flow. Neither operation claims to reproduce
biological consolidation.

### Choosing between them

When operations conflict, resolve in this order, top to bottom:

1. **keep** if the entry is an index anchor, is still active (its outcome is not yet known), or shows
   no signal of being superseded.
2. **split** if it has grown too long and covers multiple topics.
3. **delete** only if it is actually wrong. This is rare; prefer archive when in doubt.
4. **migrate-to-knowledge-base** if it is a principle or method worth reusing.
5. **migrate-to-rules** if it is a procedure worth formalizing.
6. **archive** if it is resolved, old, and already captured by a downstream artifact.
7. **compact** if only part of it has lost its value.

The ordering matters because the cheap operations (archive, compact) are tempting and lossy. Forcing
the migration questions first means a reusable lesson gets promoted into the knowledge base *before*
anyone considers archiving it into silence.

A note on **delete**: at the design level it is the only decision that may
authorize eventual destruction, so it is gated hard. "This is no longer
relevant" is not a reason to delete; it is a reason to archive. The bar is
"this is false, or a later decision made it void." In this reference runtime,
however, delete is deliberately a recoverable logical tombstone—not proof of
privacy erasure. A host that requires physical deletion must perform and verify
that separate retention-policy operation.

## Four representations, not one memory file

A long-running agent should not treat every representation as the same kind of
memory:

| Representation | Purpose | Default policy |
|---|---|---|
| **raw host trace** | Provider-native transcript or tool-event evidence | Do not retain unless an explicit host privacy and retention policy permits it; when retained, never rewrite the evidence in place |
| **working memory** | Host-owned, token-budgeted current-task context | Assemble it from only the scoped candidate records needed now |
| **episodic memory** | Structured event with entity binding, ingest time, text, and source label | Preserve the host's evidence link separately when available |
| **consolidated memory** | Reusable knowledge or an approved procedure derived from episodes | Version it, record its sources, and make promotion explicit |

A transcript stored on disk is not automatically working memory, and a summary
is not automatically a trustworthy fact. Retrieval returns a record-count-
limited candidate view; the host decides what fits its model's token budget and
working context. Consolidation derives a new representation and must not erase
its evidence. The public runtime owns explicit `events.jsonl` records and
checkpoints, but it does not scrape Claude Code, Codex, or other host
transcripts. This repository ships no Claude Code JSONL or Codex rollout
adapter. An integrating host or custom adapter owns any permitted raw-trace
retention and maps only selected events into the runtime.

## Session to long-term transfer

The lifecycle above governs entries at rest. There is also an explicit software
flow *through* a session, using the same mnemonic labels without asserting a
biological transfer mechanism.

- **Session start (recall).** The host explicitly queries long-term memory and
  supplies a scoped result to the current working context: for example, recent
  events, applicable rules, and exact state. The runtime does not inject this
  context into a model by itself. This is the long-term-to-working direction.
- **During the session (tagging).** The host explicitly calls
  `brain_remember` (or `brain-ai remember`) for selected decisions, issues, and
  externally made agreements as they happen. Anything not deliberately
  recorded remains outside the structured episodic store; the runtime does not
  infer it from a provider transcript.
- **Session end (consolidation and handoff).** The host previews
  `brain-ai consolidate`, applies it only after approval, and calls
  `brain_checkpoint` with an explicit/default entity (or
  `brain-ai handoff --entity ...`) for a durable scoped handoff. The legacy `brain-ai checkpoint`
  writes only a global summary. This is
  an explicit integration sequence, not an automatic transfer of everything
  in working memory.

The single most common failure here is skipping the explicit write and trying
to reconstruct the session at the end. By then the context may have been
compressed and early work may be gone. Treat `brain_remember` as the structured
write; consolidation and checkpointing are separate, explicit operations.

The two directions define a **host integration contract**, not a background
loop. On the core memory path, the host translates the current goal into a
query and entity scope, PFC returns candidate records from the relevant stores,
and the host assembles the actual working context. Bottom-up, the host
explicitly records selected outcomes with `brain_remember`, previews and
applies consolidation, and creates the checkpoint. On the optional action
path, a host-proposed action can receive a TH/BG verdict, and CB is used only
when the host invokes `brain-ai harness` or `brain-ai sequence`. The loop is
not closed merely because files or an MCP connection exist: every producer
needs a consumer, and an integration check should verify that the handoff was
consumed.

## Health metrics

You cannot eyeball whether a memory system is healthy. These three signals catch the failures early,
and each has a concrete threshold you set for your own stack:

- **Index budget.** The always-loaded index has a hard size ceiling, because it is paid on every
  single session. Past the ceiling it is truncated, and truncation is silent. Keep the index to
  one line per entry (a title and a hook), and push detail into linked topic files. When the index
  approaches its ceiling, that is the trigger to run the lifecycle, not a reason to raise the
  ceiling.
- **Orphan rate.** An entry that exists but is not linked from the index is unrecallable: the agent
  has no path to it, so for practical purposes it does not exist. Orphan rate (entries with no
  inbound link) is the clearest signal that the store is decaying into write-only memory. It should
  trend toward zero.
- **Recall cap.** When a memory file is auto-retrieved by relevance, only the first slice of it is
  injected. A file longer than that slice is read truncated, and the part past the cap is invisible
  at recall time even though it is on disk. Keep individual topic files under the cap, or the most
  important content can sit just past the fold and never surface.

The pattern across all three: **what is on disk is not what is recalled.** A healthy lifecycle keeps
the recalled view (index, links, the top of each file) faithful to what actually matters, instead of
letting the gap between stored and retrieved widen until the agent is confidently working from a
partial picture.

## Where this lives in the repo

The decision table here pairs with the memory-file skeleton and a decision helper in
[`templates/memory/`](../templates/memory/). The governance disciplines that decide *when* to promote
a procedure into an enforced rule are in [`03-governance-tiers.md`](03-governance-tiers.md).
