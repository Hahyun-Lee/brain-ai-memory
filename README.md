**English** | [한국어](README.ko.md)

# Brain-AI Memory — Memory Management for Long-Running Agents

> **Retrieval finds text. Memory management decides what stays, changes, and
> reaches the next session.**

Brain-AI Memory is an installable, local, provider-neutral **reference kernel
for typed operational memory** in agents that work across sessions. It stores
host-selected records as episodic events, semantic knowledge, procedural rules,
and exact state; binds them to stable entities and source labels; and provides
scoped recall, consolidation, supersession, lifecycle decisions, and handoff
primitives.

Keep your model, RAG, vector store, tools, and workflow engine. Brain-AI Memory
manages what retrieval alone does not: what kind of memory a record is, what it
belongs to, whether it is still active, and what it should become next.

An optional **memory-to-action bridge** can check proposed actions and run a
host-supplied fallback sequence. That bridge consumes managed memory; it is not
the memory manager itself.

**The core problem is memory continuity:** can the next session reconstruct the
right entity, current knowledge, exact state, applicable procedure, source,
and unresolved work without treating every old trace as equally current?

> **Scope of the public alpha.** This package owns structured local stores,
> entity-scoped candidate recall bundles, stored-entry lifecycle state, audit,
> and checkpoints. The host still owns transcript capture, selection and
> ingestion, token-budgeted model context, autonomous scheduling, physical
> retention/deletion, and production action enforcement.

## See the managed lifecycle in one minute

No API key, model call, database server, or external service is required.

```bash
git clone https://github.com/Hahyun-Lee/brain-ai-memory.git
cd brain-ai-memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

brain-ai tour
```

```text
Brain-AI Memory · managed memory → optional control → durable handoff
1  BIND     Atlas 2.1 → belongs_to → Atlas
2  RECALL   Atlas 2.1 release day is Thursday.
3  STATE    open_reviews = 3
4  GUARD    blocked — release approval is required before production deployment
5  FALLBACK completed after 2 attempts
6  UPDATE   old fact → superseded by → new fact
✓  HANDOFF  checkpoint <id>
```

The memory-management path is `BIND → RECALL/STATE → UPDATE → HANDOFF`: an
entity-scoped episode is recalled, stale knowledge is superseded, exact state
is preserved, and the next session gets a durable checkpoint. `GUARD →
FALLBACK` demonstrates the optional memory-to-action bridge. The tour makes
both paths inspectable under `./.brain-ai/`.

## Who should use this?

| Audience | Fit |
|---|---|
| agent, workflow, or research-tool builders | **Yes—the primary audience**, when they need typed memory, entity scope, source trails, lifecycle, and handoff across sessions |
| teams operating auditable local agents | **Yes**, when memory changes and sources must remain inspectable; production hardening is still required |
| Codex or Claude Code power users | **Yes**, when they can configure explicit recall, remember, consolidation, and checkpoint calls; this is not a drop-in replacement for built-in memory |
| RAG, Obsidian, or vector-store users | **Yes**, when retrieval works but scope, staleness, consolidation, or session continuity does not |
| ordinary ChatGPT/Claude users seeking a better one-off chat | **No direct need**; they may benefit indirectly from an application built with it |
| one-shot agents or ordinary document search | **Usually no**; use context or RAG first |

Use it when memory keeps growing without a lifecycle, project identities mix,
stale facts remain active, exact state is buried in prose, reusable episodes
never become knowledge, or the next session cannot recover the previous
decision and its source. It is infrastructure for people who configure agents,
not a consumer chat application.

Codex/Claude session resume and built-in memory remain useful. Do not replace
them if they already solve your problem. Brain-AI Memory is for the narrower
case where operational memory must be provider-neutral, typed, inspectable,
source-labeled, lifecycle-managed, and deliberately carried across agents or
workflows.

![Graphical abstract: a host selects a few records from raw session evidence and maps them into separate episode, knowledge, relationship, procedure, and exact-state compartments; the agent receives scoped context, while a separate lower lane checks only a proposed action before an executable sequence can reach a tool](docs/assets/graphical-abstract.png)

