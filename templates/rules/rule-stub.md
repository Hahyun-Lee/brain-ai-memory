# Rule: <short name>

> Copy this stub when you add a conditional procedural rule (a Tier 3 advisory
> rule, in the language of docs/03-governance-tiers.md). A rule that follows this
> shape is easy for the agent to load, apply at the right moment, and later
> promote or retire on evidence. Delete this quote block when you fill it in.

**Condition.** When does this rule apply? State the trigger as concretely as you
can, so the agent can tell whether it is in scope right now. A rule that is
"always on" is usually really several rules; split it. *(Example: "When drawing a
conclusion from a comparison of two numbers.")*

**Principle.** The one-sentence rule itself, written so it is hard to misread.
This is the line the agent should be able to recall verbatim. *(Example: "Two
numbers are comparable only if they share the same data, metric, aggregation, and
space.")*

**Procedure.** The concrete steps the agent takes when the condition is met. Keep
it to a short ordered list. If the procedure is a multi-step fallback loop,
consider externalizing it as an executable harness instead of prose, because a
narrated procedure can be abandoned mid-loop (docs/01, the CB failure mode).

1. <step>
2. <step>
3. <step>

**Failure mode it prevents.** What goes wrong without this rule? Name the specific
mistake, ideally one you have actually seen. This is what justifies the rule's
existence and what you check against when deciding whether it still earns its
place. *(Example: "A multiplier comparison across two different metric spaces,
stated as if it were a like-for-like result.")*

**Tier and evidence.** Start at Tier 3 (advisory). Record here if and why it was
promoted: how many times the pattern was violated, what the guard or warning is,
and the trend since. A rule with no failure history does not need a gate; a rule
violated repeatedly under warning is a candidate for one (docs/03).

- Tier: `advisory` | `guarded` | `enforced`
- Promotion note: <empty until there is evidence>
