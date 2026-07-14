# Benchmark protocol

**Status: one reproducible full-dataset retrieval pilot completed; internal
operational A/B results exist; no release-grade public QA run completed.**

This directory defines what must be true before Brain-AI Memory can make a
public comparative performance claim. The live deployment and internal A/B
results are summarized in [evidence/](../evidence/), but their raw source data
remain private. The capacity simulation is not part of the benchmark scoreboard.

## Completed retrieval pilot

The first public-data comparison ran over all 500 cleaned LongMemEval-S
questions. It compares recency, full-session BM25, and keyword-pointer BM25 at
four compression levels. The strongest pointer setting used 93.0% less indexed
source text than full-session BM25 but scored 71.0% rather than 86.1%
answer-session recall@3.

This negative result shows that simple keyword pointers do not preserve the
full-text retriever's recall. It is retrieval-only: no reader LLM, QA accuracy,
consolidation, or reconsolidation was evaluated. Read the
[pilot report and raw artifacts](pilots/longmemeval-s-retrieval-20260714/README.md).

## What can be evaluated

The operational system contains a working memory stack, lifecycle rules,
semantic retrieval, guards, and harnesses. This public clean-room repo does not
ship that private backend. Therefore a release-grade public comparison still
requires a reference implementation that:

1. ingests the same timestamped history stream for every condition;
2. creates memory without seeing the future evaluation question;
3. retrieves evidence under a fixed context budget;
4. exposes consolidation and reconsolidation as independently removable
   modules; and
5. records every retrieved item, model call, token count, and latency.

The seven-component architecture is broader than conversational retrieval.
Long-term QA can test episodic/semantic memory and the two transfer channels.
Rule gating, fallback completion, exact numerical state, and input filtering
need separate task suites and must not be declared validated by a QA score.

## Preregistered hypotheses

### H1 — useful recall under a fixed budget

At the same reader model and context budget, a lifecycle index plus on-demand
detail improves downstream answer accuracy or reduces retrieved tokens relative
to append-only memory.

### H2 — update rather than accumulate

Reconsolidation improves knowledge-update and conflict-resolution accuracy
without reducing performance on unchanged facts.

### H3 — consolidation earns its cost

Promoting repeated episodes into semantic or procedural memory improves
multi-session reasoning or reduces retrieval cost relative to storing episodes
alone.

Failure to support any hypothesis is a valid result. The implementation and
report must preserve negative findings.

## Evaluation ladder

### Stage 1 — LongMemEval

[LongMemEval](https://github.com/xiaowu0162/LongMemEval) is the primary
release gate because its 500 questions cover information extraction,
multi-session reasoning, knowledge updates, temporal reasoning, and abstention.

Required conditions:

1. no external memory;
2. full history when it fits, with a disclosed truncation rule when it does not;
3. append-only memory under the same retrieval budget;
4. summarization or compaction;
5. a standard flat retrieval baseline;
6. Brain-AI pointer index only;
7. Brain-AI plus consolidation; and
8. Brain-AI plus consolidation and reconsolidation.

Oracle evidence may be used only to diagnose reader quality. It is not a valid
headline memory-system result.

### Stage 2 — MemoryAgentBench

[MemoryAgentBench](https://github.com/HUST-AI-HYZ/MemoryAgentBench) adds
accurate retrieval, test-time learning, long-range understanding, and conflict
resolution. This is the main test of the claim that memory is more than storage.

### Stage 3 — LongMemEval-V2

[LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) evaluates
environment state, workflows, recurring gotchas, and premise awareness across
long web-agent trajectories. It is the appropriate later test for procedural
execution and environment-specific experience, but it is too expensive and
broad to serve as the first implementation check.

## Controlled variables

The following must be identical across compared conditions:

- dataset version, split, and item order;
- reader model, revision, quantization, and system prompt;
- generation temperature, seed, and maximum output tokens;
- online ingestion order and access to timestamps;
- context and retrieval token budgets;
- scoring implementation and judge, if an LLM judge is unavoidable; and
- hardware class for latency comparisons.

Changing the reader model or importing numbers from another paper invalidates a
head-to-head claim. Results from different protocols may be reported in separate
rows, never as a direct comparison.

## Leakage and fairness rules

- The evaluation question and answer must not be available during ingestion.
- Answer-session identifiers and has-answer fields must be stripped before
  indexing.
- Handwritten rules may not mention benchmark item IDs or answers.
- Hyperparameters are selected on a development set and frozen before the test
  run.
- Failed or timed-out items remain in the denominator.
- Every condition receives the same number of retry attempts.
- Results include all benchmark categories, not only favorable subsets.

## Required metrics

### Quality

- answer accuracy overall and by question type;
- retrieval recall at k at session and turn granularity;
- knowledge-update or conflict-resolution accuracy;
- abstention accuracy; and
- accuracy as history length grows.

### Efficiency

- tokens written during ingestion;
- tokens retrieved and read per question;
- model calls per ingestion event and per query;
- wall-clock ingestion and query latency, with mean and p95; and
- final index and detail-store size.

### Reliability

- failures and timeouts;
- variance across at least three seeds for stochastic components; and
- paired confidence intervals over per-item differences.

## Ablations

The full system must be decomposed so the source of a gain is visible:

1. pointer index without lifecycle migration;
2. episodic/semantic separation;
3. consolidation added;
4. reconsolidation added;
5. time-aware retrieval added; and
6. any model-generated summary or rule extraction added.

An ablation that does not change behavior should not remain in the claimed
architecture on the strength of analogy alone.

## Artifacts for every run

Each run directory must contain:

- manifest.json — immutable configuration and aggregate metrics;
- predictions.jsonl — one record per benchmark item;
- retrieval.jsonl — ranked retrieved items and their token counts;
- events.jsonl — ingestion and query timing;
- stdout.log and stderr.log; and
- the SHA-256 digest of every artifact; and
- the exact reader and scoring prompts or their content hashes.

Start from [manifest.template.json](manifest.template.json) and validate with:

    python3 benchmarks/validate_manifest.py path/to/manifest.json

For a result intended to support a public claim:

    python3 benchmarks/validate_manifest.py path/to/manifest.json --release

The release check rejects incomplete or partial splits, non-official scoring,
oracle evidence, a dirty repository, artifacts outside the run directory,
missing or changed artifacts, placeholder hashes, and absent
quality/efficiency metrics.

## Claim release gate

A top-line statement such as “improves memory,” “beats RAG,” or “reduces cost”
may enter the main README only when:

1. the full registered split is complete;
2. all controlled variables are matched;
3. the release manifest validates;
4. raw per-item outputs are committed or permanently archived;
5. quality and efficiency are reported together;
6. uncertainty is reported; and
7. the wording is no broader than the evaluated task.

Until then, the README does not report a release-grade end-to-end improvement
claim.
