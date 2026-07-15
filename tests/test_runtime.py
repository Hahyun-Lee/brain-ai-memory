from __future__ import annotations

import json
import asyncio
import sys
import os
import tempfile
import unittest
from pathlib import Path

from brain_ai_memory.adapters import SmartConnectionsAdapter, VaultBM25Adapter
from brain_ai_memory.cli import run_tour
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

    def test_harness_and_sequence_consume_entity_scoped_rules(self):
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project")
        boreal = self.runtime.store.put_entity("Boreal", entity_type="project")
        self.runtime.store.add_rule(
            r"entity-sensitive-command",
            reason="Atlas-specific approval required",
            entities=[atlas["id"]],
        )
        command = [sys.executable, "-c", "print('ok')", "entity-sensitive-command"]

        blocked = self.runtime.execute("deploy", command, entity="Atlas")
        allowed = self.runtime.execute("deploy", command, entity=boreal["id"])
        sequence = self.runtime.execute_sequence(
            "deploy",
            [command],
            entity=atlas["id"],
        )

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["entity"]["id"], atlas["id"])
        self.assertEqual(allowed["status"], "completed")
        self.assertEqual(sequence["status"], "blocked")
        self.assertEqual(sequence["entity"], atlas["id"])

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

    def test_lifecycle_delete_is_a_recoverable_tombstone_not_physical_erasure(self):
        event = self.runtime.store.append_event("superseded claim", source="test")
        decision = self.runtime.store.record_lifecycle(
            "episodic", event["id"], "delete", "made void by later evidence"
        )
        self.assertEqual(decision["operation"], "delete")
        self.assertEqual(self.runtime.store.events(), [])
        retained = self.runtime.store.events(include_inactive=True)
        self.assertEqual([item["id"] for item in retained], [event["id"]])
        self.assertEqual(retained[0]["text"], "superseded claim")

        knowledge = self.runtime.store.put_knowledge("obsolete policy", source="test")
        self.runtime.store.record_lifecycle(
            "semantic", knowledge["id"], "delete", "superseded"
        )
        self.assertEqual(self.runtime.store.knowledge(), [])
        retained_knowledge = self.runtime.store.knowledge(include_inactive=True)
        self.assertEqual(retained_knowledge[0]["status"], "deleted")
        self.assertEqual(retained_knowledge[0]["text"], "obsolete policy")

    def test_reconsolidation_supersedes_stale_knowledge(self):
        old = self.runtime.store.put_knowledge("Release day is Friday", source="test")
        result = self.runtime.reconsolidate(old["id"], "Release day is Thursday", source="test")
        active = self.runtime.store.knowledge()
        self.assertEqual(result["old_id"], old["id"])
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["text"], "Release day is Thursday")
        self.assertEqual(active[0]["supersedes"], old["id"])

    def test_entity_relations_scope_memory_rules_and_exact_state(self):
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project", aliases=["A"])
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project", aliases=["Project Atlas"])
        boreal = self.runtime.store.put_entity("Boreal", entity_type="project")
        release = self.runtime.store.put_entity("Atlas 2.1", entity_type="release")
        relation = self.runtime.store.add_relation(release["id"], "belongs_to", atlas["id"])
        self.runtime.store.put_knowledge(
            "Atlas deploys on Thursday", source="test", entities=[atlas["id"]]
        )
        self.runtime.store.put_knowledge(
            "Boreal deploys on Monday", source="test", entities=[boreal["id"]]
        )
        self.runtime.store.set_state("open_reviews", 3, entity=atlas["id"])
        self.runtime.store.set_state("open_reviews", 7, entity=boreal["id"])
        self.runtime.store.set_state("open_reviews", 99)
        self.runtime.store.add_rule(
            r"deploy\s+production",
            reason="Atlas approval required",
            entities=[atlas["id"]],
        )

        atlas_result = self.runtime.process(
            "How many open reviews before deploy?",
            proposed_action="deploy production",
            entity="A",
        )
        boreal_result = self.runtime.process(
            "How many open reviews before deploy?",
            proposed_action="deploy production",
            entity=boreal["id"],
        )

        self.assertEqual(relation["predicate"], "belongs_to")
        self.assertEqual(atlas["aliases"], ["A", "Project Atlas"])
        self.assertEqual(atlas_result["entity"]["id"], atlas["id"])
        self.assertEqual(atlas_result["memory"]["IPS"][0]["value"], 3)
        self.assertEqual(atlas_result["status"], "blocked")
        self.assertEqual(boreal_result["memory"]["IPS"][0]["value"], 7)
        self.assertEqual(boreal_result["status"], "ready")
        self.assertTrue(
            all("Boreal" not in item["text"] for item in atlas_result["memory"]["ATL"])
        )

    def test_ontology_is_loaded_and_validated_at_startup(self):
        summary = self.runtime.ontology_summary
        self.assertEqual(summary["component_count"], 7)
        self.assertEqual(summary["category_counts"], {"memory": 5, "control": 2})
        self.assertEqual(summary["channel_count"], 2)
        self.assertIn("PFC", summary["component_ids"])
        self.assertIn("consolidation", summary["channel_ids"])

    def test_tour_closes_the_failure_to_control_loop(self):
        tour = run_tour(self.runtime)
        self.assertIn("Thursday", tour["found"])
        self.assertIn(
            tour["found"],
            {item["text"] for item in tour["evidence"]["context"]["memory"]["ATL"]},
        )
        self.assertTrue(
            all(
                "Friday" not in item["text"]
                for item in tour["evidence"]["context"]["memory"]["ATL"]
            )
        )
        self.assertEqual(tour["exact_state"], "open_reviews = 3")
        self.assertIn("approval", tour["blocked"])
        self.assertEqual(tour["fallback"], "completed after 2 attempts")
        self.assertIn("superseded", tour["updated"])
        self.assertIn("Friday", tour["updated"])
        self.assertIn("Thursday", tour["updated"])


