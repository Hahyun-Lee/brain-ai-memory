# 01 — The Mapping

> The brain does not have *a* memory. It has several, each specialized, each able to fail on
> its own, joined by channels that move information between them. This document maps those
> systems onto concrete LLM-agent constructs so you can reason about agent memory the way a
> clinician reasons about a brain: component by component, failure by failure.

The machine-readable version of everything below lives in [`schema/brain_components.yaml`](../schema/brain_components.yaml).
This file is the narrative: the *why*.

![Architecture overview: input gating, orchestration, five specialized systems, and two memory channels](assets/architecture-overview.svg)

## Why a mapping at all

The usual way an agent "has memory" is a pile of mechanisms that grew one at a time: a vector
store for retrieval, a scratchpad for the current task, a context window that silently drops the
oldest tokens, maybe a JSON file of facts. Each was added to fix a specific pain. None of them
answers the structural question: *given a piece of information, which store should hold it, and
when should it move?*

When something goes wrong (the agent repeats a question it already answered, cites a source it
half-remembers, miscounts a list, gives up on a multi-step task halfway) you have no vocabulary
to say *which* part broke. "The memory failed" is as useless as a doctor saying "the brain is
sick."

The brain solved the same problem under far harder constraints, and its solution is **separation
of concerns**. Working memory is not the hippocampus is not the semantic cortex. Each is a
different mechanism with a different failure mode and a different fix. Borrow that structure and
agent memory becomes *diagnosable*: every failure points at a component, and every component has
its own remedy.

A caveat up front: this is an **engineering analogy**, not a neuroscience claim. The brain is far
messier than seven boxes, and real regions overlap and share work. The mapping earns its place
only by making agent failures easier to name and fix, not by being literally true. Where the
analogy would mislead, drop it.

## Mechanisms are not the architecture

This mapping does not replace RAG, hooks, harnesses, or loops. It assigns them
different jobs:

- **RAG or a vector store** retrieves candidate knowledge.
- **A hook** provides a moment when the system can inspect or intercept an
  event.
- **A guard** makes a single allow/deny decision at that moment.
- **A harness** owns a multi-step sequence and its fallback paths.
- **A loop** feeds an outcome or verdict back into another attempt.

Those mechanisms can be combined without a memory architecture, but the result
is often a pile of fixes with no answer to four questions: which subsystem owns
the information, how that subsystem fails, when the information should change
form, and whether the feedback path is actually closed. The mapping supplies
that diagnostic contract. Its claim is not that the mechanisms are new; it is
that keeping their responsibilities and failure modes separate makes the whole
system easier to operate.

## The seven components and two channels

```
                          ┌─────────────────────────────┐
                          │   PFC — Orchestrator         │
                          │   routes work to the right   │
                          │   store; sets priorities     │
                          └───────────────┬─────────────┘
                                          │ routes to
        ┌────────────────┬────────────────┼────────────────┬────────────────┐
        ▼                ▼                ▼                 ▼                ▼
  ┌───────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌───────────┐
  │ HC        │   │ ATL        │   │ BG         │   │ CB         │   │ IPS       │
  │ episodic  │   │ semantic   │   │ rules      │   │ execution  │   │ numerical │
  │ (events,  │   │ (concepts, │   │ (allow /   │   │ (run the   │   │ (exact    │
  │  entities)│   │  facts)    │   │  deny)     │   │  loop)     │   │  counts)  │
  └─────┬─────┘   └─────┬──────┘   └────────────┘   └────────────┘   └───────────┘
        │               │
        │ consolidation │           ┌────────────────────────────────────────┐
        └──────────────►│           │ TH — input gate: filters dangerous      │
        (episode →      │           │ input before it ever reaches the agent  │
         knowledge)     │           └────────────────────────────────────────┘
        ◄───────────────┘
         reconsolidation
        (update stale memory at recall time)
```

Two of these (**BG** and **TH**) are simple allow/deny valves and close their own loops. The
rest depend on the orchestrator's judgment and stay partly open. Keep that asymmetry in mind; it
is revisited at the end.

---

### PFC — the Orchestrator

