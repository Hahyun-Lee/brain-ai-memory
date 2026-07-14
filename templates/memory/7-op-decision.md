# 7-Operation Decision Helper

> A pocket version of the decision rule in docs/02-memory-lifecycle.md. When you
> review a memory entry, walk this top to bottom and stop at the first match.
> The order is deliberate: the cheap, lossy operations (archive, compact) sit at
> the bottom so a reusable lesson gets promoted before anyone buries it.

## Walk this in order, stop at the first match

1. **KEEP** if any of:
   - it is an index anchor that other entries point to, or
   - it is still active (its outcome is not yet known), or
   - there is no signal that it has been superseded.

2. **SPLIT** if it has grown long and now covers several distinct topics.
   → Break into separate topic files, each linked from the index.

3. **DELETE** only if it is actually wrong or made void by a later decision.
   → Remove entirely. Rare. When unsure, do not delete; archive instead.
     (Archived memory is dormant and can be re-cued; deleted memory is gone.)

4. **MIGRATE-TO-KNOWLEDGE-BASE** if it is a reusable principle or method useful
   beyond this one context.
   → Rewrite as a decontextualized note in the semantic store; archive the
     operational entry. (This is episodic → semantic consolidation, docs/01.)

5. **MIGRATE-TO-RULES** if it is a repeatable procedure that can be written as
   steps.
   → Move into the procedural rule set; archive the operational entry.

6. **ARCHIVE** if it is resolved, old, and already captured by a downstream
   artifact (a rule, a commit, another doc).
   → Move the body to an archive file; keep a one-line link in the index.

7. **COMPACT** if only part of it has lost value but the core point survives.
   → Shrink to a one-line pointer; keep the link.

## The two questions that catch the common mistakes

- **"Is this reusable beyond here?"** asked *before* archiving. This is what
  stops a hard-won lesson from being filed into silence. If yes, it migrates
  (4 or 5) rather than archives (6).
- **"Is this actually false, or just no longer relevant?"** asked before
  deleting. "No longer relevant" is a reason to archive, not delete. Only
  "false / superseded" clears the bar for delete (3).
