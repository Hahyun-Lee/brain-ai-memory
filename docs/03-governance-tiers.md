# 03 — Governance Tiers

> An agent makes the same kinds of mistakes a base model makes: it forgets a rule it knows, repeats
> a pattern it was told to avoid, gives up on a procedure halfway. The question this document answers
> is how to correct those mistakes systematically, without burying the agent in self-surveillance
> that makes it worse. The answer is a three-tier escalation, and one insight about what these
> systems actually do.

Builds on [`01-the-mapping.md`](01-the-mapping.md): the procedural-rule component
(BG) and the pre-execution gate (TH) are where governance lives. This document
is how you decide what belongs there. The broader architecture can wire input
and write/security gates at the host boundary; the public alpha implements only
the narrower contract it can demonstrate—a check over an explicit proposed-
action string.

## The three tiers

Not every rule deserves the same enforcement. Hard-blocking everything is brittle and slow; trusting
the model to remember everything does not work. So rules live at one of three tiers, and they move
between tiers based on evidence.

### Tier 3 — Advisory (the rule is written down)

The rule lives in the agent's instructions and is expected to be read and followed. No mechanism
enforces it; the model complies because it was told to. This is where every rule starts, and where
most should stay. Advisory rules are cheap to add and cheap to change, and they cover the vast space
of "good judgment" that cannot be reduced to a fixed check.

The weakness is exactly that nothing enforces them. An advisory rule is a hope that the model
remembers in the moment. For rules where forgetting is rare or low-cost, that is fine. For rules
that are violated repeatedly, it is not, and the violation count is the signal to promote.

### Tier 2 — Guarded (a warning fires, but does not block)

A lightweight check runs at the relevant moment and emits a warning when a precondition looks
unmet, without stopping the action. This tier catches "should have done X but didn't" cases: the
guard notices the missing step and surfaces it, leaving the decision to proceed with the agent.

Guarded is the right tier for preconditions that are usually-but-not-always required, where a hard
block would produce false positives that train the agent to route around the guard. The warning
keeps a human-legible record of how often the precondition is actually missed, which feeds the next
promotion decision.

### Tier 1 — Enforced (the action is blocked)

A deterministic gate fires before the action and refuses it outright. This is reserved for two
cases: patterns that have been violated often enough that advice and warnings demonstrably did not
work, and a small set of preventive safety gates (the gating component from
[`01`](01-the-mapping.md), blocking a dangerous proposed action before it executes). Enforced rules are
allow/deny valves with no judgment in them, which is exactly why they can be fully automated. Use
this tier sparingly; everything here is something the agent can no longer do, including the
occasional case where it should.

## Promotion criteria

Rules earn their tier through evidence, not through how important they feel:

- A pattern violated **twice** is a signal that the advisory rule is not landing. Record it
  explicitly and tighten the written rule, rather than assuming a re-read will fix it.
- A pattern that keeps recurring after that is a candidate for **Tier 2**, where a guard makes the
  miss visible at the moment it happens.
- A pattern violated **repeatedly despite a Tier 2 warning** is a candidate for **Tier 1**, where it
  is blocked. Repetition under warning is the proof that the softer tiers are insufficient.
- The exception is **preventive safety**. A dangerous-action pattern identified by threat analysis can
  go straight to Tier 1 with no violation history, because the whole point of a safety gate is to
  block the first occurrence, not the third.

Promotion is not free, and it comes with an obligation. A guard that only adds enforcement, with no
feedback on whether the underlying mistake is actually getting rarer, tends to fail quietly:
enforcement accuracy goes up while the agent's own calibration does not improve. So a promotion
pairs the gate (the accuracy side) with a periodic, non-judgmental record of the trend (the insight
side). The framing matters: track "is this drifting better or worse over time," not "how many
violations this week." Surveillance framed as a running tally tends to backfire; the same data
framed as a trend is what actually drives the behavior change.

## CATCH ≠ PREVENTION

This is the load-bearing insight of the whole governance layer, and it is easy to get backwards.

These tiers do not *prevent* the agent's mistakes. The impulse to skip a step, estimate a number, or
give up early comes from the base model and does not go away. Governance does not remove the impulse;
it *catches* the impulse before it becomes an action. Every hook, guard, and advisory rule is an
externalized catch sitting downstream of a base-model tendency that is still there underneath.

Three consequences follow, and they change how you reason about the whole system:

1. **The success metric is catch-efficacy, not extinction.** "We added a guard and the violations
   stopped appearing" usually means the catch is working, not that the tendency is gone. Measuring
   for extinction will mislead you, because the impulse is structurally permanent.
2. **The first diagnostic question is about consumption, not existence.** When something slips
   through, the useful question is rarely "is there no rule for this?" It is "there is a catch for
   this; did an *independent* check actually consume it?" A system that catches its own mistakes by
   asking itself to check is prone to confabulation: it reports the check passed because it expects
   it to pass. Independence of the catch is what makes it real.
3. **New catches show diminishing returns.** Because the catches are downstream of a fixed set of
   base-model tendencies, the tenth guard adds far less than the first. Past a point, the productive
   move is not another catch; it is to spend the effort on the actual work the agent exists to do.
   A governance layer that keeps growing is usually avoiding that conclusion.

## Verdict-gated loops

The cleanest place to apply all of this is a loop whose continuation is gated by an explicit
verdict rather than by the model's sense that it is done.

A naive agent loop runs until the model decides to stop, which is the same judgment that produced
the mistake you are trying to catch. A verdict-gated loop instead runs a deterministic check at the
end of each pass and continues, retries, or escalates based on the check's result, not the model's
satisfaction. The check is the catch; the loop structure is what forces the catch to be consumed
every pass instead of when the model remembers to.

This is why an *executable harness* (the procedural-execution component from
[`01`](01-the-mapping.md)) beats a written procedure for anything multi-step: the harness runs the
verdict check on every iteration and cannot quietly skip it, whereas a procedure narrated by the
model can be abandoned the moment the first path fails. When the quality of an output depends on a
check actually running, put the check in code and gate the loop on it. Reserve the model's judgment
for the parts that genuinely require judgment, and let the deterministic gate carry the parts that
do not.

## Where this lives in the repo

Generic skeletons for an advisory self-check trigger and a blacklist-pattern guard are in
[`templates/hooks/`](../templates/hooks/). The short, adoptable rule set that lives at Tier 3,
including the self-verdict discipline that makes a catch independent, is in
[`04-principles.md`](04-principles.md).
