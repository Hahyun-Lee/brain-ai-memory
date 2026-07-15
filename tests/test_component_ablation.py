from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "benchmarks" / "run_component_ablation.py"
RECORDED_ROOT = ROOT / "benchmarks" / "pilots" / "component-ablation-20260715"
RECORDED_MANIFEST = RECORDED_ROOT / "manifest.json"
SPEC = importlib.util.spec_from_file_location("component_ablation", RUNNER)
assert SPEC and SPEC.loader
ablation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ablation
SPEC.loader.exec_module(ablation)


class ComponentAblationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = ablation.load_cases()
        cls.records, cls.summary = ablation.run_suite(cls.cases)

    def test_full_flat_and_component_effects(self):
        by_name = {row["condition"]: row for row in self.summary["conditions"]}
        flat = by_name[self.summary["flat_condition"]]
        full = by_name[self.summary["full_condition"]]
        self.assertEqual((flat["passed"], flat["total"]), (1, 20))
        self.assertEqual((full["passed"], full["total"]), (20, 20))
        self.assertEqual(self.summary["record_count"], 420)
        self.assertEqual(
            self.summary["flat_retrieval_diagnostic"],
            {
                "top_id_matches": 6,
                "memory_query_count": 6,
                "note": "content retrieval only; typed component and exact-value checks are scored separately",
            },
        )

        expected_drops = {
            "pfc_routing": 8,
            "atl_semantic": 2,
            "hc_episodic": 2,
            "ips_state": 2,
            "th_gate": 2,
            "bg_rules": 2,
            "cb_sequence": 2,
            "consolidation": 3,
            "reconsolidation": 1,
            "checkpoint": 1,
        }
        self.assertEqual(
            {item["feature"]: item["drop_from_full"] for item in self.summary["component_effects"]},
            expected_drops,
        )
        self.assertTrue(all(item["newly_recovered_cases"] for item in self.summary["component_effects"]))

    def test_written_artifact_hashes_and_record_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "run"
            manifest = ablation.write_artifacts(
                output, self.records, self.summary, ablation.CASES
            )
            lines = (output / "records.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), self.summary["record_count"])
            self.assertTrue(all(isinstance(json.loads(line), dict) for line in lines))
            for filename, expected in manifest["artifact_sha256"].items():
                actual = hashlib.sha256((output / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)
            self.assertEqual(
                manifest["semantic_outcome"]["sha256"],
                ablation.semantic_outcome_sha256(self.records),
            )
            self.assertIn("src/brain_ai_memory/runtime.py", manifest["implementation_sha256"])
            self.assertIn("schema/brain_components.yaml", manifest["implementation_sha256"])

    def test_current_outcomes_match_recorded_semantic_digest(self):
        manifest = json.loads(RECORDED_MANIFEST.read_text(encoding="utf-8"))
        recorded = ablation.load_records(RECORDED_ROOT / "records.jsonl")
        expected = manifest["semantic_outcome"]["sha256"]
        self.assertEqual(
            tuple(manifest["semantic_outcome"]["excluded_fields"]),
            ablation.SEMANTIC_EXCLUDED_FIELDS,
        )
        self.assertEqual(ablation.semantic_outcome_sha256(recorded), expected)
        self.assertEqual(ablation.semantic_outcome_sha256(self.records), expected)
        result = ablation.verify_reference(self.records, RECORDED_MANIFEST)
        self.assertTrue(result["semantic_parity"])

    def test_semantic_digest_excludes_only_documented_diagnostics(self):
        changed = json.loads(json.dumps(self.records))
        for row in changed:
            row["latency_ms"] = row["latency_ms"] + 987.654
            observed = row.get("observed", {})
            for name in ("counts_before", "counts_after"):
                counts = observed.get(name)
                if isinstance(counts, dict):
                    counts["entities"] = 999
                    counts["relations"] = 999
        self.assertEqual(
            ablation.semantic_outcome_sha256(changed),
            ablation.semantic_outcome_sha256(self.records),
        )
        changed[0]["passed"] = not changed[0]["passed"]
        self.assertNotEqual(
            ablation.semantic_outcome_sha256(changed),
            ablation.semantic_outcome_sha256(self.records),
        )

    def test_recorded_source_provenance(self):
        manifest = json.loads(RECORDED_MANIFEST.read_text(encoding="utf-8"))
        commit = manifest["repository_commit"]
        available = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if available.returncode != 0:
            self.skipTest("recorded source commit is unavailable in this shallow clone")
        result = ablation.verify_recorded_source_provenance(RECORDED_MANIFEST)
        self.assertEqual(
            result["repository_commit"],
            "d0d675ead16b96b6f4ac0a5aaab7ddcf20786ba7",
        )
        self.assertEqual(result["source_files_verified"], 8)


if __name__ == "__main__":
    unittest.main()
