# Changelog

## 0.5.0 — 2026-07-16

### Added

- a source-addressed Markdown adoption workflow: `audit`, `review`, `apply`,
  and recoverable `rollback`;
- deterministic exact-duplicate and explicit key/value conflict candidates,
  without inferring which statement is true or current;
- an idempotent import ledger that retains file, line-range, fragment, and
  source hashes for every approved semantic, episodic, exact-state, rule, or
  supersession decision;
- project-scoped `handoff` and `resume` commands plus the `brain_resume` MCP
  tool;
- preview-first `connect` and `disconnect` commands for project or user Codex
  and Claude Code MCP configuration;
- an MCP default entity so host calls do not silently fall back to global
  scope; and
- explicit many-to-one supersession edges so a reused replacement retains
  every old-record, entity, source, and import-batch lineage.

### Safety

- audit previews do not initialize the memory database, and saved audit/review
  plans never rewrite their source Markdown;
- apply requires an explicit reviewed allowlist and `--yes`, validates plan
  integrity, and fails closed when either the source hash or logical store
  revision has changed;
- arbitrary Markdown prose cannot become an enabled rule or overwrite exact
  state without a specific human decision;
- import identity is entity-scoped, and rollback preserves unrelated entity
  link roles and refuses to invalidate a later applied batch that still
  depends on the same imported target;
- rolled-back deterministic reviews can create a new immutable batch attempt
  without overwriting the earlier receipt, and legacy single-attempt batch
  tables migrate transactionally;
- default Markdown discovery pins the validated in-project path and opens it
  without following a swapped parent or leaf symbolic link, while explicit
  paths open the canonical parent component-by-component;
- entity scope is applied before semantic ranking and top-k; external vault
  results without a verified entity binding remain explicitly unscoped;
- newly created runtime directories and sensitive files use owner-only modes,
  and `doctor` reports permissive existing stores;
- supersession rollback retains its lineage edge as a logical tombstone and
  restores the replacement's prior compatibility pointer;
- v0.4 scalar supersession pointers migrate to explicit lineage edges without
  duplicating them on restart, while ambiguous legacy branches remain visible
  as migration conflicts;
- runtime-home symlinks and non-regular artifacts are rejected, vault adapters
  do not traverse links outside the configured root, and `doctor` verifies the
  generated catch-all ignore rule as well as owner-only permissions;
- managed Codex and Claude Code configuration is previewed with unrelated
  values omitted, and supported POSIX platforms pin its parent directory
  across read, compare, atomic replace, and verification; and
- rollback is logical and evidence-preserving, not physical erasure.

### Packaging

- source distributions include the benchmark inputs required by their bundled
  tests;
- CI verifies the core runtime and adoption workflow on Python 3.10, 3.11, and 3.12, then
  builds, checks, installs, and smoke-tests the wheel and source distribution;
- the installed-wheel check now runs the public audit, review, apply, generated
  MCP configuration, real stdio calls, checkpoint, fresh-process resume, and
  entity-isolation path as one reproducible integration test; and
- `brain-ai-mcp` exits with a concise installation hint when the optional MCP
  dependency is absent.

## 0.4.0 — 2026-07-15

### Added

- required machine-readable `memory` versus `control` categories in ontology
  v3, with startup validation of category values and observable category
  counts; the bundled ontology declares the canonical five-plus-two split;
- normalized semantic-outcome parity and recorded-source provenance checks for
  the ten-mechanism lifecycle/control ablation;
- a Korean memory-lifecycle guide with the same four-representation and host
  handoff contract as the English guide; and
- a pinned `plot` extra plus CI chart-generation smoke coverage.

### Changed

- reposition the public package around its implemented core: a typed,
  entity-scoped memory-management reference kernel, with guarding and fallback
  execution documented as an optional downstream bridge;
- propagate an optional entity scope through `harness` and `sequence`, so
  supplied entity-bound rules are evaluated at their execution boundary;
- separate primary memory evidence from supporting lifecycle/action contract
  conformance and identify controlled end-to-end lifecycle QA as the main
  missing benchmark;
- the graphical abstract and social preview now separate host-selected memory
  mapping from proposed-action gating;
