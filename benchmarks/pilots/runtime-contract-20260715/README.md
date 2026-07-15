# Public runtime component-contract A/B (2026-07-15)

## Result

| Condition | Passed | Accuracy |
|---|---:|---:|
| flat retrieval-only control | 8 / 14 | 57.1% |
| Brain-AI public runtime | 14 / 14 | 100.0% |

| Task | Flat control | Brain-AI runtime |
|---|---:|---:|
| semantic + episodic recall | 4 / 4 | 4 / 4 |
| exact numerical state | 2 / 2 | 2 / 2 |
| action gate | 1 / 4 | 4 / 4 |
| component routing | 1 / 4 | 4 / 4 |

## What it means

The installable public package executes the contracts it claims to implement:
it separates semantic and episodic retrieval, returns exact state, consumes
deterministic gates, and records component routing. The flat control can retrieve
text and exact state but cannot enforce a rule or distinguish routes it does not
have.

## What it does not mean

This is a 14-case deterministic conformance suite authored around the public
component contracts. It is not an external QA benchmark, the cases are not a
representative sample of real agent work, and 100% is not a claim of general
agent quality. The flat control is substantially faster because it does less.
External LongMemEval/MemoryAgentBench evaluation is still required before any
claim that the lifecycle improves answer quality, latency, or cost.

## Reproduce

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
python benchmarks/run_runtime_contract.py
```

The case records are in
[`runtime_contract_cases.jsonl`](../../runtime_contract_cases.jsonl). The runner
prints aggregate and per-case results, including measured query latency for the
current machine.
