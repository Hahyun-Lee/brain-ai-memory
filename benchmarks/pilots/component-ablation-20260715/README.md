# Ten-mechanism lifecycle/control contract ablation (2026-07-15)

This deterministic benchmark removes and cumulatively adds ten authored
lifecycle/control mechanisms. It asks whether those mechanisms execute their
stated contracts. It does **not** cover the whole public package or test LLM
answer quality, general reasoning, or real-world agent efficacy. The cases are
authored around these contracts, so this is not an external benchmark or
evidence that a brain-inspired architecture beats RAG.

## Result

| condition | passed | rate | delta vs all-ten |
|---|---:|---:|---:|
| flat retrieval-only control | 1 / 20 | 5.0% | -19 |
| all ten mechanisms enabled | 20 / 20 | 100.0% | +0 |

The flat control retrieved the expected top item for 6 / 6 memory queries (see
`observed.top_id_matches` in `records.jsonl`) but does not satisfy typed
routing, exact-state, gating, fallback, or lifecycle contracts.

## What each addition recovered

| addition | cumulative score | newly recovered contract cases |
|---|---:|---|
| PFC · query/action-cue routing | 3 / 20 | `pfc_route_numeric`, `pfc_route_procedure` |
| ATL · semantic knowledge | 5 / 20 | `atl_privacy_policy`, `atl_release_policy` |
| HC · timestamped episodes | 7 / 20 | `hc_cache_incident`, `hc_schedule_change` |
| IPS · typed exact numerical state | 9 / 20 | `ips_open_reviews`, `ips_retry_failures` |
| TH · deterministic input/action gate | 11 / 20 | `th_pipe_shell`, `th_root_delete` |
| BG · stored procedural rules | 13 / 20 | `bg_custom_block`, `bg_custom_warn` |
| CB · executable fallback sequence | 15 / 20 | `cb_fallback_exhausts`, `cb_fallback_recovers` |
| HC→ATL/BG · approved consolidation | 18 / 20 | `consolidation_preview`, `consolidation_to_rule`, `consolidation_to_semantic` |
| ATL update · provenance-preserving supersession | 19 / 20 | `reconsolidation_supersedes` |
| Lifecycle · durable checkpoint | 20 / 20 | `checkpoint_persists` |

## Leave-one-out removal from the all-ten condition

| removed mechanism | score | drop | contracts that fail |
|---|---:|---:|---|
| PFC · query/action-cue routing | 12 / 20 | -8 | `atl_privacy_policy`, `atl_release_policy`, `hc_cache_incident`, `hc_schedule_change`, `ips_open_reviews`, `ips_retry_failures`, `pfc_route_numeric`, `pfc_route_procedure` |
| ATL · semantic knowledge | 18 / 20 | -2 | `atl_privacy_policy`, `atl_release_policy` |
| HC · timestamped episodes | 18 / 20 | -2 | `hc_cache_incident`, `hc_schedule_change` |
| IPS · typed exact numerical state | 18 / 20 | -2 | `ips_open_reviews`, `ips_retry_failures` |
| TH · deterministic input/action gate | 18 / 20 | -2 | `th_pipe_shell`, `th_root_delete` |
| BG · stored procedural rules | 18 / 20 | -2 | `bg_custom_block`, `bg_custom_warn` |
| CB · executable fallback sequence | 18 / 20 | -2 | `cb_fallback_exhausts`, `cb_fallback_recovers` |
| HC→ATL/BG · approved consolidation | 17 / 20 | -3 | `consolidation_preview`, `consolidation_to_rule`, `consolidation_to_semantic` |
| ATL update · provenance-preserving supersession | 19 / 20 | -1 | `reconsolidation_supersedes` |
| Lifecycle · durable checkpoint | 19 / 20 | -1 | `checkpoint_persists` |

## Interpretation boundary

- Scores mean only that deterministic software contracts were met.
- Entity/relation management, ontology loading, MCP/CLI surfaces, semantic
  adapters, and provider-host integration are outside these 20 cases.
- PFC removal has a larger drop because routed memory access depends on it;
  this is an explicit dependency, not a measured biological interaction.
- Latency includes fresh local-store setup and subprocess startup for the
  executable-sequence cases. It is diagnostic, not a production estimate.
- No LLM, network service, hidden operational data, or external judge is used.
- End-to-end quality claims still require preregistered LongMemEval or
  MemoryAgentBench runs with matched model and context budgets.

## Recorded run and current-release parity

The committed records were produced from the clean source commit recorded in
`manifest.json` (`d0d675ead16b96b6f4ac0a5aaab7ddcf20786ba7`). The artifact
hashes certify the committed files. A rerun is **not** expected to reproduce
those bytes: measured latency and generated metadata vary by environment and
time.

To rerun the recorded source without changing your current checkout:

```bash
git worktree add /tmp/brain-ai-ablation-recorded \
  d0d675ead16b96b6f4ac0a5aaab7ddcf20786ba7
(cd /tmp/brain-ai-ablation-recorded && \
  python3 benchmarks/run_component_ablation.py \
    --output /tmp/component-ablation-recorded)
python3 benchmarks/run_component_ablation.py \
  --verify-records /tmp/component-ablation-recorded/records.jsonl \
  --reference-manifest benchmarks/pilots/component-ablation-20260715/manifest.json \
  --verify-source-provenance
```

To run the current release and require the same normalized semantic outcomes:

```bash
python3 benchmarks/run_component_ablation.py \
  --output /tmp/component-ablation-current \
  --reference-manifest benchmarks/pilots/component-ablation-20260715/manifest.json \
  --verify-source-provenance
python3 -m pip install ".[plot]"
python3 benchmarks/plot_component_ablation.py \
  --summary /tmp/component-ablation-current/summary.json \
  --output /tmp/component-ablation-current.png
python3 -m unittest discover -s tests -v
```

Semantic parity excludes only environment-dependent `latency_ms` and the
later-added `entities`/`relations` keys inside consolidation count snapshots.
All scored observations and checks remain in the digest. A shallow clone must
fetch the recorded commit before `--verify-source-provenance` can validate it.
The plotting extra pins Matplotlib 3.10.8; exact PNG bytes can still differ
across platform font/rendering backends, so the PNG is not a manifest-pinned
benchmark artifact.

Artifacts: `records.jsonl` contains every condition × case observation;
`summary.json` contains aggregates and recovered/failing case IDs;
`manifest.json` records artifact hashes, relevant source hashes, the exact
condition matrix, and the normalized semantic-outcome digest.
