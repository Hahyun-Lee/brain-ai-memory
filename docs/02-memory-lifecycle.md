# 02 — The Memory Lifecycle

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

The brain avoids both by *moving* memories rather than only keeping or dropping them. A specific
episode consolidates into general knowledge. A repeated action becomes an automatic procedure. An
unused trace decays but stays cued. The lifecycle below is the agent version: a small set of
operations and a rule for choosing between them, applied to every entry.

## The seven operations

Every memory entry, when you next look at it, gets exactly one of these:

| Operation | When it applies | What happens |
|---|---|---|
| **keep** | Still active, still referenced, or carries no signal that it has been superseded | Left in place, unchanged |
| **compact** | The point survives but the detail no longer earns its space | Shrunk to a one-line pointer; the link is preserved |
| **archive** | Resolved, old, and captured elsewhere (a rule, a commit, a downstream doc) | Body moved to an archive file; a one-line link stays in the index |
| **migrate-to-knowledge-base** | A reusable principle or method, useful beyond this one context | Rewritten as a decontextualized note in the semantic store; the operational entry is archived |
| **migrate-to-rules** | A repeatable procedure that can be written down as steps | Moved into the procedural rule set; the operational entry is archived |
| **delete** | Wrong or superseded by a later decision, with nothing worth keeping | Removed entirely, archive included. Used sparingly |
| **split** | One entry has grown to cover several distinct topics | Broken into separate topic files, each linked from the index |

Two of these correspond directly to the consolidation channel from
[`01`](01-the-mapping.md#the-two-channels): **migrate-to-knowledge-base** is episodic-to-semantic
promotion (a specific event becomes general knowledge), and **migrate-to-rules** is the procedural
version (a repeated fix becomes an automatic step). The rest are housekeeping that keeps the
episodic store legible enough for that promotion to happen at all.

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

A note on **delete**: it is the only operation that destroys information, so it is gated hard. "This
is no longer relevant" is not a reason to delete; it is a reason to archive. The bar for delete is
"this is false, or a later decision made it void." When unsure, archive. Archived memory is dormant,
not gone, and can be recalled by a cue; deleted memory cannot.

## Session to long-term transfer

The lifecycle above governs entries at rest. There is also a flow *through* a session, and it maps
onto the same brain analogy.

- **Session start (recall).** Long-term memory loads into working memory: the index, recent
  decisions, open threads. The agent reconstructs where it left off rather than starting blank. This
  is the long-term-to-working direction.
- **During the session (tagging).** Decisions, issues, and externally-made agreements get tagged in
  place as they happen, not reconstructed at the end. Tagging at the moment of the event is the
  difference between an accurate episodic trace and a plausible reconstruction. Anything decided
  outside the agent (a conversation, a meeting) has to be written in deliberately, or it never
  enters memory at all.
- **Session end (consolidation).** Working memory transfers back to long-term: the session's tagged
  decisions become durable entries, and the index is updated. This is the moment to run the
  consolidation channel, promoting the episodes that earned it.

The single most common failure here is skipping the tagging step and trying to reconstruct the
session at the end. By then the context has been compressed and the early work is gone. Treat the
tag as the write; the end-of-session step is consolidation, not recall.

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
