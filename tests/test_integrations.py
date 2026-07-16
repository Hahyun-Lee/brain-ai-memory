import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from brain_ai_memory.integrations import (
    lifecycle_connection_change,
    lifecycle_connection_status,
    loop_connection_change,
    loop_connection_status,
)
from brain_ai_memory.cli import doctor, emit_doctor, main as cli_main
from brain_ai_memory.runtime import BrainAIRuntime
from brain_ai_memory.workspace import (
    WorkflowConflict,
    connection_change,
    connection_status,
)


class LifecycleIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.home = self.base / "runtime"
        self.runtime = BrainAIRuntime(self.home)
        self.home = self.runtime.home
        self.runtime.store.put_entity(
            "Atlas", entity_type="project", aliases=["A"]
        )

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self) -> dict:
        result = {}
        for path in sorted(self.base.rglob("*")):
            relative = path.relative_to(self.base).as_posix()
            info = path.lstat()
            if path.is_symlink():
                result[relative] = ("link", os.readlink(path))
            elif path.is_dir():
                result[relative] = ("dir", stat.S_IMODE(info.st_mode))
            else:
                result[relative] = (
                    "file",
                    stat.S_IMODE(info.st_mode),
                    info.st_mtime_ns,
                    path.read_bytes(),
                )
        return result

    def write_unrelated_configs(self, host: str) -> tuple[Path, dict]:
        unrelated_group = {
            "matcher": "custom-only",
            "hooks": [
                {
                    "type": "command",
                    "command": "/usr/bin/printf existing-hook",
                    "timeout": 7,
                }
            ],
        }
        hook_path = (
            self.project / ".codex" / "hooks.json"
            if host == "codex"
            else self.project / ".claude" / "settings.local.json"
        )
        hook_path.parent.mkdir(parents=True)
        hook_config = {
            "hooks": {"SessionStart": [unrelated_group]},
            "unrelated": {"secret": "TOP-SECRET-MUST-NOT-LEAK"},
        }
        hook_path.write_text(
            json.dumps(hook_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if host == "codex":
            mcp_path = self.project / ".codex" / "config.toml"
            mcp_path.write_text(
                'model = "existing-model"\n\n'
                '[mcp_servers.existing]\n'
                'command = "/usr/bin/printf"\n'
                'args = ["existing-server"]\n',
                encoding="utf-8",
            )
        else:
            mcp_path = self.project / ".mcp.json"
            mcp_path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "existing": {
                                "command": "/usr/bin/printf",
                                "args": ["existing-server"],
                            }
                        },
                        "unrelated": {"secret": "TOP-SECRET-MUST-NOT-LEAK"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return hook_path, unrelated_group

    @staticmethod
    def managed_group(config: dict, event: str, binding: Path) -> dict:
        marker = str(binding)
        groups = [
            group
            for group in config.get("hooks", {}).get(event, [])
            if marker in json.dumps(group, ensure_ascii=False)
        ]
        if len(groups) != 1:
            raise AssertionError(
                f"expected one managed {event} group for {binding}, got {len(groups)}"
            )
        return groups[0]

    def test_loop_preview_is_pure_and_redacts_unrelated_configuration(self):
        self.write_unrelated_configs("codex")
        before = self.snapshot()

        preview = loop_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            scope="project",
            project_root=self.project,
            apply=False,
        )

        self.assertEqual(preview["status"], "preview")
        self.assertTrue(preview["changed"])
        self.assertFalse(preview["applied"])
        self.assertIn("--mode loop", preview["next"])
        self.assertNotIn("TOP-SECRET-MUST-NOT-LEAK", preview["diff"])
        self.assertEqual(self.snapshot(), before)

        missing = self.base / "missing-project"
        with self.assertRaisesRegex(ValueError, "project root does not exist"):
            loop_connection_change(
                self.home,
                "codex",
                entity="Atlas",
                project_root=missing,
            )

    def test_autonomous_loop_rejects_user_scope_without_mutation(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "project scope only"):
            loop_connection_change(
                self.home,
                "codex",
                entity="Atlas",
                scope="user",
                project_root=self.project,
                apply=True,
            )
        self.assertEqual(self.snapshot(), before)

    def test_loop_connection_accepts_entity_alias_without_rewriting_binding(self):
        applied = loop_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        binding = Path(applied["lifecycle"]["binding"])
        before = binding.read_bytes()

        status = loop_connection_status(
            self.home,
            "codex",
            entity="A",
            scope="project",
            project_root=self.project,
        )
        self.assertTrue(status["configured"])
        preview = loop_connection_change(
            self.home,
            "codex",
            entity="A",
            project_root=self.project,
        )
        self.assertFalse(preview["changed"])
        self.assertEqual(binding.read_bytes(), before)

        disconnected = loop_connection_change(
            self.home,
            "codex",
            entity="A",
            project_root=self.project,
            disconnect=True,
            apply=True,
        )
        self.assertEqual(disconnected["status"], "disconnected")

    def test_doctor_filters_quarantine_by_selected_entity_and_loop_apply_fails_closed(self):
        self.runtime.store.put_entity("Boreal", entity_type="project")
        legacy_id = "rule_v05_atlas_only"
        with self.runtime.store.connect() as conn:
            conn.execute(
                """INSERT INTO rules
                (id, pattern, effect, reason, source, enabled, created_at)
                VALUES (?, ?, 'block', ?, 'v0.5', 1, ?)""",
                (
                    legacy_id,
                    r"^deploy\s+atlas\s+now$",
                    "Atlas deploy requires approval",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
        self.runtime.store.link_entity("rule", legacy_id, "Atlas")
        upgraded = BrainAIRuntime(self.home)

        atlas_checks = doctor(upgraded, entity="Atlas")
        boreal_checks = doctor(upgraded, entity="Boreal")
        global_checks = doctor(upgraded)
        self.assertEqual(atlas_checks["quarantined_rule_ids"], [legacy_id])
        self.assertFalse(atlas_checks["ready"])
        self.assertEqual(boreal_checks["quarantined_rule_ids"], [])
        self.assertTrue(boreal_checks["ready"])
        self.assertEqual(global_checks["quarantined_rule_ids"], [])

        before = self.snapshot()
        with self.assertRaisesRegex(
            ValueError, "cannot enable autonomous loop.*rule list"
        ):
            loop_connection_change(
                self.home,
                "codex",
                entity="A",
                project_root=self.project,
                apply=True,
            )
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.project / ".codex" / "config.toml").exists())
        self.assertFalse((self.project / ".codex" / "hooks.json").exists())

    def test_doctor_surfaces_v05_project_connection_migration_command(self):
        connected = connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        config_path = Path(connected["path"])
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                '"--locked-entity"', '"--entity"'
            ),
            encoding="utf-8",
        )
        status = connection_status(
            self.home,
            "claude-code",
            project_root=self.project,
            entity="A",
        )
        self.assertTrue(status["migration_required"])

        with mock.patch(
            "brain_ai_memory.cli.importlib.util.find_spec", return_value=object()
        ):
            checks = doctor(
                self.runtime,
                "claude-code",
                scope="project",
                project_root=self.project,
                entity="A",
                mode="tools",
            )
        self.assertTrue(checks["migration_required"])
        self.assertIn(status["migration_command"], checks["next_action"])
        self.assertTrue(checks["next_action"].endswith("--apply"))

    def test_codex_and_claude_apply_status_and_disconnect_preserve_user_config(self):
        cases = {
            "codex": {
                "events": {
                    "SessionStart",
                    "UserPromptSubmit",
                    "PreToolUse",
                    "PostToolUse",
                    "PreCompact",
                    "Stop",
                },
                "session_end": "unsupported",
            },
            "claude-code": {
                "events": {
                    "SessionStart",
                    "UserPromptSubmit",
                    "PreToolUse",
                    "PostToolUse",
                    "PreCompact",
                    "Stop",
                    "SessionEnd",
                },
                "session_end": "configured",
            },
        }
        for host, expected in cases.items():
            with self.subTest(host=host):
                project = self.project / host
                project.mkdir()
                original_project = self.project
                self.project = project
                try:
                    hook_path, unrelated_group = self.write_unrelated_configs(host)
                    applied = loop_connection_change(
                        self.home,
                        host,
                        entity="Atlas",
                        scope="project",
                        project_root=project,
                        apply=True,
                    )
                    binding = Path(applied["lifecycle"]["binding"])
                    self.assertEqual(applied["status"], "configured")
                    self.assertTrue(binding.is_file())
                    if os.name == "posix":
                        self.assertEqual(stat.S_IMODE(binding.stat().st_mode), 0o600)

                    config = json.loads(hook_path.read_text(encoding="utf-8"))
                    self.assertEqual(config["unrelated"]["secret"], "TOP-SECRET-MUST-NOT-LEAK")
                    self.assertIn(unrelated_group, config["hooks"]["SessionStart"])
                    managed_events = {
                        event
                        for event in config["hooks"]
                        if any(
                            str(binding) in json.dumps(group, ensure_ascii=False)
                            for group in config["hooks"][event]
                        )
                    }
                    self.assertEqual(managed_events, expected["events"])

                    for event in expected["events"]:
                        group = self.managed_group(config, event, binding)
                        self.assertEqual(len(group["hooks"]), 1)
                        handler = group["hooks"][0]
                        self.assertEqual(handler["type"], "command")
                        self.assertGreater(handler["timeout"], 5)
                        if host == "codex":
                            self.assertIn("brain_ai_memory.hook_cli", handler["command"])
                            self.assertIn(str(binding), handler["command"])
                            self.assertNotIn("args", handler)
                        else:
                            self.assertEqual(handler["command"], os.path.abspath(sys.executable))
                            self.assertEqual(
                                handler["args"],
                                [
                                    "-m",
                                    "brain_ai_memory.hook_cli",
                                    "--binding",
                                    str(binding),
                                ],
                            )

                    status = loop_connection_status(
                        self.home,
                        host,
                        entity="Atlas",
                        scope="project",
                        project_root=project,
                    )
                    self.assertTrue(status["configured"])
                    self.assertFalse(status["active"])
                    self.assertEqual(status["lifecycle"]["configured_entity"], "Atlas")
                    self.assertEqual(
                        status["lifecycle"]["session_end_support"],
                        expected["session_end"],
                    )
                    self.assertIsNone(status["lifecycle"]["error"])

                    disconnected = loop_connection_change(
                        self.home,
                        host,
                        entity="Atlas",
                        scope="project",
                        project_root=project,
                        disconnect=True,
                        apply=True,
                    )
                    self.assertEqual(disconnected["status"], "disconnected")
                    self.assertFalse(binding.exists())

                    remaining_hooks = json.loads(hook_path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        remaining_hooks,
                        {
                            "hooks": {"SessionStart": [unrelated_group]},
                            "unrelated": {"secret": "TOP-SECRET-MUST-NOT-LEAK"},
                        },
                    )
                    if host == "codex":
                        mcp_config = tomllib.loads(
                            (project / ".codex" / "config.toml").read_text(encoding="utf-8")
                        )
                        self.assertEqual(mcp_config["model"], "existing-model")
                        self.assertEqual(
                            mcp_config["mcp_servers"]["existing"]["args"],
                            ["existing-server"],
                        )
                        self.assertNotIn("brain-ai-memory", mcp_config["mcp_servers"])
                    else:
                        mcp_config = json.loads(
                            (project / ".mcp.json").read_text(encoding="utf-8")
                        )
                        self.assertEqual(
                            mcp_config["mcpServers"],
                            {
                                "existing": {
                                    "command": "/usr/bin/printf",
                                    "args": ["existing-server"],
                                }
                            },
                        )
                        self.assertEqual(
                            mcp_config["unrelated"]["secret"],
                            "TOP-SECRET-MUST-NOT-LEAK",
                        )
                    final_status = loop_connection_status(
                        self.home,
                        host,
                        entity="Atlas",
                        scope="project",
                        project_root=project,
                    )
                    self.assertFalse(final_status["configured"])
                    self.assertFalse(final_status["active"])
                finally:
                    self.project = original_project

    def test_modified_managed_hook_is_not_removed_or_replaced(self):
        applied = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        hook_path = Path(applied["hook_config"])
        binding = Path(applied["binding"])
        config = json.loads(hook_path.read_text(encoding="utf-8"))
        group = self.managed_group(config, "SessionStart", binding)
        group["hooks"][0]["timeout"] = 99
        hook_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        tampered = hook_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "modified"):
            lifecycle_connection_change(
                self.home,
                "codex",
                entity="Atlas",
                project_root=self.project,
                disconnect=True,
                apply=True,
            )

        self.assertEqual(hook_path.read_bytes(), tampered)
        self.assertTrue(binding.is_file())

    def test_reapply_is_idempotent_and_clean_disconnect_removes_created_files(self):
        applied = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        hook_path = Path(applied["hook_config"])
        binding = Path(applied["binding"])
        before = (hook_path.read_bytes(), binding.read_bytes())

        preview = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
        )
        self.assertFalse(preview["changed"])
        self.assertEqual((hook_path.read_bytes(), binding.read_bytes()), before)

        lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            disconnect=True,
            apply=True,
        )
        self.assertFalse(hook_path.exists())
        self.assertFalse(binding.exists())

        clean_project = self.base / "clean-disconnect"
        clean_project.mkdir()
        clean = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=clean_project,
            disconnect=True,
        )
        self.assertFalse(clean["changed"])
        self.assertFalse((clean_project / ".codex" / "hooks.json").exists())

    @unittest.skipUnless(os.name == "posix", "POSIX permission modes are required")
    def test_reapply_repairs_binding_permissions(self):
        applied = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        binding = Path(applied["binding"])
        binding.chmod(0o644)
        broken = lifecycle_connection_status(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
        )
        self.assertFalse(broken["configured"])
        self.assertIn("0600", broken["error"])

        repaired = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        self.assertTrue(repaired["changed"])
        self.assertEqual(stat.S_IMODE(binding.stat().st_mode), 0o600)
        self.assertTrue(
            lifecycle_connection_status(
                self.home,
                "codex",
                entity="Atlas",
                project_root=self.project,
            )["configured"]
        )

    def test_missing_event_hook_is_detected_even_when_handler_digest_is_shared(self):
        applied = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        hook_path = Path(applied["hook_config"])
        config = json.loads(hook_path.read_text(encoding="utf-8"))
        config["hooks"].pop("Stop")
        hook_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing or modified"):
            lifecycle_connection_change(
                self.home,
                "codex",
                entity="Atlas",
                project_root=self.project,
                disconnect=True,
            )

    def test_lifecycle_failure_restores_preexisting_mcp_config_byte_for_byte(self):
        connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        mcp_path = self.project / ".codex" / "config.toml"
        # Simulate the valid, older default-entity form that loop setup upgrades.
        old_text = mcp_path.read_text(encoding="utf-8").replace(
            '"--locked-entity"', '"--entity"'
        )
        mcp_path.write_text(old_text, encoding="utf-8")
        original = mcp_path.read_bytes()

        real_lifecycle = lifecycle_connection_change

        def fail_apply(*args, **kwargs):
            if kwargs.get("apply"):
                raise RuntimeError("synthetic lifecycle failure")
            return real_lifecycle(*args, **kwargs)

        with mock.patch(
            "brain_ai_memory.integrations.lifecycle_connection_change",
            side_effect=fail_apply,
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic lifecycle failure"):
                loop_connection_change(
                    self.home,
                    "codex",
                    entity="Atlas",
                    project_root=self.project,
                    apply=True,
                )

        self.assertEqual(mcp_path.read_bytes(), original)

    def test_concurrent_mcp_edit_is_not_clobbered_by_lifecycle_rollback(self):
        mcp_path = self.project / ".codex" / "config.toml"
        real_lifecycle = lifecycle_connection_change

        def edit_then_fail(*args, **kwargs):
            if kwargs.get("apply"):
                with mcp_path.open("a", encoding="utf-8") as handle:
                    handle.write('\nmodel = "concurrent-user-edit"\n')
                raise RuntimeError("synthetic lifecycle failure after concurrent edit")
            return real_lifecycle(*args, **kwargs)

        with mock.patch(
            "brain_ai_memory.integrations.lifecycle_connection_change",
            side_effect=edit_then_fail,
        ):
            with self.assertRaisesRegex(WorkflowConflict, "could not be restored"):
                loop_connection_change(
                    self.home,
                    "codex",
                    entity="Atlas",
                    project_root=self.project,
                    apply=True,
                )

        self.assertIn("concurrent-user-edit", mcp_path.read_text(encoding="utf-8"))

    def test_loop_disconnect_removes_only_mcp_files_it_created(self):
        for host in ("codex", "claude-code"):
            with self.subTest(host=host, origin="created"):
                project = self.base / f"clean-{host}"
                project.mkdir()
                applied = loop_connection_change(
                    self.home,
                    host,
                    entity="Atlas",
                    project_root=project,
                    apply=True,
                )
                config_path = Path(applied["mcp"]["path"])
                self.assertTrue(config_path.is_file())
                loop_connection_change(
                    self.home,
                    host,
                    entity="Atlas",
                    project_root=project,
                    disconnect=True,
                    apply=True,
                )
                self.assertFalse(config_path.exists())

            with self.subTest(host=host, origin="preexisting-empty"):
                project = self.base / f"preexisting-{host}"
                project.mkdir()
                config_path = (
                    project / ".codex" / "config.toml"
                    if host == "codex"
                    else project / ".mcp.json"
                )
                config_path.parent.mkdir(parents=True, exist_ok=True)
                original = b"" if host == "codex" else b"{}\n"
                config_path.write_bytes(original)
                loop_connection_change(
                    self.home,
                    host,
                    entity="Atlas",
                    project_root=project,
                    apply=True,
                )
                loop_connection_change(
                    self.home,
                    host,
                    entity="Atlas",
                    project_root=project,
                    disconnect=True,
                    apply=True,
                )
                self.assertTrue(config_path.is_file())
                self.assertEqual(config_path.read_bytes(), original)

            with self.subTest(host=host, origin="created-then-deleted"):
                project = self.base / f"deleted-{host}"
                project.mkdir()
                applied = loop_connection_change(
                    self.home,
                    host,
                    entity="Atlas",
                    project_root=project,
                    apply=True,
                )
                config_path = Path(applied["mcp"]["path"])
                config_path.unlink()
                loop_connection_change(
                    self.home,
                    host,
                    entity="",
                    project_root=project,
                    disconnect=True,
                    apply=True,
                )
                self.assertFalse(config_path.exists())
                status = loop_connection_status(
                    self.home,
                    host,
                    entity="Atlas",
                    scope="project",
                    project_root=project,
                )
                self.assertFalse(status["configured"])

    @unittest.skipUnless(os.name == "posix", "POSIX permission modes are required")
    def test_hook_cli_rejects_a_binding_readable_by_other_users(self):
        applied = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        binding = Path(applied["binding"])
        binding.chmod(0o644)
        before = lifecycle_connection_status(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
        )["observed_events"]

        output = self.run_hook(
            binding,
            {
                "hook_event_name": "SessionStart",
                "session_id": "permission-test",
                "cwd": str(self.project),
                "source": "startup",
            },
        )

        message = output["systemMessage"]
        self.assertIn("loop unavailable", message)
        self.assertIn("error ref:", message)
        self.assertNotIn("must not be accessible", message)
        after = lifecycle_connection_status(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
        )["observed_events"]
        self.assertEqual(after, before)

    def run_hook(self, binding: Path, payload: dict) -> dict:
        environment = os.environ.copy()
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "brain_ai_memory.hook_cli",
                "--binding",
                str(binding),
            ],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            env=environment,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        return json.loads(completed.stdout)

    def test_synthetic_codex_hook_lifecycle_becomes_active_and_resumes_handoff(self):
        applied = lifecycle_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        binding = Path(applied["binding"])
        base = {"session_id": "synthetic-1", "cwd": str(self.project)}
        payloads = [
            {**base, "hook_event_name": "SessionStart", "source": "startup"},
            {
                **base,
                "hook_event_name": "UserPromptSubmit",
                "turn_id": "turn-1",
                "prompt": "Continue the Atlas work",
            },
            {
                **base,
                "hook_event_name": "PostToolUse",
                "turn_id": "turn-1",
                "tool_name": "apply_patch",
                "tool_use_id": "patch-1",
                "tool_input": {
                    "command": (
                        "*** Begin Patch\n"
                        "*** Add File: notes.txt\n"
                        "+durable change\n"
                        "*** End Patch"
                    )
                },
                "tool_response": {"ok": True},
            },
            {
                **base,
                "hook_event_name": "Stop",
                "turn_id": "turn-1",
                "last_assistant_message": "done",
            },
        ]
        for payload in payloads:
            output = self.run_hook(binding, payload)
            self.assertNotIn("loop unavailable", output.get("systemMessage", ""))

        status = lifecycle_connection_status(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
        )
        self.assertTrue(status["configured"])
        self.assertTrue(status["active"])
        self.assertEqual(
            {event["event_name"] for event in status["observed_events"]},
            {"SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"},
        )
        checkpoints = BrainAIRuntime(self.home).store.checkpoints()
        self.assertEqual(len(checkpoints), 1)
        checkpoint_id = checkpoints[0]["id"]

        resumed = self.run_hook(
            binding,
            {
                "hook_event_name": "SessionStart",
                "session_id": "synthetic-2",
                "cwd": str(self.project),
                "source": "startup",
            },
        )
        context = resumed["hookSpecificOutput"]["additionalContext"]
        self.assertIn(checkpoint_id, context)
        self.assertIn("notes.txt", context)

    def test_doctor_human_output_explains_configured_but_not_active(self):
        loop_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "brain_ai_memory.cli",
                "--home",
                str(self.home),
                "doctor",
                "--host",
                "codex",
                "--entity",
                "Atlas",
                "--mode",
                "loop",
                "--project-root",
                str(self.project),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "Automatic session memory: configured=yes, active=no",
            completed.stdout,
        )
        self.assertIn("review the project hooks with /hooks", completed.stdout)
        self.assertIn("Agent connection support: installed", completed.stdout)
        self.assertNotIn('"configured"', completed.stdout)

    def test_connect_apply_and_doctor_explain_missing_optional_support(self):
        loop_connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=self.project,
            apply=True,
        )
        before = self.snapshot()
        stderr = io.StringIO()
        with mock.patch(
            "brain_ai_memory.cli.importlib.util.find_spec", return_value=None
        ), contextlib.redirect_stderr(stderr):
            code = cli_main(
                [
                    "--home",
                    str(self.home),
                    "connect",
                    "codex",
                    "--entity",
                    "Atlas",
                    "--mode",
                    "loop",
                    "--project-root",
                    str(self.project),
                    "--apply",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("python -m pip install '.[mcp]'", stderr.getvalue())
        self.assertEqual(self.snapshot(), before)

        with mock.patch(
            "brain_ai_memory.cli.importlib.util.find_spec", return_value=None
        ):
            checks = doctor(
                self.runtime,
                "codex",
                scope="project",
                project_root=self.project,
                entity="Atlas",
                mode="loop",
            )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            emit_doctor(checks, False)
        self.assertIn("Agent connection support: missing", stdout.getvalue())
        self.assertIn("python -m pip install '.[mcp]'", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
