#!/usr/bin/env python3
"""Run deterministic cumulative and leave-one-out mechanism ablations.

This suite measures authored contracts for ten lifecycle/control mechanisms.
It does not cover every public package feature. Its cases use no LLM or
external API and cannot support a claim of better general QA, reasoning, or
agent quality. The flat control may retrieve the right text while failing a
typed route, gate, sequence, or lifecycle contract; raw records preserve those
partial observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from brain_ai_memory.runtime import BrainAIRuntime  # noqa: E402
from brain_ai_memory.text import ranked  # noqa: E402


CASES = Path(__file__).with_name("component_ablation_cases.jsonl")
DEFAULT_OUTPUT = Path(__file__).parent / "pilots" / "component-ablation-20260715"

FEATURES = (
    "pfc_routing",
    "atl_semantic",
    "hc_episodic",
    "ips_state",
    "th_gate",
    "bg_rules",
    "cb_sequence",
    "consolidation",
    "reconsolidation",
    "checkpoint",
)

FEATURE_LABELS = {
    "pfc_routing": "PFC · query/action-cue routing",
    "atl_semantic": "ATL · semantic knowledge",
    "hc_episodic": "HC · timestamped episodes",
    "ips_state": "IPS · typed exact numerical state",
    "th_gate": "TH · deterministic proposed-action gate",
    "bg_rules": "BG · stored procedural rules",
    "cb_sequence": "CB · executable fallback sequence",
    "consolidation": "HC→ATL/BG · approved consolidation",
    "reconsolidation": "ATL update · source-linked supersession",
    "checkpoint": "Lifecycle · durable checkpoint",
}

# Files that directly determine this deterministic suite. A recorded manifest
# hashes the versions at its repository_commit; a new run hashes the current
# checkout. The ontology was added after the recorded run and is included for
# current runs because BrainAIRuntime now loads it during initialization.
IMPLEMENTATION_INPUTS = (
    "benchmarks/run_component_ablation.py",
    "benchmarks/component_ablation_cases.jsonl",
    "src/brain_ai_memory/__init__.py",
    "src/brain_ai_memory/runtime.py",
    "src/brain_ai_memory/storage.py",
    "src/brain_ai_memory/text.py",
    "src/brain_ai_memory/config.py",
    "src/brain_ai_memory/adapters.py",
    "src/brain_ai_memory/ontology.py",
    "schema/brain_components.yaml",
)

SEMANTIC_NORMALIZATION = "component-ablation-outcome-v1"
SEMANTIC_EXCLUDED_FIELDS = (
    "latency_ms",
    "observed.counts_before.entities",
    "observed.counts_before.relations",
    "observed.counts_after.entities",
    "observed.counts_after.relations",
)


@dataclass(frozen=True)
class Condition:
    name: str
    family: str
    features: frozenset[str]
    changed_feature: str | None


def load_cases(path: Path = CASES) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def conditions() -> list[Condition]:
    output = [Condition("flat-retrieval-control", "control", frozenset(), None)]
    enabled: set[str] = set()
    for index, feature in enumerate(FEATURES, start=1):
        enabled.add(feature)
        output.append(
            Condition(
                f"cumulative-{index:02d}-{feature.replace('_', '-')}",
                "cumulative",
                frozenset(enabled),
                feature,
            )
        )
    full = frozenset(FEATURES)
    for feature in FEATURES:
        output.append(
            Condition(
                f"remove-{feature.replace('_', '-')}",
                "leave-one-out",
                full - {feature},
                feature,
            )
        )
    return output


def seed(runtime: BrainAIRuntime) -> tuple[dict[str, str], list[dict]]:
    ids: dict[str, str] = {}
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
        "After the cache incident, the team invalidated stale pointers and rebuilt the index.",
        source="benchmark",
    )["id"]
    runtime.store.set_state("atlas_open_reviews", 3, source="benchmark")
    runtime.store.set_state("retry_failures", 7, source="benchmark")
    runtime.store.add_rule(
        "deploy production",
        reason="production deployment requires approval",
        source="benchmark",
    )
    runtime.store.add_rule(
        "publish preview",
        effect="warn",
        reason="preview publication should be announced",
        source="benchmark",
    )

    flat: list[dict] = []
    for item in runtime.store.knowledge():
        flat.append({"id": item["id"], "text": item["text"], "source_type": "semantic"})
    for item in runtime.store.events():
        flat.append({"id": item["id"], "text": item["text"], "source_type": "episodic"})
    for item in runtime.store.states():
        flat.append(
            {
                "id": item["key"],
                "text": f"{item['key']} {item['value']}",
                "source_type": "untyped-text",
            }
        )
    return ids, flat


def _recall(
    runtime: BrainAIRuntime,
    case: dict,
    condition: Condition,
    ids: dict[str, str],
    flat: list[dict],
) -> tuple[bool, dict]:
    feature = case["mechanism"]
    expected_id = ids.get(case["expected_id"], case["expected_id"])
    if "pfc_routing" in condition.features and feature in condition.features:
        result = runtime.recall(case["query"], limit=1)
        hits = result["by_component"].get(case["expected_component"], [])
        hit = hits[0] if hits else None
        observed = {
            "route": result["route"],
            "top_id_matches": bool(hit and hit.get("id") == expected_id),
            "component": hit.get("component") if hit else None,
            "kind": hit.get("kind") if hit else None,
            "typed_value": hit.get("value") if hit else None,
        }
    else:
        hits = ranked(flat, case["query"], limit=1)
        hit = hits[0] if hits else None
        observed = {
            "route": ["flat"],
            "top_id_matches": bool(hit and hit.get("id") == expected_id),
            "component": "flat" if hit else None,
            "kind": hit.get("source_type") if hit else None,
            "typed_value": None,
        }
    checks = {
        "top_id": observed["top_id_matches"],
        "component": observed["component"] == case["expected_component"],
        "kind": observed["kind"] == case["expected_kind"],
    }
    if case["task"] == "state":
        checks["typed_value"] = observed["typed_value"] == case["expected_value"]
    return all(checks.values()), {**observed, "checks": checks}


def _gate(runtime: BrainAIRuntime, case: dict, condition: Condition) -> tuple[bool, dict]:
    enabled = case["mechanism"] in condition.features
    if enabled:
        result = runtime.gate(case["action"])
    else:
        result = {
            "allowed": True,
            "effect": "allow",
            "reason": "gate or stored-rule mechanism removed",
            "rule_id": None,
        }
    checks = {
        "allowed": result["allowed"] is case["expected_allowed"],
        "effect": result["effect"] == case["expected_effect"],
    }
    return all(checks.values()), {
        "allowed": result["allowed"],
        "effect": result["effect"],
        "reason": result["reason"],
        "checks": checks,
    }


def _sequence(runtime: BrainAIRuntime, case: dict, condition: Condition) -> tuple[bool, dict]:
    fail = [sys.executable, "-c", "raise SystemExit(1)"]
    if case["scenario"] == "recover":
        steps = [fail, [sys.executable, "-c", "print('recovered')"]]
    else:
        steps = [fail, [sys.executable, "-c", "raise SystemExit(2)"]]
    if "cb_sequence" in condition.features:
        result = runtime.execute_sequence("component ablation", steps)
    else:
        first = runtime.execute("component ablation", steps[0])
        result = {"status": first["status"], "attempt_count": 1, "attempts": [first]}
    recovered = False
    if result["attempts"]:
        execution = result["attempts"][-1].get("execution") or {}
        recovered = execution.get("stdout", "").strip() == "recovered"
    checks = {
        "status": result["status"] == case["expected_status"],
        "attempt_count": result["attempt_count"] == case["expected_attempt_count"],
    }
    if case["scenario"] == "recover":
        checks["fallback_output"] = recovered
    return all(checks.values()), {
        "status": result["status"],
        "attempt_count": result["attempt_count"],
        "fallback_output_recovered": recovered,
        "checks": checks,
    }


def _consolidation(runtime: BrainAIRuntime, case: dict, condition: Condition) -> tuple[bool, dict]:
    scenario = case["scenario"]
    kwargs = {"promote_to": "semantic"}
    if scenario == "rule":
        kwargs = {"promote_to": "rule", "rule_pattern": "ship release"}
    event = runtime.store.append_event(
        "Approved release knowledge from repeated episodes.", source="benchmark", **kwargs
    )
    before = runtime.store.counts()
    if "consolidation" in condition.features:
        result = runtime.consolidate(apply=scenario != "preview")
    else:
        result = {"applied": False, "candidate_count": 0, "candidates": []}
    after = runtime.store.counts()
    active_event_ids = {item["id"] for item in runtime.store.events()}
    status = result["candidates"][0]["status"] if result["candidates"] else None
    if scenario == "preview":
        checks = {
            "candidate_visible": result["candidate_count"] == 1,
            "approval_required": status == "pending-approval",
            "no_semantic_mutation": after["semantic"] == before["semantic"],
            "episode_still_active": event["id"] in active_event_ids,
        }
    elif scenario == "semantic":
        created = [item for item in runtime.store.knowledge() if item["source"].startswith("consolidated:")]
        checks = {
            "applied": status == "applied",
            "semantic_created": len(created) == 1,
            "episode_migrated": event["id"] not in active_event_ids,
        }
    else:
        created = [item for item in runtime.store.rules() if item["source"].startswith("consolidated:")]
        checks = {
            "applied": status == "applied",
            "rule_created": len(created) == 1,
            "episode_migrated": event["id"] not in active_event_ids,
        }
    return all(checks.values()), {
        "scenario": scenario,
        "candidate_count": result["candidate_count"],
        "candidate_status": status,
        "counts_before": before,
        "counts_after": after,
        "episode_active": event["id"] in active_event_ids,
        "checks": checks,
    }


def _reconsolidation(runtime: BrainAIRuntime, condition: Condition) -> tuple[bool, dict]:
    old = runtime.store.put_knowledge("The Atlas release day is Friday.", source="benchmark")
    if "reconsolidation" in condition.features:
        result = runtime.reconsolidate(
            old["id"], "The Atlas release day is Thursday.", source="benchmark-update"
        )
        new_id = result["new_id"]
    else:
        new_id = runtime.store.put_knowledge(
            "The Atlas release day is Thursday.", source="append-only-control"
        )["id"]
    all_items = runtime.store.knowledge(include_inactive=True)
    active = runtime.store.knowledge()
    old_item = next(item for item in all_items if item["id"] == old["id"])
    new_item = next(item for item in all_items if item["id"] == new_id)
    checks = {
        "one_active_fact": len([item for item in active if "Atlas release day" in item["text"]]) == 1,
        "old_superseded": old_item["status"] == "superseded",
        "provenance_link": new_item["supersedes"] == old["id"],
    }
    return all(checks.values()), {
        "active_fact_count": len([item for item in active if "Atlas release day" in item["text"]]),
        "old_status": old_item["status"],
        "new_links_to_old": new_item["supersedes"] == old["id"],
        "checks": checks,
    }


def _checkpoint(runtime: BrainAIRuntime, condition: Condition) -> tuple[bool, dict]:
    pending = runtime.store.append_event(
        "Pending lesson for the next session.", source="benchmark", promote_to="semantic"
    )
    if "checkpoint" in condition.features:
        record = runtime.checkpoint("ablation checkpoint")
    else:
        record = {
            "summary": "",
            "counts": runtime.store.counts(),
            "pending_consolidation": [],
        }
    persisted = runtime.store.checkpoints()
    checks = {
        "summary": record["summary"] == "ablation checkpoint",
        "pending_captured": pending["id"] in record["pending_consolidation"],
        "persisted": len(persisted) == 1,
        "counts_captured": record["counts"]["episodic"] >= 1,
    }
    return all(checks.values()), {
        "summary": record["summary"],
        "pending_captured": pending["id"] in record["pending_consolidation"],
        "persisted_count": len(persisted),
        "checks": checks,
    }


def evaluate_case(case: dict, condition: Condition) -> tuple[bool, dict, float]:
    with tempfile.TemporaryDirectory() as tmp:
        runtime = BrainAIRuntime(Path(tmp) / ".brain-ai")
        ids, flat = seed(runtime)
        started = time.perf_counter()
        if case["task"] == "route":
            route = runtime.route(case["query"]) if "pfc_routing" in condition.features else ["flat"]
            checks = {component: component in route for component in case["expected_components"]}
            passed, observed = all(checks.values()), {"route": route, "checks": checks}
        elif case["task"] in {"recall", "state"}:
            passed, observed = _recall(runtime, case, condition, ids, flat)
        elif case["task"] == "gate":
            passed, observed = _gate(runtime, case, condition)
        elif case["task"] == "sequence":
            passed, observed = _sequence(runtime, case, condition)
        elif case["task"] == "consolidation":
            passed, observed = _consolidation(runtime, case, condition)
        elif case["task"] == "reconsolidation":
            passed, observed = _reconsolidation(runtime, condition)
        elif case["task"] == "checkpoint":
            passed, observed = _checkpoint(runtime, condition)
        else:
            raise ValueError(f"unknown task: {case['task']}")
        latency_ms = (time.perf_counter() - started) * 1000
    return passed, observed, latency_ms


def run_suite(cases: list[dict] | None = None) -> tuple[list[dict], dict]:
    cases = cases or load_cases()
    all_conditions = conditions()
    records: list[dict] = []
    for condition in all_conditions:
        for case in cases:
            passed, observed, latency_ms = evaluate_case(case, condition)
            records.append(
                {
                    "condition": condition.name,
                    "condition_family": condition.family,
                    "enabled_features": sorted(condition.features, key=FEATURES.index),
                    "changed_feature": condition.changed_feature,
                    "case_id": case["id"],
                    "category": case["category"],
                    "mechanism": case["mechanism"],
                    "passed": passed,
                    "latency_ms": round(latency_ms, 3),
                    "observed": observed,
                }
            )
    return records, summarize(records, cases, all_conditions)


def _condition_summary(records: list[dict], name: str, case_count: int) -> dict:
    selected = [record for record in records if record["condition"] == name]
    latencies = [record["latency_ms"] for record in selected]
    by_category = {}
    for category in sorted({record["category"] for record in selected}):
        group = [record for record in selected if record["category"] == category]
        by_category[category] = {
            "passed": sum(record["passed"] for record in group),
            "total": len(group),
        }
    return {
        "condition": name,
        "passed": sum(record["passed"] for record in selected),
        "total": case_count,
        "accuracy": sum(record["passed"] for record in selected) / case_count,
        "mean_latency_ms": round(statistics.fmean(latencies), 3),
        "p95_latency_ms": sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)],
        "by_category": by_category,
    }


def summarize(records: list[dict], cases: list[dict], all_conditions: list[Condition]) -> dict:
    case_count = len(cases)
    condition_rows = [_condition_summary(records, item.name, case_count) for item in all_conditions]
    by_name = {row["condition"]: row for row in condition_rows}
    flat_score = by_name["flat-retrieval-control"]["passed"]
    full_name = f"cumulative-{len(FEATURES):02d}-{FEATURES[-1].replace('_', '-')}"
    full_score = by_name[full_name]["passed"]
    previous_passes = {
        record["case_id"] for record in records
        if record["condition"] == "flat-retrieval-control" and record["passed"]
    }
    effects = []
    for index, feature in enumerate(FEATURES, start=1):
        cumulative_name = f"cumulative-{index:02d}-{feature.replace('_', '-')}"
        current_passes = {
            record["case_id"] for record in records
            if record["condition"] == cumulative_name and record["passed"]
        }
        removal_name = f"remove-{feature.replace('_', '-')}"
        removal_failures = sorted(
            record["case_id"] for record in records
            if record["condition"] == removal_name and not record["passed"]
        )
        effects.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS[feature],
                "cumulative_condition": cumulative_name,
                "cumulative_score": by_name[cumulative_name]["passed"],
                "newly_recovered_cases": sorted(current_passes - previous_passes),
                "leave_one_out_condition": removal_name,
                "leave_one_out_score": by_name[removal_name]["passed"],
                "drop_from_full": full_score - by_name[removal_name]["passed"],
                "failed_without_feature": removal_failures,
            }
        )
        previous_passes = current_passes
    for row in condition_rows:
        row["delta_vs_flat"] = row["passed"] - flat_score
        row["delta_vs_full"] = row["passed"] - full_score
    flat_memory = [
        record for record in records
        if record["condition"] == "flat-retrieval-control"
        and record["category"] in {"semantic_memory", "episodic_memory", "exact_state"}
    ]
    return {
        "benchmark": "Brain-AI ten-mechanism lifecycle/control contract ablation",
        "claim_scope": "authored deterministic contracts for ten ablated mechanisms only; not the full package, external LLM QA, or agent-quality efficacy",
        "case_count": case_count,
        "condition_count": len(all_conditions),
        "record_count": len(records),
        "flat_condition": "flat-retrieval-control",
        "full_condition": full_name,
        "flat_retrieval_diagnostic": {
            "top_id_matches": sum(
                bool(record["observed"].get("top_id_matches")) for record in flat_memory
            ),
            "memory_query_count": len(flat_memory),
            "note": "content retrieval only; typed component and exact-value checks are scored separately",
        },
        "conditions": condition_rows,
        "component_effects": effects,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalized_semantic_outcomes(records: list[dict]) -> list[dict]:
    """Return stable scored outcomes, excluding diagnostics and schema-only counts.

    Latency is environment-dependent. The entity/relation count keys were added
    to MemoryStore.counts after the recorded run but do not change any ablation
    check. Every other field remains in the digest so a behavioral difference
    fails parity instead of being silently normalized away.
    """

    normalized: list[dict] = []
    for record in records:
        item = json.loads(json.dumps(record, ensure_ascii=False))
        item.pop("latency_ms", None)
        observed = item.get("observed")
        if isinstance(observed, dict):
            for name in ("counts_before", "counts_after"):
                counts = observed.get(name)
                if isinstance(counts, dict):
                    counts.pop("entities", None)
                    counts.pop("relations", None)
        normalized.append(item)
    return sorted(
        normalized,
        key=lambda item: (str(item.get("condition", "")), str(item.get("case_id", ""))),
    )


def semantic_outcome_sha256(records: list[dict]) -> str:
    payload = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in normalized_semantic_outcomes(records)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def implementation_sha256() -> dict[str, str]:
    return {
        relative: sha256_file(ROOT / relative)
        for relative in IMPLEMENTATION_INPUTS
    }


def verify_reference(records: list[dict], manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    semantic = manifest.get("semantic_outcome", {})
    if semantic.get("normalization") != SEMANTIC_NORMALIZATION:
        raise ValueError(
            f"unsupported semantic normalization in {manifest_path}: "
            f"{semantic.get('normalization')!r}"
        )
    if tuple(semantic.get("excluded_fields", ())) != SEMANTIC_EXCLUDED_FIELDS:
        raise ValueError(f"semantic exclusions do not match {SEMANTIC_NORMALIZATION}")
    expected = semantic.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"semantic outcome digest is missing or invalid in {manifest_path}")
    actual = semantic_outcome_sha256(records)
    if actual != expected:
        raise ValueError(
            f"semantic outcome differs from recorded run: expected {expected}, got {actual}"
        )
    return {
        "reference_manifest": str(manifest_path),
        "normalization": SEMANTIC_NORMALIZATION,
        "semantic_outcome_sha256": actual,
        "semantic_parity": True,
    }


def verify_recorded_source_provenance(manifest_path: Path) -> dict:
    """Verify source hashes against blobs at the manifest's recorded commit."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    commit = manifest.get("repository_commit")
    expected_by_path = manifest.get("implementation_sha256", {})
    if not commit or not expected_by_path:
        raise ValueError(f"recorded source provenance is incomplete in {manifest_path}")
    if not isinstance(commit, str) or not 7 <= len(commit) <= 40 or any(
        character not in "0123456789abcdefABCDEF" for character in commit
    ):
        raise ValueError(f"invalid recorded git commit in {manifest_path}")
    verified = 0
    for relative, expected in expected_by_path.items():
        source_path = Path(relative)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise ValueError(f"unsafe recorded source path: {relative}")
        result = subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(
                f"cannot read {relative} at recorded commit {commit}; fetch repository history"
            )
        actual = hashlib.sha256(result.stdout).hexdigest()
        if actual != expected:
            raise ValueError(
                f"recorded source hash mismatch for {relative}: expected {expected}, got {actual}"
            )
        verified += 1
    return {"repository_commit": commit, "source_files_verified": verified}


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def render_report(summary: dict) -> str:
    by_name = {row["condition"]: row for row in summary["conditions"]}
    flat = by_name[summary["flat_condition"]]
    full = by_name[summary["full_condition"]]
    lines = [
        "# Ten-mechanism lifecycle/control contract ablation (2026-07-15)",
        "",
        "This deterministic benchmark removes and cumulatively adds ten authored",
        "lifecycle/control mechanisms. It asks whether those mechanisms execute their",
        "stated contracts; it does **not** cover the whole public package or test",
        "LLM answer quality, general reasoning, or real-world agent",
        "efficacy. The cases are authored around these contracts, so this is not an",
        "external benchmark or evidence that a brain-inspired architecture beats RAG.",
        "",
        "## Result",
        "",
        "| condition | passed | rate | delta vs all-ten |",
        "|---|---:|---:|---:|",
        f"| flat retrieval-only control | {flat['passed']} / {flat['total']} | {flat['accuracy']:.1%} | {flat['delta_vs_full']:+d} |",
        f"| all ten mechanisms enabled | {full['passed']} / {full['total']} | {full['accuracy']:.1%} | {full['delta_vs_full']:+d} |",
        "",
        f"The flat control retrieved the expected top item for {summary['flat_retrieval_diagnostic']['top_id_matches']} / {summary['flat_retrieval_diagnostic']['memory_query_count']} memory queries (see",
        "`observed.top_id_matches` in `records.jsonl`) but does not satisfy typed",
        "routing, exact-state, gating, fallback, or lifecycle contracts.",
        "",
        "## What each addition recovered",
        "",
        "| addition | cumulative score | newly recovered contract cases |",
        "|---|---:|---|",
    ]
    for effect in summary["component_effects"]:
        recovered = ", ".join(f"`{case}`" for case in effect["newly_recovered_cases"]) or "—"
        lines.append(
            f"| {effect['label']} | {effect['cumulative_score']} / {summary['case_count']} | {recovered} |"
        )
    lines.extend(
        [
            "",
            "## Leave-one-out removal from the all-ten condition",
            "",
            "| removed mechanism | score | drop | contracts that fail |",
            "|---|---:|---:|---|",
        ]
    )
    for effect in summary["component_effects"]:
        failures = ", ".join(f"`{case}`" for case in effect["failed_without_feature"]) or "—"
        lines.append(
            f"| {effect['label']} | {effect['leave_one_out_score']} / {summary['case_count']} | -{effect['drop_from_full']} | {failures} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- Scores mean only that deterministic software contracts were met.",
            "- Entity/relation management, ontology loading, MCP/CLI surfaces, semantic",
            "  adapters, and provider-host integration are outside these 20 cases.",
            "- PFC removal has a larger drop because routed memory access depends on it;",
            "  this is an explicit dependency, not a measured biological interaction.",
            "- Latency includes fresh local-store setup and subprocess startup for the",
            "  executable-sequence cases. It is diagnostic, not a production estimate.",
            "- No LLM, network service, hidden operational data, or external judge is used.",
            "- End-to-end quality claims still require preregistered LongMemEval or",
            "  MemoryAgentBench runs with matched model and context budgets.",
            "",
            "## Reproduce and compare",
            "",
            "The artifacts record the source commit named in `manifest.json`. A second",
            "run is not expected to reproduce artifact bytes: latency and generated",
            "metadata vary. Compare normalized semantic outcomes instead:",
            "",
            "```bash",
            "python3 benchmarks/run_component_ablation.py \\",
            "  --output /tmp/component-ablation-current \\",
            "  --reference-manifest benchmarks/pilots/component-ablation-20260715/manifest.json \\",
            "  --verify-source-provenance",
            "python3 -m pip install \".[plot]\"",
            "python3 benchmarks/plot_component_ablation.py \\",
            "  --summary /tmp/component-ablation-current/summary.json \\",
            "  --output /tmp/component-ablation-current.png",
            "python3 -m unittest discover -s tests -v",
            "```",
            "",
            "Artifacts: `records.jsonl` contains every condition × case observation;",
            "`summary.json` contains aggregates and recovered/failing case IDs;",
            "`manifest.json` records hashes and the exact condition matrix.",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(output: Path, records: list[dict], summary: dict, cases_path: Path) -> dict:
    # Capture provenance before writing into a tracked output directory; otherwise
    # the benchmark would mark a clean source tree dirty because of its own files.
    repository_commit = git_value("rev-parse", "HEAD")
    repository_dirty = bool(git_value("status", "--porcelain"))
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.jsonl"
    summary_path = output / "summary.json"
    report_path = output / "README.md"
    records_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(summary), encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "run_id": output.name,
        "status": "complete",
        "benchmark": summary["benchmark"],
        "claim_scope": summary["claim_scope"],
        "release_grade_external_benchmark": False,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository_commit": repository_commit,
        "repository_dirty": repository_dirty,
        "execution": {
            "python": sys.version.split()[0],
            "external_llm_or_api": False,
            "case_count": summary["case_count"],
            "condition_count": summary["condition_count"],
            "record_count": summary["record_count"],
        },
        "condition_matrix": [
            {
                "name": item.name,
                "family": item.family,
                "enabled_features": sorted(item.features, key=FEATURES.index),
                "changed_feature": item.changed_feature,
            }
            for item in conditions()
        ],
        "input_sha256": {
            "cases": sha256_file(cases_path),
            "runner": sha256_file(Path(__file__)),
        },
        "implementation_sha256": implementation_sha256(),
        "semantic_outcome": {
            "normalization": SEMANTIC_NORMALIZATION,
            "excluded_fields": list(SEMANTIC_EXCLUDED_FIELDS),
            "sha256": semantic_outcome_sha256(records),
        },
        "artifact_sha256": {
            "records.jsonl": sha256_file(records_path),
            "summary.json": sha256_file(summary_path),
            "README.md": sha256_file(report_path),
        },
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--reference-manifest",
        type=Path,
        help="fail unless normalized semantic outcomes match this recorded manifest",
    )
    parser.add_argument(
        "--verify-records",
        type=Path,
        help="verify an existing records.jsonl instead of running the suite",
    )
    parser.add_argument(
        "--verify-source-provenance",
        action="store_true",
        help="verify reference implementation hashes against its recorded git commit",
    )
    args = parser.parse_args()
    if args.verify_records:
        if not args.reference_manifest:
            parser.error("--verify-records requires --reference-manifest")
        result = verify_reference(load_records(args.verify_records), args.reference_manifest)
        if args.verify_source_provenance:
            result.update(verify_recorded_source_provenance(args.reference_manifest))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.verify_source_provenance and not args.reference_manifest:
        parser.error("--verify-source-provenance requires --reference-manifest")
    cases = load_cases(args.cases)
    records, summary = run_suite(cases)
    verification = None
    if args.reference_manifest:
        verification = verify_reference(records, args.reference_manifest)
        if args.verify_source_provenance:
            verification.update(verify_recorded_source_provenance(args.reference_manifest))
    manifest = write_artifacts(args.output, records, summary, args.cases)
    by_name = {row["condition"]: row for row in summary["conditions"]}
    flat = by_name[summary["flat_condition"]]
    full = by_name[summary["full_condition"]]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "flat": f"{flat['passed']}/{flat['total']}",
                "all_ten": f"{full['passed']}/{full['total']}",
                "records": summary["record_count"],
                "manifest_status": manifest["status"],
                "recorded_semantic_parity": (
                    verification["semantic_parity"] if verification else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
