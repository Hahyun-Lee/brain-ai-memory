# 04 — Principles

> The components and the lifecycle are structure. This document is the short list of *operating
> principles* that ride on top of them: a handful of rules, each adoptable on its own, that live at
> the advisory tier and govern the open, judgment-bound parts of the agent. Each is written so you
> can drop it into your own agent instructions and adapt it.

Builds on [`03-governance-tiers.md`](03-governance-tiers.md): these are Tier 3 rules. They are not
enforced by a gate, because they govern judgment, which is exactly the kind of thing a gate cannot
capture. They earn their place by being short, memorable, and right often enough to be worth the
reminder.

## Internal-first

**Before reaching outside, exhaust what you already hold.** When the agent needs information, the
default impulse is to search the widest, most external source: the web, an API, a fresh query. The
discipline is to invert that order. Check the agent's own repository and instructions first, then
its accumulated knowledge base, then local files, and only then the outside world. Most of the time
the answer is already written down, and treating an external search as the first move both wastes
effort and risks presenting as a "new finding" something the system already knew. The failure mode
this prevents is subtle: an agent that does not consult its own memory will keep rediscovering, and
re-deciding, things it settled long ago.

## World-best-sourcing

**Before building a solution, integrate the best one that already exists.** When the task calls for
a new analysis, tool, metric, or method, the tempting path is to build a small version inside your
own system. The discipline is to first ask whether the world already has a strong answer: an
open-source library, a published method, a standard dataset, an established metric. If it does,
adopt and integrate it; build your own only when nothing suitable exists. This is the outward
counterpart to internal-first. Internal-first stops you re-deriving your *own* past work;
world-best-sourcing stops you re-inventing the *world's* existing work as an inferior in-house
version. The two together mean you build only what is genuinely missing, inside or out.

## Self-verdict before escalation

**Run your own check before asking for one.** Before declaring a piece of work done, or before
escalating a question to the user, the agent should pass the output through one explicit
self-review: is anything stale, does it contradict something known, is a causal claim overstated, is
this a safe "good enough" that stops short of what the task actually needed? The point is to catch
the predictable problems *before* a human has to point them out, not to replace human review. There
is one trap to name, because it connects directly to the failure mode below: a self-check that the
agent both performs and judges is prone to passing itself. The agent expects the work to be fine, so
it reports the work is fine. A self-verdict is only worth running if it is structured to actually be
able to fail, which is why the governance layer favors *independent* checks
([`03`](03-governance-tiers.md)) for anything that matters.

## Comparison-integrity

**Two numbers are only comparable if they measure the same thing.** Before drawing a conclusion from
a comparison, confirm the two quantities share the same data, the same metric, the same level of
aggregation, and the same space. If any of those differ, a direct comparison is invalid, and the
honest move is to state the difference and compare only within its limits. Two adjacent disciplines
ride along: "not significantly different" is not the same claim as "equivalent," and a null result
in someone else's work should be attributed to the reason *they* gave for it, not to whatever makes
your own design look better. The unifying rule is that a comparison carries hidden assumptions, and
integrity means surfacing them before the conclusion, not defending the conclusion after.

## A note on confident-but-wrong

These principles share a common adversary, and it is worth naming because it is more dangerous than
ordinary error. **Confabulation** is a confident, fluent, internally consistent claim built on a
premise that is wrong. The schema in this repo carries it as a distinct diagnostic lens
([`schema/brain_components.yaml`](../schema/brain_components.yaml)), separate from a plain semantic
error, precisely because it does not look like a mistake from the inside. The agent is not unsure; it
is sure, and wrong.

Each principle here is, in part, a defense against it. Internal-first grounds claims in what is
actually written down rather than in a plausible reconstruction. Self-verdict forces a check that can
fail, instead of a confidence that confirms itself. Comparison-integrity refuses the fluent
conclusion until its assumptions are checked. The reason these have to be *principles* rather than
enforced gates is that confabulation is a judgment failure, and the only thing that catches a
judgment failure is another, independent act of judgment, applied on purpose. Build the habit of
applying it before the user has to.

## Adopting these

Each principle above is written as a single paragraph on purpose: it should fit, more or less
verbatim, into your own agent's instruction file. Take the ones that fit your work, adapt the
wording to your stack, and treat them as a starting set rather than a closed list. The form that
matters is "a short rule the agent reads every session, stated so it is easy to remember and hard to
misread." The content will differ by domain; the discipline of keeping the advisory layer small,
legible, and actually-read is what transfers.
