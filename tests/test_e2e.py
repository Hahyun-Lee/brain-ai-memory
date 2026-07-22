from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import brain_ai_memory

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


class PackagedWorkflowEndToEndTest(unittest.TestCase):
    """Exercise the public adoption and MCP persistence path as one workflow."""

    @staticmethod
    def package_environment() -> dict[str, str]:
        environment = dict(os.environ)
        package_parent = str(Path(brain_ai_memory.__file__).resolve().parent.parent)
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            package_parent if not existing else package_parent + os.pathsep + existing
        )
        return environment

    def run_cli(self, root: Path, home: Path, *arguments: str) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "brain_ai_memory.cli",
                "--home",
                str(home),
                *arguments,
                "--json",
            ],
            cwd=root,
            env=self.package_environment(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_adopt_generated_mcp_config_restart_and_resume(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self.skipTest("optional MCP dependency is not installed")

        async def call_json(session, name: str, arguments: dict) -> dict:
            result = await session.call_tool(name, arguments)
            self.assertFalse(result.isError, result.content)
            self.assertTrue(result.content)
            return json.loads(result.content[0].text)

        async def first_process(params):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    initial = await call_json(session, "brain_resume", {})
                    self.assertEqual(initial["status"], "not_found")

                    imported = await call_json(
                        session,
                        "brain_context",
                        {"query": "Atlas release day Thursday"},
                    )
                    self.assertIn("Atlas release day is Thursday", json.dumps(imported))

                    await call_json(
                        session,
                        "brain_remember",
                        {
                            "kind": "semantic",
                            "text": "Atlas production window is 09:30 UTC.",
                        },
                    )
                    await call_json(
                        session,
                        "brain_remember",
                        {
                            "kind": "state",
                            "key": "open_reviews",
                            "value_json": "3",
                        },
                    )
                    await call_json(
                        session,
                        "brain_remember",
                        {
                            "kind": "rule",
                            "text": "Production deployment requires release approval.",
                            "pattern": "production deploy",
                            "effect": "block",
                        },
                    )
                    cross_write = await session.call_tool(
                        "brain_remember",
                        {
                            "kind": "semantic",
                            "entity": "Boreal",
                            "text": "This write must be rejected.",
                        },
                    )
                    self.assertTrue(cross_write.isError)

                    atlas = await call_json(
                        session,
                        "brain_context",
                        {"query": "cobalt rollout"},
                    )
                    self.assertNotIn("Boreal uses a cobalt rollout", json.dumps(atlas))
                    cross_read = await session.call_tool(
                        "brain_context",
                        {"query": "cobalt rollout", "entity": "Boreal"},
                    )
                    self.assertTrue(cross_read.isError)

                    verdict = await call_json(
                        session,
                        "brain_check_action",
                        {"action": "production deploy now"},
                    )
                    self.assertFalse(verdict["allowed"])

                    checkpoint = await call_json(
                        session,
                        "brain_checkpoint",
                        {
                            "summary": "Atlas release review completed.",
                            "next_actions": ["Run the approved staging deploy."],
                        },
                    )
                    return checkpoint["id"]

        async def second_process(params, checkpoint_id: str):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    resumed = await call_json(session, "brain_resume", {})
                    self.assertEqual(resumed["id"], checkpoint_id)
                    self.assertEqual(
                        resumed["next_actions"],
                        ["Run the approved staging deploy."],
                    )

                    semantic = await call_json(
                        session,
                        "brain_context",
                        {"query": "production window 09:30 UTC"},
                    )
                    self.assertIn("Atlas production window is 09:30 UTC", json.dumps(semantic))
                    self.assertNotIn("Boreal uses a cobalt rollout", json.dumps(semantic))

                    state = await call_json(
                        session,
                        "brain_context",
                        {"query": "open_reviews exact state"},
                    )
                    self.assertIn("IPS", state["route"])
                    self.assertEqual(
                        state["memory"]["IPS"][0]["key"],
                        "open_reviews",
                    )
                    self.assertEqual(state["memory"]["IPS"][0]["value"], 3)

                    verdict = await call_json(
                        session,
                        "brain_check_action",
                        {"action": "production deploy now"},
                    )
                    self.assertFalse(verdict["allowed"])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / ".brain-ai"
            source = root / "MEMORY.md"
            original = (
                "# Current facts\n\n"
                "- Atlas release day is Thursday.\n"
                "- Atlas API contract is version seven.\n"
            )
            source.write_text(original, encoding="utf-8")

            audit = self.run_cli(
                root,
                home,
                "audit",
                str(source),
                "--entity",
                "Atlas",
            )
            review_result = self.run_cli(
                root,
                home,
                "review",
                audit["id"],
                "--approve-ready",
            )
            review = review_result["review"]
            self.assertIsNotNone(review)
            receipt = self.run_cli(
                root,
                home,
                "apply",
                review["id"],
                "--yes",
            )
            self.assertEqual(receipt["status"], "applied")
            self.assertEqual(source.read_text(encoding="utf-8"), original)

            runtime = brain_ai_memory.BrainAIRuntime(home)
            boreal = runtime.store.put_entity("Boreal", entity_type="project")
            runtime.store.put_knowledge(
                "Boreal uses a cobalt rollout.",
                entities=[boreal["id"]],
            )

            connection = self.run_cli(
                root,
                home,
                "connect",
                "codex",
                "--entity",
                "Atlas",
                "--project-root",
                str(root),
                "--apply",
            )
            self.assertEqual(connection["status"], "connected")
            self.assertTrue(connection["applied"])

            config = tomllib.loads((root / ".codex" / "config.toml").read_text())
            entry = config["mcp_servers"]["brain-ai-memory"]
            self.assertEqual(entry["command"], os.path.abspath(sys.executable))
            self.assertEqual(entry["args"][4], "--locked-entity")
            params = StdioServerParameters(
                command=entry["command"],
                args=entry["args"],
                env=self.package_environment(),
            )

            checkpoint_id = asyncio.run(first_process(params))
            asyncio.run(second_process(params, checkpoint_id))


if __name__ == "__main__":
    unittest.main()
