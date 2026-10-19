# How memory supports agent self-monitoring

A useful memory should help an agent answer more than “have I seen this text?”
Before using a remembered decision, the agent needs to check which project it
belongs to, what supports it, whether it has been replaced, and what still needs
a person's judgment. These checks are the practical role of metacognition in
Brain-AI Memory.

## A decision changes between sessions

Consider a synthetic release-planning example. A project note says Friday. A
later approved decision changes the release day to Thursday.

| Reader's question | Memory operation | What still needs judgment |
|---|---|---|
| Which project owns this decision? | Give records a project ID (entity); lock the connection to that project. | Select the intended project when configuring the connection. |
| What supported Friday? | Inspect the imported source path, line span and hashes. | Decide whether that source is authoritative. |
| Is Friday still current? | Mark Friday as replaced and keep it in history (`supersede`). | Confirm that Thursday replaces the same decision. |
| What is the exact current value? | Store and query a named project value (state key), outside prose. | Save the approved value; use the release's supported query route. |
| What should happen next? | Save a project summary and next action (`checkpoint`) for the next session. | Supply the summary and concrete next action. |

Saving a new semantic note does not automatically supersede an older one.
Reading a document does not save its facts. A checkpoint does not replace the
individual fact or state writes. The [companion skill](../skills/brain-ai-memory/SKILL.md)
gives the agent an explicit routine for these distinctions.

## Checking currentness has a specific meaning

For approved Markdown imports, the runtime records source fragments and hashes.
Source-freshness checks can identify changed support and withhold affected
records pending review. The optional session loop runs these checks at supported
session and edit events. The [loop guide](08-autonomous-loop.md#source-freshness-and-reconsolidation)
describes the event and review boundaries.

A matching hash means the checked text has not changed. It does not mean the
text is true, that a policy is still valid elsewhere, or that an external
service agrees with it. A manually supplied source label is not independent
verification either. New evidence still needs an authorized correction or
review.

On published v0.7.0, an ordinary question can miss an exact-state record.
For a known key, use a numeric hint such as `metric release_channel` and inspect
the matching state in `memory.IPS`. The [companion instructions](../skills/brain-ai-memory/SKILL.md#exact-values-on-v070)
include the scoped CLI equivalent. A retrieval miss alone does not establish
that no record exists.

## What runs, and who decides

The runtime performs storage, scoped retrieval, source checks and explicit
lifecycle operations. In tools mode the agent must call those operations; the
skill supplies instructions, not enforcement. Optional hooks supply supported
execution points. A returned action verdict only controls execution when the
host consumes it at the action boundary.

This supports an agent's monitoring and correction workflow. It does not give
the model self-awareness, infer the truth of arbitrary prose, or close every
feedback loop automatically. The brain-inspired labels are an engineering
analogy, explained in [the component mapping](01-the-mapping.md). They are not
evidence of biological equivalence or better reasoning.

## Choose it for control you need to inspect

Keep a plain `MEMORY.md` or your agent's existing memory when that is enough.
Consider this runtime when you need explicit records of project ownership,
approved replacements, exact state and handoffs that you can inspect outside
the conversation. Using the same local store from multiple hosts is an
integration choice, not proof of better answers.

The [evidence summary](../README.md#evidence-status) separates software contracts
and retrieval pilots from the still-unverified benefit over native memory.
The implementation references are the released
[adoption workflow](https://github.com/Hahyun-Lee/brain-ai-memory/blob/v0.7.0/src/brain_ai_memory/workspace.py),
[runtime](https://github.com/Hahyun-Lee/brain-ai-memory/blob/v0.7.0/src/brain_ai_memory/runtime.py)
and [MCP server](https://github.com/Hahyun-Lee/brain-ai-memory/blob/v0.7.0/src/brain_ai_memory/mcp_server.py).