**Primary path:** host-selected evidence → managed memory → scoped context.
**Optional bridge:** proposed action → gate → executable sequence.

## What the system manages

| Memory-management responsibility | What the public alpha does |
|---|---|
| selected evidence | records only events the host explicitly sends; provider transcripts remain host-owned raw evidence |
| working-context candidate | reconstructs an entity-scoped, record-count-limited bundle for the host to place within its own token budget |
| episodic memory | preserves timestamped events and entity bindings in an append-only source |
| semantic memory | stores sourced reusable knowledge and versions stale facts through supersession |
| procedural memory | stores explicit rules and promotes episode candidates only after preview and approval |
| exact state | keeps knowable values in a typed store rather than asking the model to estimate them |
| lifecycle and handoff | records consolidation, reconsolidation, logical active/inactive decisions, audit, and checkpoint primitives |

Entity relations, source labels, and the validated component ontology cut
across these stores. The runtime does **not** automatically scrape provider
sessions, page memory into a model, compact or split files, or physically erase
source bytes. Its `limit` bounds records, not tokens. Those host-integration and
retention boundaries are explicit below.

## Manage memory locally

Bind memory to a stable project, release, person, or other entity so similarly
named events, facts, and values do not leak across scopes:

```bash
brain-ai entity add --name "Atlas" --type project --alias A
brain-ai remember --type episodic --entity Atlas \
  --text "The release moved to Thursday" --promote semantic
brain-ai remember --type state --entity Atlas --key open_reviews --value 3
brain-ai run --entity Atlas \
  "What changed recently and how many reviews remain?"
brain-ai consolidate          # preview
brain-ai consolidate --apply  # explicit promotion
brain-ai checkpoint --summary "release review complete"
```

The component ontology is validated when the runtime starts. Inspect it with
`brain-ai ontology`; the canonical schema remains
[`schema/brain_components.yaml`](schema/brain_components.yaml).

## Optional: connect managed memory to an agent

Install the optional MCP surface:

```bash
python -m pip install ".[mcp]"
brain-ai-mcp --home /absolute/path/to/.brain-ai
```

Add the server to any MCP client using the equivalent of:

```json
{
  "mcpServers": {
    "brain-ai-memory": {
      "command": "brain-ai-mcp",
      "args": ["--home", "/absolute/path/to/.brain-ai"]
    }
  }
}
```

Codex CLI/desktop/IDE and Claude Code support local MCP servers. A configured
host integration calls `brain_context` for scoped recall, `brain_remember` for
selected events or exact state, and `brain_checkpoint` for a handoff. If
promotion is wanted, it separately previews and applies `brain-ai consolidate`;
none of these calls happens in the background.

The public runtime does not scrape or archive a provider's native chat
transcript, and this repository includes no Claude Code JSONL or Codex rollout
adapter. Such a trace is raw evidence—not working memory by itself. An
integrating host or custom adapter decides, under an explicit privacy and
retention policy, whether to retain the trace and which selected events to map
into HC. If a raw trace is retained, preserve it as evidence rather than
rewriting it in place. Backup, access control, encryption, and deletion remain
host responsibilities.

### Optional memory-to-action enforcement

The same MCP surface also exposes `brain_check_action`, but it intentionally
does **not** expose arbitrary shell execution. The host remains responsible for
executing allowed actions. MCP connection alone is not enforcement: the host
must consume `gate.allowed = false` as a stop condition. For deterministic
blocking, route execution through `brain-ai harness` or wire the verdict into a
host pre-action hook. Pass `--entity` when entity-bound rules must apply. See
the [Codex and Claude Code setup plus integration
boundary](docs/07-mcp-server.md).

## Why the brain-inspired separation?

Human memory and control rely on partly distinct but interacting functions.
Brain-AI Memory borrows that **functional separation—not literal brain
anatomy** and turns it into inspectable software responsibilities. Brain-region
labels are mnemonics, not one-to-one localization or biological simulation.
If the analogy is not useful in your stack, keep the contracts and discard the
labels. See the [mapping and its limits](docs/01-the-mapping.md).

