from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "benchmarks" / "run_component_ablation.py"
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


if __name__ == "__main__":
    unittest.main()
