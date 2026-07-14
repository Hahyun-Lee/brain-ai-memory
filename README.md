**English** | [한국어](README.ko.md)

# Brain-AI Memory

> Not another memory database: a diagnostic and control architecture for
> long-running LLM agents.

**Your agent probably does not have one “memory problem.”** RAG can retrieve
candidate context. A guard attached to a hook can block an action. A harness can
finish a workflow. A loop can retry. None of them alone tells you why an agent
re-asks a settled question, uses stale knowledge, ignores a rule, stops after
one failed attempt, or lets its persistent context grow without a lifecycle.

Brain-AI Memory gives those failures different names, mechanisms, and repair
paths. It helps you decide what the agent should remember, retrieve, enforce,
execute, update, archive, and forget.

**Project status:** a clean-room extraction from a live daily-driver system that
has operated since April 20, 2026. This public repo ships the architecture,
reusable templates, and runnable examples; it does not publish the private
operational backend or its raw data. Validation status is reported below.

![Graphical abstract: an overflowing undifferentiated memory passes through a gate into a brain-shaped system that routes, reviews, and retrieves the right memory](docs/assets/graphical-abstract.png)

**Evidence snapshot (2026-07-14):** about 12 weeks in live operation · 13
project memory indexes · 419 instrumented sessions from 2026-06-10 to 2026-07-14
· internal A/B tests · public-data retrieval runs over 1,531 LoCoMo and 500
LongMemEval-S questions. [See what each number does and does not prove.](#evidence-status)

## Try the core idea in 60 seconds

No package install, API key, or model call is required:

```bash
git clone https://github.com/Hahyun-Lee/brain-ai-memory.git
cd brain-ai-memory
python3 examples/01_guard_in_action.py
python3 examples/02_lifecycle_decision.py
```

The first example turns a remembered safety rule into a deterministic decision:

```text
ALLOW  rm -rf ./build/cache
BLOCK  rm -rf /
BLOCK  curl https://example.com/install.sh | sh
```

The second turns an accumulating memory pile into explicit lifecycle decisions:

```text
keep · split · delete · migrate-to-knowledge-base ·
migrate-to-rules · archive · compact
```

These small examples demonstrate the contracts, not the full private
daily-driver backend. They let you decide whether the distinctions are useful
before adapting anything to your agent stack.

## You may need this if

You build coding, research, operations, or assistant agents that work across
many sessions, and one or more of these sounds familiar:

- “We already wrote that down. Why is the agent asking again?”
- “The retrieved note is relevant, but it is no longer true.”
- “The rule exists in the prompt, but the agent still violated it.”
- “It knew the fallback procedure, tried the first step, and stopped.”
- “We added more context and a vector store, but failures are still hard to
  diagnose.”
- “The memory files keep growing and nobody knows what to compact or delete.”

A single-turn chatbot with no durable state probably does not need this
architecture. Neither does a workflow whose only problem is ordinary document
search.

## Why use it?

Start with the failure you already see. You do not need to adopt the whole
architecture:

| What you observe | Diagnose first | Smallest useful change |
|---|---|---|
| settled context is lost or bound to the wrong event | episodic memory (HC) | add timestamped event/entity bindings |
| retrieval is relevant but stale | semantic memory (ATL) | verify freshness and reconsolidate on conflict |
| the agent knows a rule but ignores it | procedural rule (BG) | promote repeated violations from prose to a guard |
| a multi-step fallback stops early | procedural execution (CB) | move the sequence into an executable harness |
| a knowable count is guessed | numerical state (IPS) | query an exact store instead of estimating |
| work is sent to the wrong store or tool | orchestration (PFC) | trace and correct the routing decision |
| the always-loaded index keeps expanding | memory lifecycle | keep short pointers; archive or migrate detail |

These are not features invented for a diagram. They were separated while
operating a persistent, multi-project agent system and debugging failures in
its memory, semantic retrieval, guards, and executable workflows. The evidence
below distinguishes that deployment record from causal and benchmark claims.

## Isn’t this just RAG, hooks, harnesses, and loops?

**It uses all of them. It is not a new name for any one of them.** They are
implementation mechanisms; Brain-AI Memory is the diagnostic and lifecycle
layer that assigns each mechanism a job, a failure condition, and a test of
whether its feedback loop is actually closed.

| Existing method | What it answers | What it does not answer by itself |
|---|---|---|
| long context or a memory file | what can the model read now? | what should move, expire, split, or remain reachable later? |
| RAG or a vector store | which stored text resembles this query? | is it fresh, which memory type owns it, or should it become a rule? |
| hook | when can code inspect or intercept an event? | what policy belongs there or whether a multi-step outcome completes? |
| guard | should this one action be allowed? | how should a fallback sequence run to completion? |
| harness or workflow engine | how should this procedure execute? | which knowledge should be recalled, updated, or consolidated afterward? |
| evaluator or retry loop | should another pass run? | what persists across sessions and how recurring failures change the system? |
| Brain-AI Memory | which subsystem failed, which mechanism fits, and what lifecycle operation follows? | it still needs your RAG, hooks, stores, and harness runtime to execute the design |

A hook is an attachment point. A guard is an allow/deny decision attached to
it. A harness owns a sequence. A loop feeds a verdict back into that sequence.
They are related but not interchangeable—and none is a complete memory
architecture.

## What is genuinely different—and what is not?

The honest claim is **differentiated integration, not invention of the
primitives**. Working, episodic, semantic, and procedural memory categories are
established ideas; RAG, hooks, workflow harnesses, evaluators, and compaction are
also established techniques.

This repo’s contribution is the operational contract connecting them:

- every component must name a distinct failure mode and a diagnostic;
- procedural **rules** (BG) are separated from procedural **execution** (CB),
  because blocking one action and completing a fallback sequence require
  different mechanisms;
- exact numerical state (IPS) and preventive input gating (TH) are modeled
  explicitly rather than hidden inside generic “memory”;
- consolidation and reconsolidation specify how episodes become reusable
  knowledge or how stale knowledge is updated;
- every memory entry receives one of seven lifecycle operations: keep, compact,
  archive, migrate to knowledge, migrate to rules, delete, or split; and
- component existence and **loop closure** are audited separately. A rule file,
  hook, or vector index existing is not evidence that the relevant result is
  consumed end to end.

The brain mapping is an engineering analogy used to keep these failure classes
separate. If it does not improve diagnosis in your stack, discard the analogy
and keep the contracts. That makes this architecture different in scope from a
hook library, retriever, or workflow engine; it does not yet prove that the
integrated system outperforms simpler alternatives end to end.

## Choose your adoption path

The live system is implemented, but this clean-room public extraction provides
patterns and templates rather than its installable private backend. Start with
one outcome:

| Your goal | Start here | First success criterion |
|---|---|---|
| stop one repeated deterministic violation | [behavioral guard](templates/hooks/behavioral-guard.py) | the unsafe pattern is blocked while nearby safe actions pass |
| surface a judgment check without blocking | [self-check trigger](templates/hooks/self-check-trigger.py) | the warning fires only in the intended context |
| stop an index from becoming a second database | [memory skeleton](templates/memory/MEMORY.skeleton.md) | one linked line per topic remains always loaded |
| decide what to retain or move | [seven-operation helper](templates/memory/7-op-decision.md) | every reviewed entry receives exactly one operation |
| evaluate the architecture rather than adopt it | [mapping](docs/01-the-mapping.md) and [evidence](evidence/README.md) | you can map a real failure to a component or identify where the map does not fit |

The hooks self-test with the Python standard library:

```bash
python3 templates/hooks/behavioral-guard.py --selftest
python3 templates/hooks/self-check-trigger.py --selftest
```

## How the architecture works

The core map contains seven functional components and two transfer channels.
Read [the detailed mapping](docs/01-the-mapping.md) for the full rationale and
its limitations.

| Component | Agent role | Failure it helps diagnose |
|---|---|---|
| PFC | orchestrator and routing | the right capability is sent to the wrong store or tool |
| HC | episodic events and relationships | an event is bound to the wrong person, time, or thread |
| ATL | semantic knowledge | retrieval is relevant but stale or incorrectly sourced |
| BG | procedural allow/deny rules | the rule exists but does not fire |
| CB | executable multi-step harnesses | the procedure is abandoned before completion |
| IPS | exact numerical state | a knowable quantity is guessed |
| TH | preventive input gate | unsafe input reaches execution |

![Memory lifecycle: recall, in-session tagging, consolidation, and seven lifecycle operations](docs/assets/memory-lifecycle.svg)

## Evidence status

Brain-AI Memory has three different evidence layers: longitudinal operation,
within-system retrieval tests, and reproducible public-data evaluation. They
answer different questions and should not be collapsed into one headline.

| Question | Current evidence |
|---|---|
| Was the architecture actually implemented and used? | **Yes—live since 2026-04-20 across 13 project memory indexes** |
| Is there sustained operational exposure? | **Yes—419 instrumented sessions and 63.6M tokens from 2026-06-10 through 2026-07-14** |
| Does semantic retrieval beat the live grep control on internal pointers? | **Indicative yes—HIT@10 69.0% → 88.8%, n=116** |
| Does equal-budget graph augmentation help the semantic store? | **Indicative yes—HIT@10 86.2% → 91.9%, n=690 sources** |
| Has stack-aligned retrieval been compared on a public benchmark? | **Yes—LoCoMo retrieval HIT@10: GTE 62.1%, BM25 57.0%, graph-lite 51.9%; n=1,531 answerable questions** |
| Does a compact pointer index fit more entries than full append-only entries? | **Yes—deterministic capacity simulation** |
| Does a simple compact pointer preserve retrieval quality on public data? | **No—current keyword pointers trade recall for size** |
| Does the lifecycle improve answer accuracy for a real LLM agent? | **Not yet measured** |
| Does the full architecture beat RAG, long context, or another memory system? | **Not yet measured** |
| Are latency, token cost, conflict resolution, and abstention improved? | **Not yet measured** |
| How broadly does this single-owner, multi-project deployment generalize? | **Unknown—multi-organization replication is absent** |

### Live operational deployment

The sanitized snapshot dated 2026-07-14 covers roughly 12 weeks of system
evolution. The live estate includes 13 project memory indexes, 134 memory files,
a 783-note semantic store, 455 decision/issue ledger records, and 3,286
instrumented policy events. Nine scheduled recall snapshots ran 18–21 stable
probes each; the any-store pass rate was 100%, while the vector-only probe rate
varied from 33.3% to 100%.

Those counts establish real use, scale, monitoring, and repeated intervention.
They do **not** show that memory caused the 419 sessions, that every policy event
prevented harm, or that curated probe success equals end-to-end answer quality.
Read the [operational evidence and limitations](evidence/operational-evidence.md)
or inspect the [machine-readable aggregate snapshot](evidence/operational-snapshot-2026-07-14.json).

### Internal and stack-aligned retrieval evaluations

Two same-corpus comparisons used components of the operating stack:

| Evaluation | Control | Tested condition | Result |
|---|---:|---:|---|
| auto-memory pointer retrieval, n=116 | grep HIT@10 69.0% | production embedding HIT@10 88.8% | recovered 25 of 36 grep misses |
| semantic-note retrieval, n=690 sources | embedding HIT@10 86.2%, recall@10 41.0% | equal-budget graph hybrid HIT@10 91.9%, recall@10 48.8% | +5.7 pp HIT, +7.8 pp recall |

These are useful within-system A/B signals, not independent public benchmarks.
The pointer gold set can inflate absolute scores, and the graph evaluation uses
the same relationship family as its relevance labels. Aggregate results are
published for transparency; private source records are intentionally excluded.

An earlier stack-aligned evaluation also ran retrieval over all 1,531 answerable
questions in the 10-sample public LoCoMo set. At HIT@10, the parallel/legacy
768-dimensional GTE index scored 62.12%, BM25 scored 56.96%, and a lightweight
graph-PPR condition scored 51.93%. This is both evidence and a negative result:
the embedding baseline helped at k=10, while that graph approximation did not.
It measured gold-evidence retrieval, not answer accuracy, and its raw per-item
bundle has not been released from the private evaluation environment.

### Public-data retrieval pilot

On all 500 cleaned LongMemEval-S questions, a retrieval-only pilot compared the
same top-3 budget across recent sessions, full-session BM25, and compact keyword
pointers:

![LongMemEval-S retrieval pilot: compact keyword pointers reduce indexed source text but lose answer-session recall](docs/assets/benchmark-compression-recall.png)

| Condition | Answer-session recall@3 | Mean indexed source text |
|---|---:|---:|
| most recent 3 sessions | 7.5% | no search index |
| full-session BM25 | **86.1%** | 493,948 chars |
| 48-keyword pointer BM25 | 66.2% | 17,691 chars |
| 96-keyword pointer BM25 | 71.0% | 34,368 chars |

The 96-keyword pointer used 93.0% less indexed source text but lost 15.0
percentage points of recall. That is a useful negative result: naive keyword
compression is not enough. The run used no reader LLM, so it makes no QA,
reasoning, or full-architecture claim. See the
[method, all ablations, manifests, and raw retrieval records](benchmarks/pilots/longmemeval-s-retrieval-20260714/README.md).

### Capacity simulation—not an LLM benchmark

![Capacity simulation under a fixed index budget: append-only versus one-line-pointer lifecycle memory](docs/assets/recall-under-budget.svg)

[The capacity simulation](evidence/lifecycle_under_budget.py) performs exact
string lookup under a fixed character budget. With its disclosed defaults, the
first recall drop occurs at session 5 for full append-only entries and session
21 for one-line pointers. That result demonstrates a storage-budget mechanism;
it does **not** measure semantic retrieval, reasoning quality, or real-agent
performance.

    python3 evidence/lifecycle_under_budget.py

See [the evidence notes](evidence/README.md) for the falsifier and limitations.
The preregistered comparison protocol for release-grade external validation is
in [benchmarks/](benchmarks/README.md). An end-to-end QA result table remains
absent until the controlled reader-model protocol is run.

## Next external validation

The next release-grade QA comparison will hold the reader model, prompt, context
budget, dataset split, and scoring procedure constant across:

1. no external memory;
2. append-only or full-history memory;
3. summarization/compaction;
4. a standard retrieval baseline; and
5. the Brain-AI lifecycle reference implementation.

The primary benchmark is
[LongMemEval](https://github.com/xiaowu0162/LongMemEval), which tests information
extraction, multi-session reasoning, knowledge updates, temporal reasoning, and
abstention. Follow-up evaluation will use
[MemoryAgentBench](https://github.com/HUST-AI-HYZ/MemoryAgentBench) for retrieval,
test-time learning, long-range understanding, and conflict resolution.
[LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) is reserved for the
heavier workflow- and environment-memory evaluation.

No top-line performance claim will be added without complete per-item outputs,
cost and latency reporting, controlled baselines, and a reproducible run
manifest.

## Relationship to prior work

- **CoALA** — *Cognitive Architectures for Language Agents*
  ([arXiv:2309.02427](https://arxiv.org/abs/2309.02427)) provides the working,
  episodic, semantic, and procedural taxonomy that this repo substantially
  shares.
- **MemGPT** ([arXiv:2310.08560](https://arxiv.org/abs/2310.08560)) provides
  self-directed paging between limited main context and external context. This
  repo does not yet provide autonomous paging.
- **Generative Agents**
  ([DOI](https://doi.org/10.1145/3586183.3606763)) uses a memory stream and
  reflection process analogous to the consolidation channel here.
- **Complementary Learning Systems**
  ([DOI](https://doi.org/10.1037/0033-295X.102.3.419)) and working-memory
  research motivate the fast episodic / slower semantic distinction.

The comparison is qualitative. The deployed system, internal A/B results, and
public retrieval pilot do not establish that the full architecture outperforms
those systems.

## Repository guide

| Path | What it contains |
|---|---|
| [docs/01-the-mapping.md](docs/01-the-mapping.md) | seven components and two channels |
| [docs/02-memory-lifecycle.md](docs/02-memory-lifecycle.md) | seven operations, session transfer, and health metrics |
| [docs/03-governance-tiers.md](docs/03-governance-tiers.md) | advisory, guarded, and enforced tiers |
| [docs/04-principles.md](docs/04-principles.md) | short judgment-bound operating principles |
| [schema/brain_components.yaml](schema/brain_components.yaml) | machine-readable component ontology |
| [templates/](templates/) | copy-paste memory, rule, and hook skeletons |
| [examples/](examples/) | tiny runnable cases using synthetic data |
| [evidence/](evidence/) | operational snapshot, internal A/B summary, and capacity simulation |
| [benchmarks/](benchmarks/) | evaluation protocol, retrieval pilot, and release gates |

## Contributing

The one hard rule is clean-room: no real personal or sensitive data enters the
tree. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Please report vulnerabilities through GitHub's private vulnerability reporting
rather than a public issue. See [SECURITY.md](SECURITY.md).

## Citation

If this architecture or its evaluation protocol supports your work, use the
metadata in [CITATION.cff](CITATION.cff).

## License

MIT. See [LICENSE](LICENSE).