> **Evidence boundary.** Runtime tests verify selected package behaviors, while
> the deterministic ablation isolates authored contracts for ten tested
> lifecycle/control mechanisms. They do not prove that every package surface
> was ablated, that brain inspiration causes better LLM answers, or that this
> system beats RAG end to end. [Evidence and limitations](#evidence-status)

## Diagnose memory-management failures first

You build coding, research, operations, or assistant agents that work across
many sessions, and one or more of these sounds familiar:

- “We recorded that decision. Why can the next session not reconstruct it?”
- “The retrieved note is relevant, but it has already been superseded.”
- “This event belongs to another project or entity.”
- “The same lesson happened repeatedly but never became reusable knowledge.”
- “The exact value exists, yet the model estimated it from prose.”
- “The memory index keeps growing and nobody knows what to consolidate,
  archive, or retain.”

A single-turn chatbot with no durable state probably does not need this
architecture. Neither does a workflow whose only problem is ordinary document
search. Start with the failure you already see; you do not need to adopt the
whole architecture:

| What you observe | Diagnose first | Smallest useful change |
|---|---|---|
| settled context is lost or bound to the wrong event | episodic memory (HC) | add timestamped event/entity bindings |
| one project's memory leaks into another | entity scope and relation | bind the record to a stable entity and query within that scope |
| retrieval is relevant but stale | semantic memory (ATL) | verify freshness and reconsolidate on conflict |
| repeated episodes never become reusable knowledge or procedure | consolidation | create an explicit preview/approval promotion path |
| old and new facts remain simultaneously active | reconsolidation | supersede the stale record while retaining the old row and source link |
| a knowable value is guessed | exact state (IPS) | query a typed state store instead of estimating from prose |
| the always-loaded index keeps expanding | memory lifecycle | retain a bounded index and record archive/migration decisions |
| the next session cannot resume the prior decision | checkpoint and handoff | persist a scoped summary plus pending lifecycle candidates |

These are not features invented for a diagram. They were separated while
operating a persistent, multi-project agent system and debugging failures in
its memory, retrieval, lifecycle, and session handoffs. The evidence below
distinguishes that deployment record from causal and benchmark claims.

### Optional downstream failures

After memory is scoped and current, the memory-to-action bridge can address a
different class of failure:

| What you observe | Bridge component | Smallest useful change |
|---|---|---|
| a recalled rule is ignored during execution | procedural rule consumption (BG) | attach the stored rule to a deterministic action check |
| a fallback sequence stops after its first failure | procedural execution (CB) | move the sequence into an executable harness |
| the right memory bundle reaches an unsafe action | routing and proposed-action gate (PFC/TH) | consume the gate verdict at the host execution boundary |

## Why this is memory management—not just RAG or a harness

Finding relevant text is necessary, but it is only one operation inside a
memory system. The harder cross-session questions are: *what is this record,
what does it belong to, is it still current, can it become reusable knowledge
or a rule, and what must the next session receive?* Brain-AI Memory makes those
decisions explicit and inspectable.

| Existing method | What it supplies | What remains for memory management |
|---|---|---|
| long context or a memory file | text the model can read now | type, scope, active version, promotion, retention decision, and handoff |
| RAG or a vector store | candidate text similar to a query | entity binding, freshness, exact state, consolidation, supersession, and source/version links |
| entity model, ontology, or relational/graph DB | identity and structured relationships | which records behave as episode, knowledge, rule, or state and how they change across sessions |
| hook, guard, harness, or retry loop | interception, action policy, sequence execution, or another attempt | ownership and lifecycle of the memory those mechanisms consume and produce |
| Brain-AI Memory | typed local stores, entity scope, active-view recall, explicit promotion/update decisions, audit, and handoff | the host still supplies raw evidence, model-context assembly, scheduling, physical retention, and production policy |

Entity and relation support is therefore part of the core, but it is a local
identity-and-scope layer—not a domain ontology reasoner or a replacement for a
production database. RAG can remain the semantic retrieval backend. A hook can
call this kernel. A harness can consume its procedural memory. None of those
mechanisms alone owns the full memory lifecycle.

### The optional control bridge

A hook is an attachment point. A guard returns an allow/warn/block decision. A
harness owns a sequence. A loop feeds an outcome back into another attempt.
The public package includes small guard and fallback implementations so stored
rules and host-supplied procedure steps can influence action, but actual
enforcement and execution are **downstream of memory management** and require
the host to consume the result. They are not the reason the project is called
Brain-AI Memory.

### Contribution: differentiated memory contracts, not primitive invention

Working, episodic, semantic, and procedural memory categories are established
ideas; RAG, entity models, hooks, workflow harnesses, evaluators, and compaction
are established techniques. The contribution here is an installable contract
that connects them without collapsing their failure modes:

- PFC reconstructs a scoped working-memory candidate; HC records episodes and
  relations; ATL stores reusable sourced knowledge; BG stores procedural rules;
  and IPS preserves exact state;
- CB keeps executable procedure separate from a rule. The operating
  architecture can register such harnesses; the public alpha currently accepts
  host-supplied fallback steps rather than owning a sequence registry;
- consolidation previews an episode's promotion into knowledge or a rule, and
  reconsolidation creates a sourced superseding version instead of silently
  overwriting stale knowledge;
- a stored entry can receive one explicit lifecycle decision—keep, compact,
  archive, migrate to knowledge, migrate to rules, delete, or split—while the
  alpha records that decision and logical active view rather than pretending it
  physically transformed or erased the host's source;
- checkpoints carry counts, pending consolidation candidates, and a host-written
  summary into the next session; and
- the optional TH/BG/CB action path is tested separately from the core memory
  path, so software conformance is not mislabeled as memory-quality evidence.

The brain mapping is a functional engineering analogy. Keep it when it improves
diagnosis; discard the labels when it does not. The current evidence shows real
operation, tested retrieval tradeoffs, and distinct software contracts. It does
not yet show that brain inspiration or the integrated system beats simpler
memory systems end to end.

## Choose your adoption path

The clean-room public kernel is installable. Start with one memory failure and
add the optional action path only if you need it:

| Your goal | Start here | First success criterion |
|---|---|---|
| verify the package locally | `brain-ai tour` | inspect entity binding, current fact, exact state, update, and checkpoint under `.brain-ai/` |
| add typed memory to an agent | `entity`, `remember`, and `run` in the [`brain-ai` runtime](docs/05-runtime.md) | two similarly named projects return only their own active memory |
| add lifecycle to existing memory files | `consolidate`, `supersede`, `lifecycle`, and `checkpoint` | promotion is previewed, stale knowledge is versioned, and a handoff is recorded |
| connect Obsidian / Smart Connections | [semantic adapters](docs/06-adapters-and-observer.md) | v1 and v2 responses work; v2 hybrid ranking is preserved without duplicate BM25 |
| inspect local state and handoffs | [clean-room observer](docs/06-adapters-and-observer.md#read-only-reference-observer) | store counts, recent audit events, and the latest checkpoint render on localhost |
| deliver scoped memory to Codex, Claude Code, or another host | [MCP server](docs/07-mcp-server.md) | the host explicitly calls `brain_context`, injects selected records, writes outcomes, and checkpoints |
| enforce a stored procedure at action time | `brain-ai harness --entity ...` or a [behavioral guard](templates/hooks/behavioral-guard.py) | an entity-scoped unsafe pattern is blocked at the real execution boundary |
| execute a host-supplied fallback sequence | `brain-ai sequence --entity ...` | attempts continue until success, block, or exhaustion and the trace is audited |
| stop an index from becoming a second database | [memory skeleton](templates/memory/MEMORY.skeleton.md) | one linked line per topic remains always loaded |
| decide what to retain or move | [seven-operation helper](templates/memory/7-op-decision.md) | every reviewed entry receives exactly one recorded decision; host transforms remain explicit |
| evaluate the architecture rather than adopt it | [mapping](docs/01-the-mapping.md) and [evidence](evidence/README.md) | you can map a real failure to a component or identify where the map does not fit |

The hooks self-test with the Python standard library:

```bash
python3 templates/hooks/behavioral-guard.py --selftest
python3 templates/hooks/self-check-trigger.py --selftest
```

## How the memory architecture works

The canonical map is a seven-component **cognitive architecture**: five memory
roles (PFC working/executive, HC episodic, ATL semantic, BG procedural-rule, and
CB procedural-execution), plus two supporting control/computation roles (TH
gating and IPS exact numerical state). Consolidation and reconsolidation are
transfer channels, not extra components. The public product is a memory-
management kernel because typed memory and its lifecycle are primary; the
supporting control surfaces do not redefine it as a harness library. Read [the
detailed mapping](docs/01-the-mapping.md) for the neuroscience rationale and its
limits.

| Layer | Component | Public-package responsibility | Failure it helps diagnose |
|---|---|---|---|
| memory role | PFC | routes a query to candidate stores and reconstructs a scoped working-memory candidate | the wrong store or entity scope was selected |
| memory role | HC | episodic events, stable entities, aliases, relations, and bindings | an event is missing or bound to the wrong context |
| memory role | ATL | active semantic knowledge with sources and superseding versions | retrieval is relevant but stale or incorrectly sourced |
| memory role | BG | stored procedural rules and approved episode-to-rule promotion | a reusable rule was never captured or selected |
| memory role | CB | executable procedure representation; the alpha runs explicit host-supplied steps | a procedure remains prose or stops before fallbacks finish |
| supporting computation | IPS | entity-scoped exact numerical state | a knowable quantity is guessed from prose |
| supporting control | TH | checks a host-proposed action before execution in the public runtime | an unsafe proposed action reaches the tool boundary |
| lifecycle channel | consolidation | previews and explicitly applies episode → knowledge/rule promotion | repeated experience never becomes reusable memory |
| lifecycle channel | reconsolidation | creates a sourced superseding semantic version | stale and current knowledge remain simultaneously active |

The mapping's TH inspiration is broader input gating. The clean-room runtime
implements the narrower, observable form it actually tests: a proposed-action
check. It does not claim to filter a model's entire prompt or provider input.

### Host-owned closed loop

The public package provides the kernel operations; it does not run this loop in
the background. A complete host integration performs these steps explicitly:

1. **Select:** retain any native transcript as host-owned evidence and choose
   only the records that merit durable operational memory.
2. **Bind and write:** call `brain_remember`/`brain-ai remember` with the memory
   type, entity, source label, and exact value where applicable.
3. **Recall and assemble:** call `brain_context`/`brain-ai run`; the host then
   fits the returned candidate bundle into its own token budget and model
   context.
4. **Act:** execute with the host's own policy, optionally consuming the
   entity-scoped gate or `harness`/`sequence` bridge.
5. **Record outcome:** write the selected result as an episode or exact state.
6. **Review lifecycle:** preview/apply promotion, supersede stale knowledge, and
   record any archive, split, compact, migration, or logical-delete decision.
7. **Handoff:** write a checkpoint and have the next session consume it.

Today the package implements the called primitives and audit trail, not an
automatic transcript adapter, scheduler, token-budget assembler, physical
archive/delete engine, or checkpoint acknowledgement protocol. A connected MCP
server alone therefore does not close the loop. Finding a raw trace, selecting
an episode, assembling candidate memory, and consolidating it are distinct
operations. See the [memory lifecycle](docs/02-memory-lifecycle.md) for the
representation and handoff contract.

![Memory lifecycle: recall, in-session tagging, consolidation, and seven lifecycle operations](docs/assets/memory-lifecycle.svg)

## Evidence status

Brain-AI Memory separates four evidence classes: operational exposure, primary
memory-management evaluation, supporting software conformance, and evidence
that is still missing. They answer different questions and should not be
collapsed into one headline.

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
| Do the ten ablated memory/lifecycle and optional-control mechanisms execute their authored contracts? | **Supporting conformance only: all-ten condition 20/20; flat retrieval control 1/20. The flat control still found the expected top text for 6/6 memory queries** |

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

### Secondary: memory-to-action contract verification

Separately from the memory-performance scoreboard, the installable package was
evaluated on 20 deterministic contract cases under 21 conditions: a flat
retrieval control, ten cumulative additions, and ten leave-one-out removals. No
LLM, external API, private data, or external judge was used.

![Cumulative mechanism-contract ablation: the flat control satisfies 1 of 20 authored contracts and the condition with all ten tested mechanisms enabled satisfies all 20](docs/assets/component-ablation.png)

The all-ten condition satisfied 20/20 authored contracts and the flat control
satisfied 1/20. Importantly, the flat control still retrieved the expected top
text in all 6/6 memory queries. Its lower total reflects missing typed routing,
exact-state, gate, fallback-sequence, and lifecycle contracts—not failed text
retrieval. Each cumulative addition recovered its designated cases, and each
leave-one-out removal failed the corresponding cases.

This verifies that the ten tested software responsibilities are distinguishable
and executable. It does **not** measure answer quality, autonomous lifecycle
management, or superiority over RAG. See the [report, 420 raw records, summary,
and manifest](benchmarks/pilots/component-ablation-20260715/README.md).

## Next external validation

The primary missing evidence is a controlled, end-to-end memory-management QA
comparison: can an agent retain, retrieve, update, scope, abstain, and resume
more reliably under the same reader and budget? The next release-grade run will
hold the reader model, prompt, context budget, dataset split, and scoring
procedure constant across:

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

## Capability roadmap

The public alpha is a working kernel, not yet an autonomous closed-loop memory
service. The implementation path is:

1. add a provider-neutral ingestion envelope with session/message identity,
   event time, outcome, evidence URI/hash, and deduplication;
2. ship one opt-in transcript adapter without making private provider logs part
   of the core;
3. assemble candidate memory under a real token/byte budget and expose why each
   record was selected;
4. add checkpoint consume/acknowledge/resume plus lifecycle backlog and health
   metrics; and
5. provide explicit compact, split, archive, and verified-delete adapters, then
   test the complete host loop end to end.

Production multi-writer locking, authentication, domain-ontology reasoning,
and entity merge/versioning remain later hardening work. Until these are
implemented and tested, the accurate product boundary is an **installable
memory-management reference kernel**, not a fully autonomous memory platform.

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
| [docs/02-memory-lifecycle.md](docs/02-memory-lifecycle.md) | four representations, seven operations, host handoffs, and health metrics |
| [docs/03-governance-tiers.md](docs/03-governance-tiers.md) | advisory, guarded, and enforced tiers |
| [docs/04-principles.md](docs/04-principles.md) | short judgment-bound operating principles |
| [docs/05-runtime.md](docs/05-runtime.md) | installable memory kernel, stores, routing, lifecycle, and optional action bridge |
| [docs/06-adapters-and-observer.md](docs/06-adapters-and-observer.md) | Smart Connections compatibility and clean-room Command Center |
| [docs/07-mcp-server.md](docs/07-mcp-server.md) | provider-neutral MCP tools, resources, setup, and security boundary |
| [src/brain_ai_memory/](src/brain_ai_memory/) | public Python runtime implementation |
| [tests/](tests/) | kernel integration, adapter, and supporting contract tests |
| [CHANGELOG.md](CHANGELOG.md) | release-level changes and evidence boundaries |
| [schema/brain_components.yaml](schema/brain_components.yaml) | machine-readable component ontology |
| [templates/](templates/) | copy-paste memory, rule, and hook skeletons |
| [examples/](examples/) | tiny runnable cases using synthetic data |
| [evidence/](evidence/) | operational snapshot, internal A/B summary, and capacity simulation |
| [benchmarks/](benchmarks/) | memory-evaluation protocol and pilots, plus supporting contract verification |

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