- ablation wording now refers to the ten mechanisms actually tested; and
- clarify the copy contract for the memory skeleton and its accompanying topic
  stubs.

### Documentation

- distinguish provider-native raw traces, reconstructed working memory,
  structured episodes, and approved consolidated memory;
- define top-down control and bottom-up learning as an explicit host
  integration contract rather than background runtime automation;
- document that Claude Code/Codex transcript adapters are not included, plus
  the host boundary for authorization, ingestion, preserved evidence, access,
  backup, encryption, retention, and deletion;
- define lifecycle `delete` as a recoverable logical tombstone in the reference
  alpha, with physical erasure delegated to an explicit host retention flow; and
- publish the capability path from the current reference kernel to a tested,
  host-integrated closed loop without implying background automation.

### Compatibility

- custom ontology v2 files must add a valid `category: memory` or
  `category: control` field to every component before upgrading.

## 0.3.1 — 2026-07-15

### Fixed

- reuse one Smart Connections stdio process across adapter queries so local
  embedding and reranker models stay warm instead of paying cold-start latency
  on every recall; and
- close and discard a failed child connection before activating the observable
  local fallback.

## 0.3.0 — 2026-07-15

### Added

- provider-neutral MCP server with scoped context, action checks, typed memory
  writes, entity/relation tools, lifecycle handoffs, and status/ontology
  resources;
- stable entity identities, aliases, typed relations, memory bindings, and
  entity-scoped exact state;
- startup validation of the canonical component/channel ontology;
- a concise `brain-ai tour` that demonstrates current fact recall, exact state,
  action blocking, fallback completion, supersession, and checkpointing; and
- English and Korean MCP setup and security-boundary guides.
- 20-case, 21-condition deterministic component-contract ablation with 420 raw
  records, cumulative additions, leave-one-out removals, artifact hashes, and a
  reproducible chart.
- Smart Connections adapter compatibility with both the v1 result list and v2
  response envelope, including retrieval provenance and bounded snippets.

### Changed

- README opening now explains the practical failure, controlled outcome,
  one-minute tour, and connection path before implementation jargon.
- neuroscience language now distinguishes functional inspiration from software
  adaptation and removes one-to-one anatomical or clinical implications.
- package version advanced to `0.3.0`; MCP remains an optional dependency and
  arbitrary command execution is intentionally absent from the MCP surface.
- v2 hybrid Smart Connections profiles retain the server's ranking and disk
  coverage instead of adding a second local BM25 contribution; v1, `plugin`,
  and failure paths keep reciprocal-rank fallback.

### Evidence boundary

The ablation verifies authored contracts for the ten tested lifecycle/control
mechanisms. It does not cover every public package surface or show that
biological inspiration causes the result, that the runtime improves LLM answer
quality, or that the architecture beats RAG on an external workload.

## 0.2.0 — 2026-07-15

Brain-AI Memory changes from an architecture-only extraction into an
installable public alpha.

### Added

- dependency-free Python package and `brain-ai` CLI;
- differentiated HC, ATL, BG, IPS, TH, CB, and PFC runtime paths;
- explicit command harness and fallback sequence execution;
- checkpoint, consolidation preview/apply, reconsolidation, and all seven
  lifecycle operations;
- local multilingual BM25, direct Markdown vault, and Smart Connections MCP
  semantic adapters;
- reciprocal-rank fusion and visible fallback diagnostics for Smart Connections;
- localhost-only clean-room Command Center with read-only JSON endpoints;
- eight end-to-end and adapter tests;
- 14-case flat-control versus runtime component-contract A/B; and
- complete English and Korean installation, runtime, adapter, and observer docs.

### Evidence boundary

The contract A/B verifies that the public package executes its stated routing,
recall, exact-state, and gating contracts. It is not evidence that the system
improves LLM answer quality. The existing LongMemEval-S pilot remains
retrieval-only, and release-grade end-to-end QA evaluation is still pending.

## 0.1.0 — 2026-07-14

- Initial clean-room architecture, component ontology, templates, examples,
  operational evidence snapshot, and public retrieval pilot.
