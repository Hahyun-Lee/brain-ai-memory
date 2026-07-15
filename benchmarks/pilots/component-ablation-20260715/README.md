# Component-contract ablation (2026-07-15)

This deterministic benchmark removes and cumulatively adds public runtime
components. It asks whether the package executes its stated contracts; it
does **not** test LLM answer quality, general reasoning, or real-world agent
efficacy. The cases are authored around these contracts, so this is not an
external benchmark or evidence that a brain-inspired architecture beats RAG.

## Result

| condition | passed | rate | delta vs full |
|---|---:|---:|---:|
| flat retrieval-only control | 1 / 20 | 5.0% | -19 |
| full public runtime | 20 / 20 | 100.0% | +0 |

The flat control retrieved the expected top item for 6 / 6 memory queries (see
`observed.top_id_matches` in `records.jsonl`) but does not satisfy typed
component, exact-state, gating, fallback, or lifecycle contracts.

## What each addition recovered

| addition | cumulative score | newly recovered contract cases |
|---|---:|---|
| PFC · goal-aware component routing | 3 / 20 | `pfc_route_numeric`, `pfc_route_procedure` |
| ATL · semantic knowledge | 5 / 20 | `atl_privacy_policy`, `atl_release_policy` |
| HC · timestamped episodes | 7 / 20 | `hc_cache_incident`, `hc_schedule_change` |
| IPS · typed exact numerical state | 9 / 20 | `ips_open_reviews`, `ips_retry_failures` |
| TH · deterministic input/action gate | 11 / 20 | `th_pipe_shell`, `th_root_delete` |
| BG · stored procedural rules | 13 / 20 | `bg_custom_block`, `bg_custom_warn` |
| CB · executable fallback sequence | 15 / 20 | `cb_fallback_exhausts`, `cb_fallback_recovers` |
| HC→ATL/BG · approved consolidation | 18 / 20 | `consolidation_preview`, `consolidation_to_rule`, `consolidation_to_semantic` |
| ATL update · provenance-preserving supersession | 19 / 20 | `reconsolidation_supersedes` |
| Lifecycle · durable checkpoint | 20 / 20 | `checkpoint_persists` |

## Leave-one-out removal from the full runtime

| removed mechanism | score | drop | contracts that fail |
|---|---:|---:|---|
| PFC · goal-aware component routing | 12 / 20 | -8 | `atl_privacy_policy`, `atl_release_policy`, `hc_cache_incident`, `hc_schedule_change`, `ips_open_reviews`, `ips_retry_failures`, `pfc_route_numeric`, `pfc_route_procedure` |
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
- PFC removal has a larger drop because routed memory access depends on it;
  this is an explicit dependency, not a measured biological interaction.
- Latency includes fresh local-store setup and subprocess startup for the
  executable-sequence cases. It is diagnostic, not a production estimate.
- No LLM, network service, hidden operational data, or external judge is used.
- End-to-end quality claims still require preregistered LongMemEval or
  MemoryAgentBench runs with matched model and context budgets.

## Reproduce

```bash
python3 benchmarks/run_component_ablation.py \
  --output benchmarks/pilots/component-ablation-20260715
python3 benchmarks/plot_component_ablation.py
python3 -m unittest discover -s tests -v
```

Artifacts: `records.jsonl` contains every condition × case observation;
`summary.json` contains aggregates and recovered/failing case IDs;
`manifest.json` records hashes and the exact condition matrix.
