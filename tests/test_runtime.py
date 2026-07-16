from __future__ import annotations

import json
import asyncio
import sys
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from brain_ai_memory.adapters import SmartConnectionsAdapter, VaultBM25Adapter
from brain_ai_memory.cli import run_tour
from brain_ai_memory.mcp_server import MCPUnavailableError, main as mcp_main
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

    def test_entity_reconsolidation_does_not_change_another_project(self):
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project")
        boreal = self.runtime.store.put_entity("Boreal", entity_type="project")
        old = self.runtime.store.put_knowledge(
            "Release day is Friday",
            source="test",
            entities=[atlas["id"], boreal["id"]],
        )
        with self.assertRaisesRegex(ValueError, "project-scoped supersession"):
            self.runtime.store.put_knowledge(
                "Unsafe global replacement",
                source="test",
                supersedes=old["id"],
            )

        result = self.runtime.reconsolidate(
            old["id"],
            "Release day is Thursday",
            source="test",
            entity="Atlas",
        )

        self.assertEqual(result["entity"], "Atlas")
        atlas_text = {
            item["text"]
            for item in self.runtime.store.search_knowledge(
                "Release day", entity_id=atlas["id"]
            )
        }
        boreal_text = {
            item["text"]
            for item in self.runtime.store.search_knowledge(
                "Release day", entity_id=boreal["id"]
            )
        }
        self.assertEqual(atlas_text, {"Release day is Thursday"})
        self.assertEqual(boreal_text, {"Release day is Friday"})
        second = self.runtime.reconsolidate(
            old["id"],
            "Release day is Monday",
            source="test",
            entity="Boreal",
        )
        edges = self.runtime.store.knowledge_supersessions(old_id=old["id"])
        self.assertEqual(
            {(edge["entity_id"], edge["replacement_id"]) for edge in edges},
            {
                (atlas["id"], result["new_id"]),
                (boreal["id"], second["new_id"]),
            },
        )

    def test_multiple_old_facts_can_converge_on_one_scoped_replacement(self):
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project")
        first = self.runtime.store.put_knowledge(
            "Release day is Friday",
            entities=[atlas["id"]],
        )
        second = self.runtime.store.put_knowledge(
            "Release date remains Friday",
            entities=[atlas["id"]],
        )

        replacement = self.runtime.reconsolidate(
            first["id"], "Release day is Thursday", entity=atlas["id"]
        )
        reused = self.runtime.reconsolidate(
            second["id"], "Release day is Thursday", entity=atlas["id"]
        )

        self.assertEqual(replacement["new_id"], reused["new_id"])
        edges = self.runtime.store.knowledge_supersessions(
            replacement_id=replacement["new_id"],
            entity_id=atlas["id"],
        )
        self.assertEqual({edge["old_id"] for edge in edges}, {first["id"], second["id"]})

    def test_entity_relations_scope_memory_rules_and_exact_state(self):
        before = self.runtime.store.counts()
        with self.assertRaisesRegex(KeyError, "unknown entity"):
            self.runtime.store.put_knowledge(
                "Must not become an orphan",
                entities=["missing-project"],
            )
        with self.assertRaisesRegex(KeyError, "unknown entity"):
            self.runtime.store.add_rule(
                r"deploy",
                reason="Must not become an orphan",
                entities=["missing-project"],
            )
        self.assertEqual(self.runtime.store.counts(), before)

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

    def test_entity_scope_is_applied_before_semantic_top_k(self):
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project")
        boreal = self.runtime.store.put_entity("Boreal", entity_type="project")
        atlas_memory = self.runtime.store.put_knowledge(
            "Atlas deployment window is Tuesday",
            source="test",
            entities=[atlas["id"]],
        )
        self.runtime.store.put_knowledge(
            "Boreal deployment deployment deployment window",
            source="test",
            entities=[boreal["id"]],
        )

        result = self.runtime.recall(
            "deployment window",
            entity=atlas["id"],
            limit=1,
        )

        self.assertEqual(
            [item["id"] for item in result["by_component"]["ATL"]],
            [atlas_memory["id"]],
        )

    def test_external_semantic_backend_does_not_hide_scoped_local_memory(self):
        atlas = self.runtime.store.put_entity("Atlas", entity_type="project")
        local_memory = self.runtime.store.put_knowledge(
            "Atlas deployment window is Tuesday",
            source="test",
            entities=[atlas["id"]],
        )
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Boreal.md").write_text(
                "deployment deployment deployment window",
                encoding="utf-8",
            )
            self.runtime.semantic = VaultBM25Adapter(vault)

            scoped = self.runtime.recall(
                "deployment window",
                entity=atlas["id"],
                limit=1,
            )
            unscoped = self.runtime.semantic.search("deployment window", limit=1)

        self.assertEqual(
            [item["id"] for item in scoped["by_component"]["ATL"]],
            [local_memory["id"]],
        )
        self.assertEqual(unscoped[0]["entity_scope"], "unscoped-external")

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
        self.assertEqual(
            tour["evidence"]["resumed_handoff"]["id"],
            tour["checkpoint"],
        )
        self.assertIn("Thursday", tour["updated"])


