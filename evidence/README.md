# Evidence

Brain-AI Memory is a clean-room extraction from a real daily-driver system, not
a design backed only by small synthetic examples. The deployment is longitudinal
and spans multiple projects, stores, hooks, and workflows under one owner. That
is strong evidence of implementation and operational exposure, but it is not
independent multi-user validation or proof of superiority.

The evidence is separated by what it can support. Operational exposure,
memory-management performance, and software conformance are not interchangeable.

## Evidence ladder

### 1. Operational reality—not efficacy

- [Operational evidence](operational-evidence.md) reports live deployment
  scale, health probes, lifecycle episodes, and internal A/B retrieval results.
- The [sanitized aggregate snapshot](operational-snapshot-2026-07-14.json)
  contains the machine-readable numbers behind that report.

This establishes that the architecture was implemented, exercised, monitored,
and repaired longitudinally. It does not establish that the architecture
caused better agent outcomes.

### 2. Primary memory-management evidence

- The operating stack has indicative same-system pointer and semantic-store
  retrieval A/B results. The operational report also includes an aggregate
  public-data LoCoMo comparison over all 1,531 answerable questions in its 10
  samples; its private per-item evaluation bundle is not published here.
- The [LongMemEval-S retrieval pilot](../benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md)
  is the fully reproducible public-data result: 500 cleaned questions with raw
  per-item artifacts. Its important result is negative—the 96-keyword pointer
  used 93.0% less indexed text than full-session BM25, but answer-session
  recall@3 fell from 86.1% to 71.0%.
- The capacity simulation below is a synthetic mechanism check. It shows how a
  compact index delays overflow under its disclosed fixed budget; it is not a
  semantic-retrieval or LLM benchmark.

These results cover operational exposure, retrieval behavior, and one capacity
mechanism. They do not yet evaluate the complete memory lifecycle end to end.
The [benchmark protocol](../benchmarks/README.md) defines the controlled public
comparison still required.

### 3. Supporting memory-to-action contract verification

The [ten-mechanism lifecycle/control ablation](../benchmarks/pilots/component-ablation-20260715/README.md)
contains 20 deterministic cases under 21 cumulative and leave-one-out
conditions, with 420 raw records. It verifies authored typed-routing,
exact-state, gating, fallback, consolidation, reconsolidation, and checkpoint
contracts. It is software conformance evidence, not representative
memory-management performance or LLM efficacy.

### What is still missing

No completed public end-to-end comparison yet shows that the full lifecycle
improves reader-model answer accuracy, knowledge-update or conflict-resolution
accuracy, abstention, cost, or latency against matched memory baselines. The
supporting conformance result cannot fill that evidence gap.

## What is claimed, and what is not

**Claimed.** The architecture has sustained operational exposure; tested
retrieval components have disclosed positive and negative results; and, under
the capacity simulation's fixed budget, a one-line-index-plus-on-demand-detail
discipline raises the point at which overflow begins.

**Not claimed.** That the complete lifecycle makes a real LLM agent smarter,
that the lifecycle/control conformance score is a memory-performance score,
that Brain-AI dominates every workload, or that a single-owner longitudinal
deployment is a controlled comparison. The simulation below models index
capacity, not an LLM.

## The capacity simulation

[`lifecycle_under_budget.py`](lifecycle_under_budget.py) is a deterministic
capacity simulation. It compares two index representations on identical
synthetic entries, exact-string queries, and a fixed character budget.
Append-only loads full entries; lifecycle loads one-line pointers and fetches
detail on demand. The same truncation rule is applied to both.

Run it yourself (stdlib only, no setup):

```
python3 evidence/lifecycle_under_budget.py
```

### Capacity result (default parameters)

With an 800-char index budget and ~200-char entries, append-only spends ~250
chars per entry in the index and the lifecycle policy spends ~39:

| sessions stored | append-only recall | lifecycle recall |
|---|---|---|
| 1–4 | 100% | 100% |
| 5 | 80% | 100% |
| 8 | 50% | 100% |
| 12 | 33% | 100% |
| 20 | 20% | 100% |
| 21 | 19% | 95% |
| 24 | 17% | 83% |

(Here, “recall” means exact-string answerability in the simulation. It is not
semantic retrieval or LLM question-answering accuracy.)

### How to read it

Three things in that table matter, and the third is the honest one:

1. **Sessions 1–4: no difference.** While everything fits under budget, both
   policies score 100%. The discipline buys nothing here, and the script says so.
   A valid mechanism check must contain this no-effect region.
2. **From session 5, append-only degrades.** Each new session pushes the
   oldest entries past the front of the budget, so queries about early facts
   fail. This is the docs/02 failure mode happening on cue: the store becomes
   write-only for anything old.
3. **The lifecycle policy has its own ceiling.** It holds 100% only to session
   20; at 21 its one-line index also begins to overflow and recall drops too. The
   discipline raises the ceiling about 4x (first failure at session 21 vs. 5), it
   does not remove it. A simulation showing 100% lifecycle recall forever
   would be hiding this, and it does not.

*On eviction direction:* this models context-window-style truncation, where the
oldest entries fall off the front as newer ones arrive. A file-based store read
top-down can truncate the other end instead (the newest appends drop off). The
claim here does not depend on which end is lost: both policies truncate by the
exact same rule, so the only thing that changes between them is how many entries
fit before overflow — the ceiling, not the direction.

### The built-in falsifier

The advantage is conditional on cumulative memory exceeding the budget. Enlarge
`BUDGET`, or shrink `DETAIL_CHARS` so nothing overflows, and the two policies
converge to identical scores. The effect is a direct, disclosed consequence of
the budget being exceeded, not an artifact tuned to favor the discipline.

## Why keep the simulation

The live evidence shows that the architecture exists and has been exercised;
the simulation isolates one mechanism in a form anyone can reproduce without
private data. Neither substitutes for a controlled end-to-end comparison.

The controlled protocol and release gates for that comparison are in
[`../benchmarks/README.md`](../benchmarks/README.md). Do not describe this
simulation as a benchmark or the 4x capacity threshold as a 4x improvement in
agent memory.
