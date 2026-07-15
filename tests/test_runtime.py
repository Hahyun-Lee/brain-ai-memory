from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from brain_ai_memory.adapters import SmartConnectionsAdapter, VaultBM25Adapter
from brain_ai_memory.runtime import BrainAIRuntime


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / ".brain-ai"
        self.runtime = BrainAIRuntime(self.home)

    def tearDown(self):
        self.temp.cleanup()

    def test_differentiated_recall_and_gate(self):
        self.runtime.store.put_knowledge("배포 전에는 코드 리뷰가 완료되어야 한다", source="test")
        self.runtime.store.append_event("배포 일정이 금요일에서 목요일로 변경되었다", source="test")
        self.runtime.store.set_state("open_reviews", 3, source="test")
        self.runtime.store.add_rule(r"deploy\s+production", reason="approval required", source="test")

        result = self.runtime.process(
            "최근 배포 규칙과 open review 개수는?",
            proposed_action="deploy production",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("IPS", result["route"])
        self.assertIn("HC", result["route"])
        self.assertTrue(result["memory"]["ATL"])
        self.assertEqual(result["memory"]["IPS"][0]["value"], 3)

    def test_builtin_gate_blocks_and_harness_runs_safe_command(self):
        blocked = self.runtime.execute("unsafe", ["rm", "-rf", "/"])
        self.assertEqual(blocked["status"], "blocked")
        safe = self.runtime.execute("safe", [sys.executable, "-c", "print('ok')"])
        self.assertEqual(safe["status"], "completed")
        self.assertEqual(safe["execution"]["stdout"].strip(), "ok")

    def test_sequence_consumes_fallback_until_success(self):
        result = self.runtime.execute_sequence(
            "fallback",
            [
                [sys.executable, "-c", "raise SystemExit(1)"],
                [sys.executable, "-c", "print('recovered')"],
            ],
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["attempts"][1]["execution"]["stdout"].strip(), "recovered")

    def test_consolidation_requires_apply(self):
        event = self.runtime.store.append_event(
            "Repeated failures should become a reusable rule.",
            source="test",
            promote_to="semantic",
        )
        preview = self.runtime.consolidate()
        self.assertEqual(preview["candidates"][0]["status"], "pending-approval")
        self.assertEqual(self.runtime.store.counts()["semantic"], 0)
        applied = self.runtime.consolidate(apply=True)
        self.assertEqual(applied["candidates"][0]["status"], "applied")
        self.assertNotIn(event["id"], [item["id"] for item in self.runtime.store.events()])
        self.assertEqual(self.runtime.store.counts()["semantic"], 1)

    def test_seven_operation_lifecycle_hides_archived_event(self):
        event = self.runtime.store.append_event("resolved old incident", source="test")
        self.runtime.store.record_lifecycle("episodic", event["id"], "archive", "resolved")
        self.assertEqual(self.runtime.store.events(), [])
        self.assertEqual(len(self.runtime.store.events(include_inactive=True)), 1)

    def test_reconsolidation_supersedes_stale_knowledge(self):
        old = self.runtime.store.put_knowledge("Release day is Friday", source="test")
        result = self.runtime.reconsolidate(old["id"], "Release day is Thursday", source="test")
        active = self.runtime.store.knowledge()
        self.assertEqual(result["old_id"], old["id"])
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["text"], "Release day is Thursday")
        self.assertEqual(active[0]["supersedes"], old["id"])


class AdapterTest(unittest.TestCase):
    def test_vault_fallback_covers_unindexed_korean_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / ".smart-env").mkdir()
            (vault / "새노트.md").write_text("장기 실행 에이전트의 메모리 생명주기", encoding="utf-8")
            results = VaultBM25Adapter(vault).search("메모리 생명주기")
            self.assertEqual(results[0]["path"], "새노트.md")
            self.assertEqual(results[0]["backend"], "vault-bm25")

    def test_smart_connections_mcp_and_vault_results_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            (vault / "MCP.md").write_text("semantic memory from MCP", encoding="utf-8")
            (vault / "Local.md").write_text("한국어 메모리 생명주기 fallback", encoding="utf-8")
            server = root / "fake_mcp.py"
            server.write_text(
                """import json, sys
for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    if msg['method']=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{},'serverInfo':{'name':'fake','version':'1'}}
    else: result={'content':[{'type':'text','text':json.dumps([{'path':'MCP.md','similarity':0.9}])}]}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}), flush=True)
""",
                encoding="utf-8",
            )
            adapter = SmartConnectionsAdapter(vault, [sys.executable, str(server)], timeout=3, merge_local=True)
            results = adapter.search("한국어 메모리 생명주기", limit=5)
            backends = " ".join(result["backend"] for result in results)
            self.assertIn("smart-connections-mcp", backends)
            self.assertIn("vault-bm25", backends)
            self.assertEqual(adapter.last_diagnostic["mcp"], "ok")
            self.assertEqual(adapter.last_diagnostic["fusion"], "reciprocal-rank")


if __name__ == "__main__":
    unittest.main()
