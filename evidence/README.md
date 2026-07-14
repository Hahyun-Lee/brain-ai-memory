# Evidence

Brain-AI Memory is a clean-room extraction from a real daily-driver system, not
a design backed only by small synthetic examples. The deployment is longitudinal
and spans multiple projects, stores, hooks, and workflows under one owner. That
is strong evidence of implementation and operational exposure, but it is not
independent multi-user validation or proof of superiority.

The evidence is separated by what it can support:

1. [Operational evidence](operational-evidence.md): live deployment scale,
   health probes, lifecycle episodes, and internal A/B retrieval results.
2. [Sanitized aggregate snapshot](operational-snapshot-2026-07-14.json): the
   machine-readable numbers behind that report.
3. The capacity simulation below: a reproducible mechanism test using synthetic
   data.
4. [Public benchmark artifacts](../benchmarks/README.md): reproducible public
   data pilots and the release gate for external QA claims.

## What is claimed, and what is not

**Claimed.** The failure mode the memory lifecycle (docs/02) is built to prevent
is real and mechanical: under a fixed recall budget, append-only memory growth
silently evicts old-but-needed facts, and a one-line-index-plus-on-demand-detail
discipline raises the point at which that happens.

**Not claimed.** That the discipline makes a real LLM agent smarter, that it
dominates every workload, or that a single-owner longitudinal deployment is a
controlled comparison. The simulation below models index capacity, not an LLM.

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
