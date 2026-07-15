# Changelog

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
