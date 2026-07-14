# Operational evidence

> Snapshot date: 2026-07-14. This report contains newly written aggregate
> evidence only. It does not copy private memory, project, or activity records.

Brain-AI Memory has operated as a live, single-owner, multi-project daily-driver
system since 2026-04-20. The public repository is a clean-room extraction from
that implementation. Its small examples are teaching artifacts, not the origin
or extent of the system.

## Evidence ladder

| Layer | Observation | What it supports | What it does not support |
|---|---|---|---|
| deployment | about 12 weeks of live evolution across 13 project memory indexes | the architecture was implemented and maintained longitudinally | effectiveness for other users or organizations |
| exposure | 419 instrumented sessions, 63,575,655 tokens, and 29 active days in a 35-day Command Center window | substantial opportunity for the system to be exercised | that memory caused usage or improved every session |
| operational substrate | 134 memory files, a 783-note semantic store, 455 decision/issue ledger records, and 3,286 policy events | persistent stores, governance, and intervention are wired into operation | that every record is correct or every event prevented harm |
| stable probes | nine scheduled snapshots with 18–21 probes each; 100% any-store pass in every snapshot | the curated cross-store recall checks remained reachable | broad semantic recall or downstream QA accuracy |
| store-specific probes | vector-only pass rate ranged from 33.3% to 100% | monitoring exposes channel-specific weakness instead of hiding it behind the aggregate | stable vector retrieval quality |
| internal A/B | two same-corpus retrieval comparisons described below | indicative component-level gains under the tested stacks | independent or multi-user replication |
| public-data retrieval | 1,531 answerable LoCoMo questions across all 10 samples | a stack-aligned retriever was compared with BM25 and graph-lite conditions | end-to-end QA or a release-grade public artifact bundle |

The exposure window is 2026-06-10 through 2026-07-14. It is shorter than the
full deployment history because the current Command Center session series
starts later.

## Internal retrieval A/B results

### Auto-memory pointer retrieval

The evaluation used 116 pointer-to-file probes over 128 operational memory
files. Both conditions received the same query text and corpus.

| Retriever | HIT@1 | HIT@5 | HIT@10 |
|---|---:|---:|---:|
| grep control | 39.66% | 60.34% | 68.97% |
| production per-file embedding | 67.24% | 81.03% | 88.79% |
| production section embedding | 60.34% | 83.62% | 88.79% |
| hybrid reciprocal-rank fusion | 53.45% | 73.28% | 81.03% |

The per-file embedding recovered 25 of the 36 targets missed by grep at top 10
(69.44%). This is an indicative A/B result: the pointer text summarizes its
target, which can inflate both arms' absolute scores, and the gold links are a
lower bound on semantic relevance.

### Semantic-note graph augmentation

The evaluation used 690 source notes and 5,936 human-curated relationships. It
compared note-level embedding retrieval with graph augmentation at the same
result budget.

| Retriever | HIT@5 | recall@5 | HIT@10 | recall@10 |
|---|---:|---:|---:|---:|
| embedding | 80.43% | 29.63% | 86.23% | 41.02% |
| equal-budget graph hybrid | 87.25% | 36.03% | 91.88% | 48.79% |

The graph condition improved HIT@10 by 5.65 percentage points and recall@10 by
7.77 points. The relevance labels are curated links and the graph uses that
same relationship family, so this is a generous evaluation of graph value, not
a neutral benchmark against every relevant-note definition.

### LoCoMo retrieval evaluation

A separate evaluation used the public LoCoMo dataset and a 768-dimensional GTE
index aligned with the system's parallel/legacy retrieval stack. It evaluated
all 1,531 answerable questions across the dataset's 10 conversation samples.
Category 5 adversarial or unanswerable items and items without usable gold
evidence were excluded before the retrieval comparison.

| Retriever | HIT@1 | HIT@5 | HIT@10 |
|---|---:|---:|---:|
| GTE embedding | 26.06% | 51.34% | 62.12% |
| BM25 | 25.60% | 47.62% | 56.96% |
| lightweight graph PPR | 26.26% | 47.09% | 51.93% |

The metric asks whether at least one gold evidence turn appears in the top k;
it is not question-answering accuracy. GTE led at k=5 and k=10, while the
lightweight graph condition underperformed both GTE and BM25 at k=10. The graph
negative result was retained rather than folded into the more favorable
semantic-note graph A/B above because the graph construction and gold labels
were different.

## Longitudinal health and lifecycle evidence

The operating system schedules deterministic recall checks across memory,
entity, and vector stores. All nine snapshots between 2026-06-12 and 2026-07-12
passed the overall any-store criterion, with 18 probes initially and 21 later.
The vector-only rate fluctuated, which is why the overall result is not promoted
as “100% retrieval accuracy.”

Two recorded lifecycle episodes reduced overloaded indexes from 51,014 to
26,645 bytes (47.8%) and from 36,366 to 26,103 characters (28.2%) while retaining
archived detail. One separate verification caught a lossy model-generated
compaction attempt; that failure changed the operating rule toward archive-first
preservation. Current monitoring still reports recall-cap warnings, so the
deployment is not presented as uniformly green.

Operational audits also changed the implementation: a stale semantic index was
rebuilt, a producer/consumer gap was found where a store existed but intake had
stopped, and deterministic guard loops were distinguished from executable
fallback loops. These are qualitative repair cases, not scored benchmark wins.

## Harness closure status

An audit of the live call paths found the deterministic rule and input-gating
loops closed. Episodic, semantic, executable-procedure, numerical, and transfer
loops were partially closed or depended on manual triggers. Semantic executive
routing remained open. This matters because a component appearing in the
ontology is not evidence that its complete feedback loop is operational.

## Interpretation rules

- Session and token counts are **exposure**, not benefit.
- Policy events are fires, rewrites, warnings, or blocks; they are not 3,286
  proven harms prevented.
- Stable probes are curated regression checks; they are not a representative
  distribution of user questions.
- Internal A/B deltas are evidence about tested components, not the causal
  effect of the entire seven-component architecture.
- The LoCoMo aggregate is a retrieval evaluation on public data, but the
  per-item artifact bundle has not been clean-room released from the private
  evaluation environment.
- Raw operational records cannot be published under the clean-room rule. The
  aggregate snapshot is auditable inside the source system but not independently
  reproducible from this public repo.
- External generalizability remains unknown because this is one owner's
  longitudinal, multi-project deployment rather than a multi-organization trial.

For reproducible public-data evidence, see the
[LongMemEval-S retrieval pilot](../benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md).
For the stronger external claim gate, see the
[benchmark protocol](../benchmarks/README.md).