class MCPServerTest(unittest.TestCase):
    def test_mcp_surface_has_control_tools_but_no_arbitrary_exec(self):
        try:
            from brain_ai_memory.mcp_server import create_mcp_server
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("optional MCP dependency is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            server = create_mcp_server(Path(tmp) / ".brain-ai")
            names = {tool.name for tool in server._tool_manager.list_tools()}
            self.assertIn("brain_context", names)
            self.assertIn("brain_check_action", names)
            self.assertIn("brain_checkpoint", names)
            self.assertNotIn("execute", " ".join(names))
            resources = {str(resource.uri) for resource in server._resource_manager.list_resources()}
            self.assertEqual(resources, {"brain-ai://status", "brain-ai://ontology"})

    def test_mcp_stdio_round_trip(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self.skipTest("optional MCP dependency is not installed")

        async def exercise(home: Path):
            params = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-m",
                    "brain_ai_memory.mcp_server",
                    "--home",
                    str(home),
                ],
                env=dict(os.environ),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertIn("brain_context", names)
                    created = await session.call_tool(
                        "brain_upsert_entity",
                        {"name": "Atlas", "entity_type": "project"},
                    )
                    self.assertFalse(created.isError)
                    context = await session.call_tool(
                        "brain_context",
                        {"query": "What changed?", "entity": "Atlas"},
                    )
                    self.assertFalse(context.isError)
                    resources = await session.list_resources()
                    self.assertEqual(
                        {str(resource.uri) for resource in resources.resources},
                        {"brain-ai://status", "brain-ai://ontology"},
                    )

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(exercise(Path(tmp) / ".brain-ai"))


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
            adapter.close()

    def test_smart_connections_v2_envelope_preserves_server_hybrid_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            (vault / "Hybrid.md").write_text(
                "full private note text that should not replace the bounded server snippet",
                encoding="utf-8",
            )
            server = root / "fake_mcp_v2.py"
            server.write_text(
                """import json, os, sys
for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    if msg['method']=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{},'serverInfo':{'name':'fake-v2','version':'2'}}
    else: result={'content':[{'type':'text','text':json.dumps({'mode':'semantic','profile':os.environ.get('SMART_SEARCH_PROFILE'),'results':[{'path':'Hybrid.md','vault':'vault','similarity':0.91,'scope':'note','snippet':'bounded hybrid snippet','retrieval':['plugin-dense','bm25'],'scoreType':'rrf'}]})}]}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}), flush=True)
""",
                encoding="utf-8",
            )
            adapter = SmartConnectionsAdapter(
                vault,
                [sys.executable, str(server)],
                timeout=3,
                merge_local=True,
                env={"SMART_SEARCH_PROFILE": "adaptive"},
            )
            results = adapter.search("hybrid retrieval", limit=5)
            self.assertEqual(results[0]["path"], "Hybrid.md")
            self.assertEqual(results[0]["text"], "bounded hybrid snippet")
            self.assertEqual(results[0]["retrieval"], ["plugin-dense", "bm25"])
            self.assertAlmostEqual(results[0]["score"], 0.91)
            self.assertEqual(adapter.last_diagnostic["mcp_profile"], "adaptive")
            self.assertTrue(adapter.last_diagnostic["server_hybrid"])
            self.assertEqual(adapter.last_diagnostic["fallback_hits"], 0)
            self.assertEqual(adapter.last_diagnostic["fusion"], "server-ranked")
            first_pid = adapter._client.process.pid
            adapter.search("second warm query", limit=5)
            self.assertEqual(adapter._client.process.pid, first_pid)
            adapter.close()


if __name__ == "__main__":
    unittest.main()
