# Changelog

## Unreleased

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

The ablation verifies distinct public software contracts. It does not show
that biological inspiration causes the result, that the runtime improves LLM
answer quality, or that the architecture beats RAG on an external workload.

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
