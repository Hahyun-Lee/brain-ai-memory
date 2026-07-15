# Changelog

## Unreleased

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