class MCPServerTest(unittest.TestCase):
    def test_entrypoint_reports_missing_optional_dependency_without_traceback(self):
        stderr = StringIO()
        error = MCPUnavailableError(
            "MCP support is optional. Install it with: pip install 'brain-ai-memory[mcp]'"
        )
        with patch(
            "brain_ai_memory.mcp_server.create_mcp_server",
            side_effect=error,
        ), redirect_stderr(stderr):
            return_code = mcp_main([])

        self.assertEqual(return_code, 2)
        self.assertIn("pip install 'brain-ai-memory[mcp]'", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

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
            self.assertIn("brain_resume", names)
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
                    "--entity",
                    "Atlas",
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
                        {"query": "What changed?"},
                    )
                    self.assertFalse(context.isError)
                    context_value = json.loads(context.content[0].text)
                    self.assertEqual(context_value["entity"]["name"], "Atlas")
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
            root = Path(tmp)
            vault = root / "vault"
            vault.mkdir()
            (vault / ".smart-env").mkdir()
            (vault / "새노트.md").write_text("장기 실행 에이전트의 메모리 생명주기", encoding="utf-8")
            outside = root / "outside.md"
            outside.write_text("메모리 생명주기 private outside note", encoding="utf-8")
            linked = vault / "linked.md"
            try:
                linked.symlink_to(outside)
            except (OSError, NotImplementedError):
                linked = None
            results = VaultBM25Adapter(vault).search("메모리 생명주기")
            self.assertEqual(results[0]["path"], "새노트.md")
            self.assertEqual(results[0]["backend"], "vault-bm25")
            self.assertEqual(results[0]["entity_scope"], "unscoped-external")
            if linked is not None:
                self.assertNotIn("linked.md", {result["path"] for result in results})
            self.assertEqual(
                VaultBM25Adapter(vault).search(
                    "메모리 생명주기",
                    entity_id="entity-atlas",
                ),
                [],
            )

    def test_smart_connections_skips_unbound_hits_for_entity_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = SmartConnectionsAdapter(
                Path(tmp),
                ["unused-because-scoped-search-is-local-only"],
            )

            results = adapter.search(
                "deployment window",
                entity_id="entity-atlas",
            )

            self.assertEqual(results, [])
            self.assertEqual(adapter.last_diagnostic["mcp"], "skipped")
            self.assertEqual(adapter.last_diagnostic["scope"], "entity-scoped")
            self.assertEqual(adapter.last_diagnostic["entity_id"], "entity-atlas")

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
    else: result={'content':[{'type':'text','text':json.dumps([{'path':'MCP.md','similarity':0.9},{'path':'../outside.md','snippet':'must not escape the vault','similarity':1.0}])}]}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}), flush=True)
""",
                encoding="utf-8",
            )
            adapter = SmartConnectionsAdapter(vault, [sys.executable, str(server)], timeout=3, merge_local=True)
            results = adapter.search("한국어 메모리 생명주기", limit=5)
            backends = " ".join(result["backend"] for result in results)
            self.assertIn("smart-connections-mcp", backends)
            self.assertIn("vault-bm25", backends)
            self.assertNotIn("../outside.md", {result["path"] for result in results})
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