**Brain role.** The prefrontal cortex is the executive: it holds goals, sets priorities, and
decides which subsystem handles what. It does not store much itself; it *directs*.

**Agent analog.** The main agent loop and its routing logic. Given a request, the orchestrator
decides: is this a fact to look up (semantic), a past event to recall (episodic), a rule to
enforce (procedural), a number to read exactly (numerical)? It is the part that chooses a store
rather than being one.

**Failure mode.** *Misrouting.* The capability exists but is misapplied: the agent estimates a
number it could have looked up, or answers from the context window something that belonged in
long-term store. The executive-dysfunction analog: not an inability, a misdirection.

**Diagnostic.** Trace a single decision. Which store did the agent actually read, and was that the
right one for this kind of question? Most "memory bugs" are really routing bugs.

---

### HC — Episodic memory (the hippocampus)

**Brain role.** The hippocampus binds the elements of an experience (what happened, where, when,
with whom) into a single retrievable episode, and indexes it for later recall.

**Agent analog.** The event log and entity graph: an append-only trace of what happened across
sessions, plus the relationships between the entities involved (this person, that decision, this
thread). It is *contextual* memory, tied to time and circumstance, unlike semantic memory.

**Failure mode.** *Broken binding.* The agent acts on a stale prior, re-asks a settled question,
or fails to connect two events that belong together. The amnesia analog: new experience never
anchors to the right context, so the past stops informing the present.

**Diagnostic.** When the agent recalls a past event, is the binding intact (right person, right
thread, right time), or did it stitch together a plausible but false link?

---

### ATL — Semantic memory (the anterior temporal lobe)

**Brain role.** Semantic memory holds decontextualized knowledge: concepts and facts stripped of
when or how you learned them. You know what a hippocampus is without remembering the lecture.

**Agent analog.** The vector / embedding store over a knowledge base of notes, documents, and
references, retrieved by similarity rather than by exact key. This is where general knowledge
lives, independent of any one session.

**Failure mode.** *Meaning errors and staleness.* Misreading a concept, following a dangling link,
treating a secondary source as primary. Then the slower failure: an index that fossilizes and keeps
returning an outdated view. The semantic-dementia analog, where the knowledge degrades while
confidence stays high.

**Diagnostic.** Is the retrieved knowledge both *relevant* and *fresh*? Did the agent verify a
cited claim against the primary source, or just trust the embedding's nearest neighbor?

---

### BG — Procedural-rule memory (the basal ganglia)

**Brain role.** The basal ganglia gate learned action rules: the habits and inhibitions that fire
without deliberation. They answer "do I do this or not?" before conscious thought catches up.

**Agent analog.** Rule memory in two forms: *static* (the instruction and config files the agent
reads) and *dynamic* (deterministic pre-action guards that fire before a tool call). The static
form is what the agent *should* know; the dynamic form is what actually *stops* it.

**Failure mode.** *Knows the rule, fails to act on it.* Either the freeze (the rule is known but
the action doesn't happen) or the compulsion (a forbidden pattern repeats despite the agent
knowing better). The rule is encoded; the gate that should fire does not.

**Diagnostic.** For each rule you care about, is there a deterministic gate that actually fires,
or does enforcement rely on the model remembering in the moment? If it relies on memory, it is not
a rule, it is a hope.

---

### CB — Procedural-execution (the cerebellum)

**Brain role.** The cerebellum runs learned motor sequences smoothly to completion: the
coordination that lets a practiced movement finish without conscious step-by-step control.

**Agent analog.** An executable harness: a script that owns a multi-step procedure, including its
fallback paths, end to end. The key word is *executable*. A procedure written as prose
instructions is re-narrated by the model every time and can be quietly dropped mid-loop; the same
procedure as code runs to completion or fails loudly.

**Failure mode.** *Premature abandonment.* The agent recalls the procedure, tries the first path,
hits a snag, and gives up: "I tried one thing." The dysmetria analog, where the sequence is known
but not carried to its end.

**Diagnostic.** Is the multi-step fallback externalized as code that runs to completion, or
re-described by the model each time? This is the single most common place where a capable agent
*looks* like it failed when really it just stopped early.

