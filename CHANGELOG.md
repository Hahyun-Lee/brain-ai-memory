# Changelog

## Unreleased

### Fixed

- normalize missing or unusable source-freshness roots to the documented
  `ValueError` contract; and
- preserve successful post-tool artifact captures when source refresh fails,
  keep the cached freshness controls active, and report the bounded diagnostic
  without marking the loop event unhealthy; and
- route explicit exact-state requests to `IPS` and make the packaged restart
  test verify the exact state key and value instead of matching echoed text.

### Verification

- expand the public suite to 137 tests with regressions for both failure paths.

## 0.7.0 — 2026-07-22

### Memory lifecycle

- compare approved project-local Markdown sources with their applied fragments
  at session start and after supported edits;
- withhold source-derived records whose exact evidence changed, disappeared,
  became unreadable, or moved outside the project from automatic recall, and
  place automatic action gating in a fail-closed review hold when an imported
  procedural source becomes stale;
- preserve unchanged fragments, produce an ordinary review audit for changed
  content, and require the existing reviewed apply path before reconsolidating
  replacement facts, state, or rules; and
- cache the completed freshness snapshot in SQLite, surface source attention in
  injected context and `doctor`, and keep prompt and pre-action boundaries free
  of source-file I/O.

### Adoption

- add a preview-first `brain-ai setup` command that creates or reuses one
  project entity, configures Codex or Claude Code, and runs the existing
  diagnostics without importing or approving memory;
- make the project directory the default local runtime home while preserving
  explicit `--home` and `BRAIN_AI_HOME` precedence; and
- add a structured field-report form for real multi-session failures and
  adoption blockers.

### Distribution

- add a release-triggered PyPI Trusted Publishing workflow that verifies the
  tag and package version, runs the public suite, smoke-tests both wheel and
  source distribution, and publishes the exact verified artifacts through
  GitHub OIDC;
- use a concise package-index landing page with absolute documentation,
  language, image, security, and issue links instead of exposing broken
  repository-relative links on PyPI; and
- keep release credentials out of the repository and expand local ignore
  rules for common environment, key, and credential files.

### Verification

- expand the public suite to 135 tests, including changed, comment-only, and
  missing-source freshness cases, a stale-rule review hold, and end-to-end
  `doctor` attention; and
- continue to treat these as deterministic lifecycle and integration checks,
  not evidence that the system can infer truth or improve end-to-end LLM answer
  quality.

## 0.6.0 — 2026-07-16

### Added

- an opt-in, project-scoped automatic session loop for Codex and Claude Code,
  installed with preview-first `connect ... --mode loop` wiring;
- byte-bounded start and prompt recall, scoped handoff delivery and
  acknowledgement, successful-edit metadata capture, and dirty-only idempotent
  checkpoints at compaction, turn, or session boundaries;
- project-private lifecycle bindings, `configured` versus observed `active`
  diagnostics, and exact managed-hook ownership for safe upgrades and removal;
- strict project locking for generated memory connections, including rejection
  of cross-entity reads, writes, graph mutation, and global consolidation
  surfaces; and
- additive loop-ledger migrations plus cross-process exact-once JSONL receipts
  with POSIX and Windows lock implementations.

### Safety and privacy

- raw prompts are used transiently for retrieval but are not persisted; raw
  tool output, assistant messages, edited file contents, and inferred facts,
  rules, state, or supersessions are not captured by the loop;
- host session and turn identifiers are persisted only as one-way hashes;
- injected records carry source identifiers, a data-not-instructions envelope,
  per-record truncation, and a hard UTF-8 byte ceiling;
- automatic semantic promotion remains disabled: truth-bearing changes still
  require explicit memory operations or the review workflow;
- the Bash pre-action decision uses a persistence-independent fast path, so a
  matched block is returned before checkpoint recovery or audit telemetry;
- stored procedural patterns use a bounded, fail-closed subset that rejects
  backtracking hazards both at direct creation and reviewed import;
- explicit detailed checkpoints take precedence over automatic checkpoints,
  concurrent duplicate edit and terminal-hook delivery is exact-once,
  interrupted checkpoint mirroring is recoverable, and old retries cannot clear
  newer work; and
- loop installation is project-only, preserves unrelated host configuration,
  rolls back the exact prior connection if lifecycle setup fails, and refuses
  modified or unowned hook removal.

### Verification

- the public suite now contains 123 tests, including 29 loop cases, 17 host
  integration cases, 4 storage durability and concurrency cases, a real stdio
  restart/resume workflow, and clean-wheel subprocess hook coverage;
- Codex and Claude Code project configuration, permission repair, preview
  purity, disconnect ownership, entity isolation, manual-checkpoint precedence,
  bounded Unicode context, failure injection, and concurrent retries are
  covered; and
- these checks establish packaging and deterministic integration behavior, not
  improved end-to-end LLM answer quality or live-host long-run reliability.

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
