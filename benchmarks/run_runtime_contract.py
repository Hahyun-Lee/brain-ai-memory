#!/usr/bin/env python3
"""A/B the installable runtime against a flat retrieval-only control.

This is a deterministic component-contract benchmark. It verifies that the
public package actually routes, recalls exact state, gates actions, and exposes
component traces. It is not an external QA benchmark and cannot support a claim
that Brain-AI improves an LLM's answer quality.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from brain_ai_memory.runtime import BrainAIRuntime
from brain_ai_memory.text import ranked


ROOT = Path(__file__).resolve().parents[1]
CASES = Path(__file__).with_name("runtime_contract_cases.jsonl")


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def seed(runtime: BrainAIRuntime) -> tuple[dict[str, str], list[dict]]:
    ids = {}
    ids["release_policy"] = runtime.store.put_knowledge(
        "Atlas releases require completed code review before deployment.", source="benchmark"
    )["id"]
    ids["privacy_policy"] = runtime.store.put_knowledge(
        "Private records must remain in the encrypted local store.", source="benchmark"
    )["id"]
    ids["schedule_change"] = runtime.store.append_event(
        "On Tuesday, the Atlas release window moved from Friday to Thursday.", source="benchmark"
    )["id"]
    ids["cache_incident"] = runtime.store.append_event(
        "After the cache incident, the team invalidated stale pointers and rebuilt the index.", source="benchmark"
    )["id"]
    runtime.store.set_state("atlas_open_reviews", 3, source="benchmark")
    runtime.store.set_state("retry_failures", 7, source="benchmark")
    runtime.store.add_rule(r"deploy\s+production", reason="production deployment requires approval", source="benchmark")

    flat = []
    for item in runtime.store.knowledge():
        flat.append({"id": item["id"], "text": item["text"]})
    for item in runtime.store.events():
        flat.append({"id": item["id"], "text": item["text"]})
    for item in runtime.store.states():
        flat.append({"id": item["key"], "text": f"{item['key']} {item['value']}"})
    return ids, flat


def evaluate_runtime(runtime: BrainAIRuntime, case: dict, ids: dict[str, str]) -> tuple[bool, dict]:
    result = runtime.process(case["query"], proposed_action=case.get("action"))
    task = case["task"]
    if task in {"recall", "state"}:
        component = case["expected_component"]
        hits = result["memory"].get(component, [])
        expected_id = ids.get(case["expected_id"], case["expected_id"])
        passed = bool(hits and hits[0].get("id") == expected_id)
        if task == "state":
            passed = passed and hits[0].get("value") == case["expected_value"]
    elif task == "gate":
        passed = result["gate"]["allowed"] is case["expected_allowed"]
    else:
        passed = case["expected_component"] in result["route"]
    return passed, result


def evaluate_flat(case: dict, flat: list[dict], ids: dict[str, str]) -> tuple[bool, dict]:
    started = time.perf_counter()
    hits = ranked(flat, case["query"], limit=1)
    task = case["task"]
    if task in {"recall", "state"}:
        expected_id = ids.get(case["expected_id"], case["expected_id"])
        passed = bool(hits and hits[0]["id"] == expected_id)
        if task == "state":
            passed = passed and str(case["expected_value"]) in hits[0]["text"]
    elif task == "gate":
        passed = case["expected_allowed"] is True  # retrieval-only control never blocks
    else:
        passed = case["expected_component"] == "ATL"  # one undifferentiated store
    return passed, {"hits": hits, "latency_ms": (time.perf_counter() - started) * 1000}


def summarize(records: list[dict], condition: str) -> dict:
    selected = [record for record in records if record["condition"] == condition]
    latencies = [record["latency_ms"] for record in selected]
    by_task = {}
    for task in sorted({record["task"] for record in selected}):
        group = [record for record in selected if record["task"] == task]
        by_task[task] = {"passed": sum(item["passed"] for item in group), "total": len(group)}
    return {
        "condition": condition,
        "passed": sum(record["passed"] for record in selected),
        "total": len(selected),
        "accuracy": sum(record["passed"] for record in selected) / len(selected),
        "mean_latency_ms": statistics.fmean(latencies),
        "p95_latency_ms": sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)],
        "by_task": by_task,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = load_cases(args.cases)
    records = []
    with tempfile.TemporaryDirectory() as tmp:
        runtime = BrainAIRuntime(Path(tmp) / ".brain-ai")
        ids, flat = seed(runtime)
        for case in cases:
            started = time.perf_counter()
            passed, _ = evaluate_runtime(runtime, case, ids)
            records.append({"case_id": case["id"], "task": case["task"], "condition": "brain-ai-runtime", "passed": passed, "latency_ms": (time.perf_counter() - started) * 1000})
            passed, detail = evaluate_flat(case, flat, ids)
            records.append({"case_id": case["id"], "task": case["task"], "condition": "flat-retrieval-control", "passed": passed, "latency_ms": detail["latency_ms"]})
    output = {
        "benchmark": "brain-ai component-contract A/B",
        "claim_scope": "public runtime contract conformance only; not LLM QA efficacy",
        "case_count": len(cases),
        "summary": [summarize(records, name) for name in ("flat-retrieval-control", "brain-ai-runtime")],
        "records": records,
    }
    payload = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