**Why it is separate from BG.** Both are "procedural," but BG enforces a single allow/deny
*decision* while CB executes a *sequence with fallbacks*. They fail differently and are fixed
differently (a guard vs. a harness), so collapsing them hides the distinction that matters.

---

### IPS — Numerical memory (the intraparietal sulcus)

**Brain role.** Parietal cortex handles exact magnitude, counting, and arithmetic: the precise
quantity rather than the rough sense of "more" or "less." (This is the number-sense region; it is
*not* the "relational memory" of episodic binding, which belongs to the hippocampus above.)

**Agent analog.** A numerical store: a small queryable mirror for the numbers the agent must not
estimate: counts, totals, metrics that have a knowable correct value.

**Failure mode.** *Estimation where the answer was knowable.* "About a dozen items" when the real
count was eleven and readable. The dyscalculia analog, and an insidious one, because an estimated
number reads exactly like a correct one.

**Diagnostic.** Was every quantity in the output read from a source, or did some get estimated from
memory? Numbers in agent output should be sourced, not recalled.

---

### TH — Gating (the thalamus)

**Brain role.** The thalamus is the relay and gate for incoming signals; it filters what reaches
cortex rather than letting all input through raw.

**Agent analog.** A preventive input gate: a pre-action filter on the *input* path that blocks a
dangerous case before it executes: an unsafe deserialization, an injected instruction, a write
that should never be permitted.

**Failure mode.** *Dangerous input passes unfiltered* and the damage is done before anything
notices.

**Diagnostic.** Is there a filter on the input path that blocks the bad case *before* execution,
rather than a cleanup that runs after? Gating is preventive by definition; a gate that only
notices afterward is not a gate.

---

## The two channels

Components store; channels *move*. These are the transfer mechanisms, and they are where a lot of
real-world agent memory quietly breaks, not because a store is missing, but because nothing ever
promotes or updates what the stores hold.

### Consolidation — episodic → semantic

The sleep analog: during rest, the hippocampus replays recent episodes and the cortex slowly
extracts the durable pattern. A specific experience becomes general knowledge.

For an agent: a one-off event (a failure hit once, a fix discovered) gets distilled into a reusable
rule and moved from the event log into the knowledge base. **If this channel never runs**,
retrieval returns a soup of raw episodes instead of distilled lessons, and the agent re-derives the
same insight again and again. Most "the agent never learns" complaints are a broken consolidation
channel, not a missing store.

### Reconsolidation — update at recall time

When the brain retrieves a memory, it briefly becomes editable again before re-storing. Recall is
not read-only; it is a chance to revise.

For an agent: when a stored memory is recalled and found to be stale or in conflict with newer
information, that is the moment to update it (with human approval) rather than act on the outdated
version. **If retrieval only ever surfaces the most recent entry**, older stale candidates are
hidden permanently and never corrected; the memory rots silently behind the freshest layer.

---

## The asymmetry you should not forget

It is tempting to read this mapping as "wire up seven components and two channels and the agent
runs itself." It does not work that way, and the honest version of the map says so.

Only the deterministic gates, **BG** and **TH**, close their own loops. They are simple
allow/deny valves: given an input, a fixed rule fires, no judgment required. Everything else stays
partly open. The orchestrator's routing, the decision to verify a citation, the choice to look up a
number instead of estimating it: these depend on the model's judgment *in the moment*. You can
prompt for them, log them, and nudge them, but you cannot turn them into deterministic valves
without throwing away the judgment that made them useful.

That asymmetry is not a gap to be closed; it is the shape of the problem. Mapping the brain does
not make a hard problem deterministic. What it does is tell you **which parts are deterministic and
which are not**, so you stop trying to hook your way out of a judgment problem, and stop trusting
judgment where a hook would do.

The rest of this repo builds on that line: [`02-memory-lifecycle.md`](02-memory-lifecycle.md) for
how entries move and age, [`03-governance-tiers.md`](03-governance-tiers.md) for the deterministic
vs. advisory split and why catching a mistake is not the same as preventing it, and
[`04-principles.md`](04-principles.md) for the short rule set that lives in the open, judgment-bound
parts.
