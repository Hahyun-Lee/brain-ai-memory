from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

import brain_ai_memory.workspace as workspace_module
from brain_ai_memory.cli import main as cli_main
from brain_ai_memory.runtime import BrainAIRuntime
from brain_ai_memory.workspace import (
    MAX_SOURCE_BYTES,
    WorkflowConflict,
    apply_review,
    build_audit,
    build_review,
    connection_change,
    connection_status,
    discover_memory_file,
    inspect_source_freshness,
    rollback_batch,
)


class WorkspaceWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / ".brain-ai"
        self.source = self.root / "MEMORY.md"

    def tearDown(self):
        self.temp.cleanup()

    def write_memory(self, text: str) -> bytes:
        payload = text.encode("utf-8")
        self.source.write_bytes(payload)
        return payload

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = cli_main(list(arguments))
        finally:
            os.chdir(previous)
        return status, stdout.getvalue(), stderr.getvalue()

    def apply_ready_memory(self, text: str) -> tuple[BrainAIRuntime, dict]:
        self.write_memory(text)
        runtime = BrainAIRuntime(self.home)
        audit = build_audit(self.source, entity="Atlas", root=self.root)
        review = build_review(audit, runtime.store, approve_ready=True)
        receipt = apply_review(self.home, runtime.store, review, audit)
        return runtime, receipt

    def test_source_freshness_creates_review_audit_and_marks_removed_fragment_stale(self):
        runtime, receipt = self.apply_ready_memory(
            "# Facts\n\n- Atlas deploys on Friday.\n"
        )
        semantic_id = receipt["results"][0]["target_id"]

        current = inspect_source_freshness(
            self.home,
            runtime.store,
            entity="Atlas",
            root=self.root,
        )
        self.assertEqual(current["attention_count"], 0)
        self.assertEqual(current["sources"][0]["status"], "current")

        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        changed = inspect_source_freshness(
            self.home,
            runtime.store,
            entity="Atlas",
            root=self.root,
        )
        source = changed["sources"][0]
        self.assertEqual(changed["attention_count"], 1)
        self.assertEqual(source["status"], "review-required")
        self.assertEqual(source["stale_targets"]["semantic"], [semantic_id])
        self.assertEqual(source["candidate_count"], 1)
        self.assertTrue(source["audit_id"].startswith("audit_"))
        self.assertTrue(
            (self.home / "workflows" / "audits" / f"{source['audit_id']}.json").is_file()
        )

    def test_source_freshness_ignores_non_memory_comment_only_change(self):
        runtime, _ = self.apply_ready_memory(
            "# Facts\n\n- Atlas deploys on Friday.\n"
        )
        self.write_memory(
            "# Facts\n\n- Atlas deploys on Friday.\n\n<!-- formatting note -->\n"
        )

        result = inspect_source_freshness(
            self.home,
            runtime.store,
            entity="Atlas",
            root=self.root,
        )

        self.assertEqual(result["attention_count"], 0)
        self.assertEqual(result["sources"][0]["status"], "current-content")
        self.assertEqual(result["sources"][0]["candidate_count"], 0)
        self.assertTrue(
            all(not values for values in result["sources"][0]["stale_targets"].values())
        )

    def test_source_freshness_rejects_missing_root_with_value_error(self):
        runtime = BrainAIRuntime(self.home)
        runtime.store.put_entity("Atlas", entity_type="project")

        with self.assertRaisesRegex(
            ValueError,
            "source freshness root must be a directory",
        ):
            inspect_source_freshness(
                self.home,
                runtime.store,
                entity="Atlas",
                root=self.root / "missing-project",
            )

    def test_top_level_version_is_pure(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as stopped:
                    cli_main(["--version"])
        finally:
            os.chdir(previous)

        self.assertEqual(stopped.exception.code, 0)
        self.assertRegex(stdout.getvalue(), r"^brain-ai \d+\.\d+\.\d+\n$")
        self.assertEqual(stderr.getvalue(), "")
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_audit_no_save_is_pure_and_does_not_create_runtime_home(self):
        original = self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        before = self.source.stat()

        status, stdout, stderr = self.run_cli(
            "audit",
            str(self.source),
            "--entity",
            "Atlas",
            "--no-save",
            "--json",
        )

        self.assertEqual(status, 0, stderr)
        result = json.loads(stdout)
        self.assertIsNone(result["plan_path"])
        self.assertFalse(result["claims"]["source_changed"])
        self.assertFalse(result["claims"]["memory_store_changed"])
        self.assertEqual(self.source.read_bytes(), original)
        after = self.source.stat()
        self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(stat.S_IMODE(after.st_mode), stat.S_IMODE(before.st_mode))
        self.assertFalse(self.home.exists())
        self.assertEqual(
            {path.relative_to(self.root).as_posix() for path in self.root.rglob("*")},
            {"MEMORY.md"},
        )

    @unittest.skipUnless(os.name == "posix", "POSIX permission modes are required")
    def test_fresh_runtime_and_recreated_event_log_are_owner_only(self):
        previous_umask = os.umask(0)
        try:
            runtime = BrainAIRuntime(self.home)
        finally:
            os.umask(previous_umask)

        self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
        private_files = (
            runtime.store.db_path,
            runtime.store.events_path,
            runtime.store.audit_path,
            runtime.store.checkpoints_path,
            self.home / "config.json",
            self.home / ".gitignore",
        )
        for path in private_files:
            with self.subTest(path=path.name):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

        runtime.store.events_path.unlink()
        previous_umask = os.umask(0)
        try:
            runtime.store.append_event("recreated privately", source="test")
        finally:
            os.umask(previous_umask)
        self.assertEqual(stat.S_IMODE(runtime.store.events_path.stat().st_mode), 0o600)

        self.home.chmod(0o755)
        status, stdout, stderr = self.run_cli(
            "--home",
            str(self.home),
            "doctor",
            "--json",
        )
        self.assertEqual(status, 0, stderr)
        diagnosis = json.loads(stdout)
        self.assertFalse(diagnosis["private_permissions"])
        self.assertFalse(diagnosis["ready"])
        self.assertTrue(
            any(str(self.home) in warning for warning in diagnosis["permission_warnings"])
        )
        self.home.chmod(0o700)

        (self.home / ".gitignore").write_text("# not a catch-all\n", encoding="utf-8")
        (self.home / ".gitignore").chmod(0o600)
        status, stdout, stderr = self.run_cli(
            "--home", str(self.home), "doctor", "--json"
        )
        self.assertEqual(status, 0, stderr)
        diagnosis = json.loads(stdout)
        self.assertFalse(diagnosis["runtime_home_git_ignored"])
        self.assertFalse(diagnosis["ready"])

        outside = self.root / "outside-home"
        outside.mkdir()
        linked_home = self.root / "linked-home"
        try:
            linked_home.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            linked_home = None
        if linked_home is not None:
            with self.assertRaisesRegex(ValueError, "symbolic-link runtime directory"):
                BrainAIRuntime(linked_home)
            with mock.patch.dict(os.environ, {"BRAIN_AI_HOME": str(linked_home)}):
                with self.assertRaisesRegex(
                    ValueError, "symbolic-link runtime directory"
                ):
                    BrainAIRuntime()
            self.assertEqual(list(outside.iterdir()), [])

        fifo_home = self.root / "fifo-home"
        fifo_home.mkdir(mode=0o700)
        fifo_config = fifo_home / "config.json"
        os.mkfifo(fifo_config, mode=0o600)
        with self.assertRaisesRegex(ValueError, "non-regular runtime file"):
            BrainAIRuntime(fifo_home)

    def test_legacy_import_ledger_migrates_before_dependency_schema_is_created(self):
        self.home.mkdir()
        with sqlite3.connect(self.home / "state.sqlite3") as conn:
            conn.execute(
                """CREATE TABLE knowledge (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                content_hash TEXT NOT NULL UNIQUE,
                supersedes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
                )"""
            )
            conn.executemany(
                """INSERT INTO knowledge
                (id, text, source, tags_json, status, content_hash, supersedes,
                 created_at, updated_at)
                VALUES (?, ?, 'legacy', '[]', ?, ?, ?, ?, ?)""",
                [
                    (
                        "mem_legacy_old",
                        "Legacy release day is Friday",
                        "superseded",
                        "a" * 64,
                        None,
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-02T00:00:00+00:00",
                    ),
                    (
                        "mem_legacy_new",
                        "Legacy release day is Thursday",
                        "active",
                        "b" * 64,
                        "mem_legacy_old",
                        "2026-01-02T00:00:00+00:00",
                        "2026-01-03T00:00:00+00:00",
                    ),
                    (
                        "mem_legacy_conflict",
                        "Legacy release day is Wednesday",
                        "archived",
                        "c" * 64,
                        "mem_legacy_old",
                        "2026-01-03T00:00:00+00:00",
                        "2026-01-04T00:00:00+00:00",
                    ),
                ],
            )
            conn.execute(
                """CREATE TABLE import_batches (
                id TEXT PRIMARY KEY,
                review_id TEXT NOT NULL UNIQUE,
                audit_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                before_revision TEXT NOT NULL,
                after_revision TEXT,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                rolled_back_at TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE import_ledger (
                fingerprint TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                fragment_sha256 TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                memory_type TEXT NOT NULL,
                target_id TEXT,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
                )"""
            )

        runtime = BrainAIRuntime(self.home)
        with runtime.store.connect() as conn:
            ledger_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(import_ledger)")
            }
            dependencies = {
                row["table"]
                for row in conn.execute(
                    "PRAGMA foreign_key_list(import_dependencies)"
                )
            }
            batch_indexes = {
                row["name"]: dict(row)
                for row in conn.execute("PRAGMA index_list(import_batches)")
            }
            foreign_key_violations = list(conn.execute("PRAGMA foreign_key_check"))
            lineage_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("knowledge_supersessions",),
            ).fetchone()
        self.assertIn("entry_fingerprint", ledger_columns)
        self.assertEqual(dependencies, {"import_batches", "import_ledger"})
        self.assertIn("idx_import_batches_current_review", batch_indexes)
        self.assertFalse(
            any(row["origin"] == "u" for row in batch_indexes.values())
        )
        self.assertEqual(foreign_key_violations, [])
        self.assertIsNotNone(lineage_table)
        replacement = runtime.store.get_knowledge("mem_legacy_new")
        self.assertEqual(replacement["supersedes_ids"], ["mem_legacy_old"])
        migrated_edges = runtime.store.knowledge_supersessions(
            old_id="mem_legacy_old",
            include_inactive=True,
        )
        self.assertEqual(
            {edge["status"] for edge in migrated_edges},
            {"active", "legacy_conflict"},
        )
        self.assertTrue(
            all(
                edge["source"]
                == "migration:v0.5:legacy-knowledge.supersedes"
                for edge in migrated_edges
            )
        )
        BrainAIRuntime(self.home)
        self.assertEqual(
            len(
                runtime.store.knowledge_supersessions(
                    old_id="mem_legacy_old", include_inactive=True
                )
            ),
            2,
        )

    def test_unsafe_sources_are_rejected_without_creating_runtime_home(self):
        cases = {
            "invalid-utf8.md": b"# Facts\n\n- invalid: \xff\n",
            "nul.md": b"# Facts\n\n- hidden\x00value\n",
            "oversize.md": b"x" * (MAX_SOURCE_BYTES + 1),
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                source = self.root / name
                source.write_bytes(payload)
                status, stdout, stderr = self.run_cli(
                    "audit",
                    str(source),
                    "--entity",
                    "Atlas",
                    "--no-save",
                    "--json",
                )
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertIn("brain-ai:", stderr)
                self.assertEqual(source.read_bytes(), payload)
                self.assertFalse(self.home.exists())

        target = self.root / "symlink-target.md"
        target_payload = b"# Facts\n\n- target remains unchanged\n"
        target.write_bytes(target_payload)
        link = self.root / "symlink-memory.md"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable on this platform")
        status, stdout, stderr = self.run_cli(
            "audit",
            str(link),
            "--entity",
            "Atlas",
            "--no-save",
            "--json",
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("symbolic link", stderr)
        self.assertEqual(target.read_bytes(), target_payload)
        self.assertTrue(link.is_symlink())
        self.assertFalse(self.home.exists())

    def test_explicit_intermediate_symlink_swap_cannot_redirect_source_bytes(self):
        safe = self.root / "safe" / "nested"
        evil = self.root / "evil" / "nested"
        safe.mkdir(parents=True)
        evil.mkdir(parents=True)
        safe_source = safe / "MEMORY.md"
        evil_source = evil / "MEMORY.md"
        safe_source.write_text("# Facts\n\n- trusted source\n", encoding="utf-8")
        evil_source.write_text("# Facts\n\n- redirected source\n", encoding="utf-8")
        link = self.root / "current"
        try:
            link.symlink_to(safe.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable on this platform")
        selected = link / "nested" / "MEMORY.md"
        original_resolve = Path.resolve
        swapped = False

        def resolve_then_swap(path: Path, strict: bool = False):
            nonlocal swapped
            resolved = original_resolve(path, strict=strict)
            if path == selected and not swapped:
                link.unlink()
                link.symlink_to(evil.parent, target_is_directory=True)
                swapped = True
            return resolved

        with mock.patch.object(Path, "resolve", resolve_then_swap):
            audit = build_audit(selected, entity="Atlas")

        self.assertTrue(swapped)
        self.assertEqual(audit["source"]["path"], str(safe_source.resolve()))
        self.assertEqual([entry["text"] for entry in audit["entries"]], ["trusted source"])
        self.assertNotIn("redirected source", json.dumps(audit))

        project = self.root / "discovery-project"
        outside = self.root / "outside-memory"
        project.mkdir()
        outside.mkdir()
        (outside / "MEMORY.md").write_text(
            "# Facts\n\n- must not cross the project root\n", encoding="utf-8"
        )
        try:
            (project / ".claude").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symbolic links are unavailable on this platform")
        with self.assertRaisesRegex(ValueError, "no memory file found"):
            discover_memory_file(project)

    def test_default_discovery_rejects_parent_swapped_after_validation(self):
        project = self.root / "discovery-race"
        claude_dir = project / ".claude"
        claude_dir.mkdir(parents=True)
        memory = claude_dir / "MEMORY.md"
        memory.write_text("# Facts\n\n- approved in-project memory\n", encoding="utf-8")
        selected = discover_memory_file(project)
        self.assertEqual(selected, memory.resolve())

        outside = self.root / "outside-race"
        outside.mkdir()
        outside_memory = outside / "MEMORY.md"
        outside_memory.write_text(
            "# Facts\n\n- must never be read through a swapped parent\n",
            encoding="utf-8",
        )
        original_dir = project / ".claude-original"

        def swap_parent(_root):
            claude_dir.rename(original_dir)
            claude_dir.symlink_to(outside, target_is_directory=True)
            return selected

        with mock.patch(
            "brain_ai_memory.workspace.discover_memory_file",
            side_effect=swap_parent,
        ):
            with self.assertRaisesRegex(
                ValueError, "outside the project root|without following links"
            ):
                build_audit(None, entity="Atlas", root=project)
        self.assertEqual(
            outside_memory.read_text(encoding="utf-8"),
            "# Facts\n\n- must never be read through a swapped parent\n",
        )

    def test_audit_finds_exact_duplicate_and_structured_conflict_but_ignores_inert_regions(self):
        self.write_memory(
            """# Facts

- release_day: Friday
- release_day: Friday
- release_day: Thursday

```markdown
- release_day: Saturday
```

````markdown
```
- release_day: SECRET_CODE_VALUE
````

<!--
- release_day: Sunday
-->

> - release_day: Monday
lazy blockquote continuation must also stay inert
"""
        )

        audit = build_audit(self.source, entity="Atlas")

        self.assertEqual(len(audit["entries"]), 3)
        self.assertEqual(
            [entry["structured"]["value"] for entry in audit["entries"]],
            ["Friday", "Friday", "Thursday"],
        )
        findings = {finding["kind"]: finding for finding in audit["findings"]}
        self.assertIn("exact_duplicate_candidate", findings)
        self.assertIn("possible_structured_conflict", findings)
        self.assertEqual(
            findings["possible_structured_conflict"]["literal_values"],
            ["Friday", "Thursday"],
        )
        self.assertIn("does not judge truth", findings["exact_duplicate_candidate"]["reason"])
        self.assertIn("no value is assumed current or true", findings["possible_structured_conflict"]["reason"])
        self.assertEqual(audit["counts"]["duplicate_candidates"], 1)
        self.assertEqual(audit["counts"]["possible_conflicts"], 1)
        self.assertFalse(audit["claims"]["truth_or_currentness_inferred"])

    def test_saved_audit_review_approve_ready_apply_is_idempotent(self):
        original = self.write_memory(
            """# Facts

- Atlas deploys on Thursday.

# Events

- Release review completed.
"""
        )

        status, stdout, stderr = self.run_cli(
            "--home",
            str(self.home),
            "audit",
            str(self.source),
            "--entity",
            "Atlas",
            "--json",
        )
        self.assertEqual(status, 0, stderr)
        audit_result = json.loads(stdout)
        audit_id = audit_result["id"]
        self.assertTrue(Path(audit_result["plan_path"]).is_file())

        status, stdout, stderr = self.run_cli(
            "--home",
            str(self.home),
            "review",
            audit_id,
            "--approve-ready",
            "--json",
        )
        self.assertEqual(status, 0, stderr)
        review_result = json.loads(stdout)["review"]
        self.assertEqual(review_result["counts"], {"approved": 2, "skipped": 0, "unresolved": 0})

        status, stdout, stderr = self.run_cli(
            "--home",
            str(self.home),
            "apply",
            review_result["id"],
            "--yes",
            "--json",
        )
        self.assertEqual(status, 0, stderr)
        first = json.loads(stdout)
        self.assertEqual(first["status"], "applied")
        self.assertEqual(sum(item["status"] == "imported" for item in first["results"]), 2)

        status, stdout, stderr = self.run_cli(
            "--home",
            str(self.home),
            "apply",
            review_result["id"],
            "--yes",
            "--json",
        )
        self.assertEqual(status, 0, stderr)
        second = json.loads(stdout)
        self.assertEqual(second["status"], "already_applied")
        self.assertEqual(second["id"], first["id"])

        runtime = BrainAIRuntime(self.home)
        self.assertEqual(runtime.store.counts()["semantic"], 1)
        self.assertEqual(runtime.store.counts()["episodic"], 1)
        self.assertEqual(runtime.store.counts()["entities"], 1)
        self.assertEqual(self.source.read_bytes(), original)

    def test_completed_review_remains_idempotent_after_source_changes(self):
        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        audit = build_audit(self.source, entity="Atlas")
        runtime = BrainAIRuntime(self.home)
        review = build_review(audit, runtime.store, approve_ready=True)
        apply_review(self.home, runtime.store, review, audit)
        self.source.write_text(
            "# Facts\n\n- Atlas deploys on Friday.\n", encoding="utf-8"
        )

        repeated = apply_review(self.home, runtime.store, review, audit)

        self.assertEqual(repeated["status"], "already_applied")

    def test_applied_legacy_rule_review_remains_idempotent_after_safety_tightening(self):
        self.write_memory("# Rules\n\n- Production deployment requires approval.\n")
        runtime = BrainAIRuntime(self.home)
        audit = build_audit(self.source, entity="Atlas")
        item_id = audit["entries"][0]["id"]
        legacy_pattern = r"^git\s+push\s+--force\s+now$"

        with mock.patch.object(
            workspace_module,
            "compile_safe_rule_pattern",
            side_effect=re.compile,
        ):
            review = build_review(
                audit,
                runtime.store,
                rules=[f"{item_id}={legacy_pattern}"],
            )
            first = apply_review(self.home, runtime.store, review, audit)

        self.assertEqual(first["status"], "applied")
        upgraded = BrainAIRuntime(self.home)
        repeated = apply_review(self.home, upgraded.store, review, audit)
        self.assertEqual(repeated["status"], "already_applied")
        self.assertEqual(repeated["id"], first["id"])
        self.assertFalse(repeated["source_file_changed"])
        quarantined = upgraded.store.unresolved_rule_quarantines()
        self.assertEqual([item["pattern"] for item in quarantined], [legacy_pattern])

    def test_bom_crlf_and_missing_final_newline_remain_byte_identical_through_apply(self):
        original = b"\xef\xbb\xbf# Facts\r\n\r\n- Atlas deploys on Thursday."
        self.source.write_bytes(original)

        audit = build_audit(self.source, entity="Atlas")
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual([entry["text"] for entry in audit["entries"]], ["Atlas deploys on Thursday."])
        runtime = BrainAIRuntime(self.home)
        review = build_review(audit, runtime.store, approve_ready=True)
        self.assertEqual(self.source.read_bytes(), original)
        receipt = apply_review(self.home, runtime.store, review, audit)

        self.assertEqual(receipt["status"], "applied")
        self.assertFalse(receipt["source_file_changed"])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(len(runtime.store.knowledge()), 1)

    def test_source_drift_raises_workflow_conflict_without_imports(self):
        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        audit = build_audit(self.source, entity="Atlas")
        runtime = BrainAIRuntime(self.home)
        review = build_review(audit, runtime.store, approve_ready=True)
        self.source.write_text("# Facts\n\n- Atlas deploys on Friday.\n", encoding="utf-8")

        with self.assertRaisesRegex(WorkflowConflict, "source_changed"):
            apply_review(self.home, runtime.store, review, audit)

        self.assertEqual(runtime.store.counts()["semantic"], 0)
        self.assertEqual(runtime.store.counts()["episodic"], 0)
        self.assertEqual(runtime.store.counts()["entities"], 0)
        with runtime.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_ledger").fetchone()[0], 0)

    def test_store_drift_after_review_raises_workflow_conflict_without_batch(self):
        original = self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        audit = build_audit(self.source, entity="Atlas")
        runtime = BrainAIRuntime(self.home)
        review = build_review(audit, runtime.store, approve_ready=True)
        independent = runtime.store.put_knowledge("Independent operator memory", source="test")

        with self.assertRaisesRegex(WorkflowConflict, "store_changed"):
            apply_review(self.home, runtime.store, review, audit)

        self.assertEqual([item["id"] for item in runtime.store.knowledge()], [independent["id"]])
        self.assertEqual(runtime.store.counts()["entities"], 0)
        self.assertEqual(self.source.read_bytes(), original)
        with runtime.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_ledger").fetchone()[0], 0)

    def test_tampered_audit_and_review_fail_integrity_checks_without_imports(self):
        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        audit = build_audit(self.source, entity="Atlas")
        runtime = BrainAIRuntime(self.home)

        tampered_audit = copy.deepcopy(audit)
        tampered_audit["entries"][0]["text"] = "Tampered fact"
        with self.assertRaisesRegex(ValueError, "audit plan integrity"):
            build_review(tampered_audit, runtime.store, approve_ready=True)

        review = build_review(audit, runtime.store, approve_ready=True)
        tampered_review = copy.deepcopy(review)
        item_id = next(iter(tampered_review["decisions"]))
        tampered_review["decisions"][item_id]["action"] = "episodic"
        with self.assertRaisesRegex(ValueError, "review plan integrity"):
            apply_review(self.home, runtime.store, tampered_review, audit)

        redirected_review = copy.deepcopy(review)
        redirected_review["entity"] = {"name": "Boreal", "type": "project"}
        with self.assertRaisesRegex(ValueError, "review plan integrity"):
            apply_review(self.home, runtime.store, redirected_review, audit)

        self.assertEqual(runtime.store.counts()["semantic"], 0)
        self.assertEqual(runtime.store.counts()["episodic"], 0)
        self.assertEqual(runtime.store.counts()["entities"], 0)
        with runtime.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_ledger").fetchone()[0], 0)

    def test_cli_apply_returns_exit_three_for_source_and_store_conflicts(self):
        for drift_kind in ("source", "store"):
            with self.subTest(drift=drift_kind):
                project = self.root / f"cli-{drift_kind}"
                project.mkdir()
                source = project / "MEMORY.md"
                home = project / ".brain-ai"
                source.write_text("# Facts\n\n- Atlas deploys on Thursday.\n", encoding="utf-8")

                status, stdout, stderr = self.run_cli(
                    "--home",
                    str(home),
                    "audit",
                    str(source),
                    "--entity",
                    "Atlas",
                    "--json",
                )
                self.assertEqual(status, 0, stderr)
                audit_id = json.loads(stdout)["id"]
                status, stdout, stderr = self.run_cli(
                    "--home",
                    str(home),
                    "review",
                    audit_id,
                    "--approve-ready",
                    "--json",
                )
                self.assertEqual(status, 0, stderr)
                review_id = json.loads(stdout)["review"]["id"]

                if drift_kind == "source":
                    source.write_text("# Facts\n\n- Atlas deploys on Friday.\n", encoding="utf-8")
                else:
                    BrainAIRuntime(home).store.put_knowledge("Independent operator memory", source="test")

                status, stdout, stderr = self.run_cli(
                    "--home",
                    str(home),
                    "apply",
                    review_id,
                    "--yes",
                    "--json",
                )
                self.assertEqual(status, 3)
                self.assertEqual(stdout, "")
                self.assertIn(f"{drift_kind}_changed", stderr)
                runtime = BrainAIRuntime(home)
                with runtime.store.connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_ledger").fetchone()[0], 0)

    def test_state_and_rule_require_explicit_review_and_apply_with_entity_scope(self):
        self.write_memory(
            """# Current state

- open_reviews = 3

# Rules

- Production deployment requires approval.
"""
        )
        audit = build_audit(self.source, entity="Atlas")
        runtime = BrainAIRuntime(self.home)
        state_entry = next(entry for entry in audit["entries"] if entry["structured"])
        rule_entry = next(entry for entry in audit["entries"] if entry["suggested_type"] == "rule")

        preview = build_review(audit, runtime.store, approve_ready=True)
        self.assertEqual(preview["counts"]["approved"], 0)
        self.assertEqual(preview["counts"]["unresolved"], 2)

        review = build_review(
            audit,
            runtime.store,
            assignments=[f"{state_entry['id']}=state"],
            rules=[f"{rule_entry['id']}=deploy production"],
            rule_effect="block",
        )
        self.assertEqual(review["counts"], {"approved": 2, "skipped": 0, "unresolved": 0})
        receipt = apply_review(self.home, runtime.store, review, audit)
        self.assertEqual(receipt["status"], "applied")

        states = runtime.store.states("Atlas", include_global=False)
        self.assertEqual([(item["key"], item["value"]) for item in states], [("open_reviews", 3)])
        rules = runtime.store.rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["effect"], "block")
        self.assertTrue(rules[0]["entity_ids"])
        gate = runtime.gate("deploy production", entity="Atlas")
        self.assertFalse(gate["allowed"])
        self.assertEqual(gate["rule_id"], rules[0]["id"])

    def test_rollback_is_logical_and_idempotent(self):
        original = self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        audit = build_audit(self.source, entity="Atlas")
        runtime = BrainAIRuntime(self.home)
        review = build_review(audit, runtime.store, approve_ready=True)
        receipt = apply_review(self.home, runtime.store, review, audit)
        self.assertEqual(len(runtime.store.knowledge()), 1)

        first = rollback_batch(self.home, runtime.store, receipt["id"])
        self.assertEqual(first["status"], "rolled_back")
        self.assertFalse(first["physical_erasure"])
        self.assertTrue(first["evidence_retained"])
        self.assertEqual(runtime.store.knowledge(), [])
        retained = runtime.store.knowledge(include_inactive=True)
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["status"], "archived")
        self.assertEqual(self.source.read_bytes(), original)

        second = rollback_batch(self.home, runtime.store, receipt["id"])
        self.assertEqual(second["status"], "already_rolled_back")
        self.assertFalse(second["physical_erasure"])
        with runtime.store.connect() as conn:
            ledger_statuses = {
                row[0] for row in conn.execute("SELECT status FROM import_ledger").fetchall()
            }
        self.assertEqual(ledger_statuses, {"rolled_back"})

        repeated_audit = build_audit(self.source, entity="Atlas")
        repeated_review = build_review(
            repeated_audit, runtime.store, approve_ready=True
        )
        repeated = apply_review(
            self.home, runtime.store, repeated_review, repeated_audit
        )
        self.assertEqual(repeated["status"], "applied")
        self.assertEqual(len(runtime.store.knowledge()), 1)
        with runtime.store.connect() as conn:
            rows = conn.execute(
                "SELECT status FROM import_ledger ORDER BY created_at"
            ).fetchall()
        self.assertEqual([row["status"] for row in rows], ["rolled_back", "active"])

    def test_rollback_requires_later_already_imported_batch_first(self):
        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        runtime = BrainAIRuntime(self.home)

        first_audit = build_audit(self.source, entity="Atlas")
        first_review = build_review(
            first_audit, runtime.store, approve_ready=True
        )
        first = apply_review(
            self.home, runtime.store, first_review, first_audit
        )
        second_audit = build_audit(self.source, entity="Atlas")
        second_review = build_review(
            second_audit, runtime.store, approve_ready=True
        )
        second = apply_review(
            self.home, runtime.store, second_review, second_audit
        )

        self.assertEqual(second["results"][0]["status"], "already_imported")
        self.assertEqual(
            second["results"][0]["depends_on_batch"], first["id"]
        )
        with self.assertRaisesRegex(
            WorkflowConflict, "batch_has_active_dependents"
        ):
            rollback_batch(self.home, runtime.store, first["id"])
        self.assertEqual(len(runtime.store.knowledge()), 1)

        self.assertEqual(
            rollback_batch(self.home, runtime.store, second["id"])["status"],
            "rolled_back",
        )
        self.assertEqual(
            rollback_batch(self.home, runtime.store, first["id"])["status"],
            "rolled_back",
        )
        self.assertEqual(runtime.store.knowledge(), [])

    def test_rollback_requires_distinct_source_using_same_target_first(self):
        source_a = self.root / "A.md"
        source_b = self.root / "B.md"
        source_a.write_text(
            "# Facts\n\n- Shared release checklist is approved.\n",
            encoding="utf-8",
        )
        source_b.write_text(
            "# Approved facts\n\n- Shared release checklist is approved.\n",
            encoding="utf-8",
        )
        runtime = BrainAIRuntime(self.home)

        audit_a = build_audit(source_a, entity="Atlas")
        review_a = build_review(audit_a, runtime.store, approve_ready=True)
        batch_a = apply_review(self.home, runtime.store, review_a, audit_a)
        audit_b = build_audit(source_b, entity="Atlas")
        review_b = build_review(audit_b, runtime.store, approve_ready=True)
        batch_b = apply_review(self.home, runtime.store, review_b, audit_b)

        self.assertEqual(batch_b["results"][0]["status"], "already_present")
        with self.assertRaisesRegex(
            WorkflowConflict, "batch_has_active_dependents"
        ):
            rollback_batch(self.home, runtime.store, batch_a["id"])
        self.assertEqual(len(runtime.store.knowledge()), 1)

        rollback_batch(self.home, runtime.store, batch_b["id"])
        repeated_audit_b = build_audit(source_b, entity="Atlas")
        repeated_review_b = build_review(
            repeated_audit_b, runtime.store, approve_ready=True
        )
        self.assertEqual(repeated_review_b["id"], review_b["id"])
        repeated_batch_b = apply_review(
            self.home, runtime.store, repeated_review_b, repeated_audit_b
        )
        self.assertNotEqual(repeated_batch_b["id"], batch_b["id"])
        self.assertEqual(
            repeated_batch_b["results"][0]["status"], "already_present"
        )

        rollback_batch(self.home, runtime.store, repeated_batch_b["id"])
        rollback_batch(self.home, runtime.store, batch_a["id"])
        self.assertEqual(runtime.store.knowledge(), [])

    def test_rolled_back_state_review_can_create_a_new_immutable_attempt(self):
        self.write_memory("# Current state\n\n- open_reviews = 3\n")
        runtime = BrainAIRuntime(self.home)
        runtime.store.put_entity("Atlas", entity_type="project")
        audit = build_audit(self.source, entity="Atlas")
        item_id = audit["entries"][0]["id"]
        review = build_review(
            audit,
            runtime.store,
            assignments=[f"{item_id}=state"],
        )
        first = apply_review(self.home, runtime.store, review, audit)
        rollback_batch(self.home, runtime.store, first["id"])

        repeated_audit = build_audit(self.source, entity="Atlas")
        repeated_review = build_review(
            repeated_audit,
            runtime.store,
            assignments=[f"{item_id}=state"],
        )
        self.assertEqual(repeated_review["id"], review["id"])
        second = apply_review(
            self.home, runtime.store, repeated_review, repeated_audit
        )

        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(
            runtime.store.states("Atlas", include_global=False)[0]["value"],
            3,
        )
        with runtime.store.connect() as conn:
            attempts = conn.execute(
                """SELECT id, status FROM import_batches
                WHERE review_id = ? ORDER BY created_at""",
                (review["id"],),
            ).fetchall()
        self.assertEqual(
            [(row["id"], row["status"]) for row in attempts],
            [(first["id"], "rolled_back"), (second["id"], "applied")],
        )

    def test_rollback_removes_only_the_entity_link_created_by_import(self):
        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        runtime = BrainAIRuntime(self.home)
        atlas = runtime.store.put_entity("Atlas", entity_type="project")
        existing = runtime.store.put_knowledge(
            "Atlas deploys on Thursday.", source="existing"
        )
        runtime.store.link_entity(
            "semantic", existing["id"], atlas["id"], role="context"
        )

        audit = build_audit(self.source, entity="Atlas")
        review = build_review(audit, runtime.store, approve_ready=True)
        receipt = apply_review(self.home, runtime.store, review, audit)
        roles_before = {
            link["role"]
            for link in runtime.store.entity_links("semantic", existing["id"])
        }
        self.assertEqual(roles_before, {"about", "context"})

        rollback_batch(self.home, runtime.store, receipt["id"])
        roles_after = {
            link["role"]
            for link in runtime.store.entity_links("semantic", existing["id"])
        }
        self.assertEqual(roles_after, {"context"})
        self.assertEqual(runtime.store.get_knowledge(existing["id"])["status"], "active")

    def test_same_source_imports_independently_into_two_entities(self):
        self.write_memory("# Facts\n\n- Shared release checklist is approved.\n")
        runtime = BrainAIRuntime(self.home)

        atlas_audit = build_audit(self.source, entity="Atlas")
        atlas_review = build_review(atlas_audit, runtime.store, approve_ready=True)
        apply_review(self.home, runtime.store, atlas_review, atlas_audit)

        boreal_audit = build_audit(self.source, entity="Boreal")
        boreal_review = build_review(boreal_audit, runtime.store, approve_ready=True)
        boreal_receipt = apply_review(
            self.home, runtime.store, boreal_review, boreal_audit
        )

        self.assertEqual(boreal_receipt["results"][0]["status"], "already_present")
        atlas_id = runtime.store.get_entity("Atlas")["id"]
        boreal_id = runtime.store.get_entity("Boreal")["id"]
        record = runtime.store.knowledge()[0]
        self.assertEqual(set(record["entity_ids"]), {atlas_id, boreal_id})
        self.assertTrue(runtime.store.search_knowledge("checklist", entity_id=atlas_id))
        self.assertTrue(runtime.store.search_knowledge("checklist", entity_id=boreal_id))
        with runtime.store.connect() as conn:
            ledger_entities = {
                row["entity_id"]
                for row in conn.execute("SELECT entity_id FROM import_ledger")
            }
        self.assertEqual(ledger_entities, {atlas_id, boreal_id})

    def test_active_ledger_does_not_hide_lifecycle_or_state_divergence(self):
        self.write_memory("# Facts\n\n- Atlas deploys on Thursday.\n")
        runtime = BrainAIRuntime(self.home)
        first_audit = build_audit(self.source, entity="Atlas")
        first_review = build_review(
            first_audit, runtime.store, approve_ready=True
        )
        first = apply_review(self.home, runtime.store, first_review, first_audit)
        target_id = first["results"][0]["target_id"]
        runtime.store.record_lifecycle(
            "semantic", target_id, "archive", "operator archived it"
        )

        repeated_audit = build_audit(self.source, entity="Atlas")
        repeated_review = build_review(
            repeated_audit, runtime.store, approve_ready=True
        )
        with self.assertRaisesRegex(WorkflowConflict, "prior_import_changed"):
            apply_review(
                self.home, runtime.store, repeated_review, repeated_audit
            )
        self.assertEqual(runtime.store.knowledge(), [])

        state_source = self.root / "STATE.md"
        state_source.write_text(
            "# Current state\n\n- open_reviews = 3\n", encoding="utf-8"
        )
        state_audit = build_audit(state_source, entity="Atlas")
        state_item = state_audit["entries"][0]["id"]
        state_review = build_review(
            state_audit,
            runtime.store,
            assignments=[f"{state_item}=state"],
        )
        apply_review(self.home, runtime.store, state_review, state_audit)
        runtime.store.set_state("open_reviews", 9, source="operator", entity="Atlas")
        new_state_audit = build_audit(state_source, entity="Atlas")
        new_state_review = build_review(
            new_state_audit,
            runtime.store,
            assignments=[f"{new_state_audit['entries'][0]['id']}=state"],
        )
        with self.assertRaisesRegex(WorkflowConflict, "prior_import_changed"):
            apply_review(
                self.home,
                runtime.store,
                new_state_review,
                new_state_audit,
            )
        self.assertEqual(
            runtime.store.states("Atlas", include_global=False)[0]["value"], 9
        )

    def test_import_does_not_turn_global_semantic_memory_into_project_only_memory(self):
        self.write_memory("# Facts\n\n- Shared policy requires review.\n")
        runtime = BrainAIRuntime(self.home)
        boreal = runtime.store.put_entity("Boreal", entity_type="project")
        global_record = runtime.store.put_knowledge(
            "Shared policy requires review.", source="global"
        )

        audit = build_audit(self.source, entity="Atlas")
        review = build_review(audit, runtime.store, approve_ready=True)
        apply_review(self.home, runtime.store, review, audit)

        with runtime.store.connect() as conn:
            global_scope = conn.execute(
                "SELECT global_scope FROM knowledge WHERE id = ?",
                (global_record["id"],),
            ).fetchone()[0]
        self.assertEqual(global_scope, 1)
        self.assertEqual(
            [item["id"] for item in runtime.store.search_knowledge(
                "Shared policy", entity_id=boreal["id"]
            )],
            [global_record["id"]],
        )
        self.assertEqual(
            [item["id"] for item in runtime.recall(
                "Shared policy", entity="Boreal"
            )["by_component"]["ATL"]],
            [global_record["id"]],
        )
        atlas = runtime.store.get_entity("Atlas")
        runtime.store.link_entity("semantic", global_record["id"], atlas["id"])
        self.assertEqual(
            runtime.store.search_knowledge("Shared policy", entity_id=boreal["id"]),
            [],
        )
        self.assertEqual(
            runtime.recall("Shared policy", entity="Boreal")["by_component"]["ATL"],
            [],
        )
        with self.assertRaisesRegex(ValueError, "instead of widening"):
            runtime.store.put_knowledge(
                "Shared policy requires review.", source="unscoped-repeat"
            )
        self.assertEqual(
            runtime.store.search_knowledge("Shared policy", entity_id=boreal["id"]),
            [],
        )

    def test_supersession_changes_only_the_reviewed_entity_and_can_rollback(self):
        self.write_memory("# Facts\n\n- Release day is Thursday.\n")
        runtime = BrainAIRuntime(self.home)
        atlas = runtime.store.put_entity("Atlas", entity_type="project")
        boreal = runtime.store.put_entity("Boreal", entity_type="project")
        old = runtime.store.put_knowledge(
            "Release day is Friday",
            source="test",
            entities=[atlas["id"], boreal["id"]],
        )

        audit = build_audit(self.source, entity="Atlas")
        entry_id = audit["entries"][0]["id"]
        review = build_review(
            audit,
            runtime.store,
            supersedes=[f"{entry_id}={old['id']}"],
        )
        receipt = apply_review(self.home, runtime.store, review, audit)

        atlas_text = {
            item["text"]
            for item in runtime.store.search_knowledge("Release day", entity_id=atlas["id"])
        }
        boreal_text = {
            item["text"]
            for item in runtime.store.search_knowledge("Release day", entity_id=boreal["id"])
        }
        self.assertIn("Release day is Thursday.", atlas_text)
        self.assertNotIn("Release day is Friday", atlas_text)
        self.assertEqual(boreal_text, {"Release day is Friday"})
        active_edges = runtime.store.knowledge_supersessions(
            old_id=old["id"], entity_id=atlas["id"]
        )
        self.assertEqual(len(active_edges), 1)
        self.assertEqual(active_edges[0]["batch_id"], receipt["id"])

        rollback_batch(self.home, runtime.store, receipt["id"])
        atlas_after = {
            item["text"]
            for item in runtime.store.search_knowledge("Release day", entity_id=atlas["id"])
        }
        self.assertEqual(atlas_after, {"Release day is Friday"})
        retained_edges = runtime.store.knowledge_supersessions(
            old_id=old["id"],
            entity_id=atlas["id"],
            include_inactive=True,
        )
        self.assertEqual(retained_edges[0]["status"], "rolled_back")

    def test_supersession_reuses_existing_replacement_and_rejects_foreign_target(self):
        self.write_memory("# Facts\n\n- Release day is Thursday.\n")
        runtime = BrainAIRuntime(self.home)
        atlas = runtime.store.put_entity("Atlas", entity_type="project")
        boreal = runtime.store.put_entity("Boreal", entity_type="project")
        old_atlas = runtime.store.put_knowledge(
            "Release day is Friday", source="test", entities=[atlas["id"]]
        )
        existing_new = runtime.store.put_knowledge(
            "Release day is Thursday.", source="test", entities=[boreal["id"]]
        )

        audit = build_audit(self.source, entity="Atlas")
        entry_id = audit["entries"][0]["id"]
        review = build_review(
            audit,
            runtime.store,
            supersedes=[f"{entry_id}={old_atlas['id']}"],
        )
        receipt = apply_review(self.home, runtime.store, review, audit)
        self.assertEqual(receipt["results"][0]["target_id"], existing_new["id"])
        reused = runtime.store.get_knowledge(existing_new["id"])
        self.assertIn(old_atlas["id"], reused["supersedes_ids"])
        self.assertEqual(reused["supersedes"], old_atlas["id"])
        self.assertEqual(
            runtime.store.knowledge_supersessions(
                old_id=old_atlas["id"], entity_id=atlas["id"]
            )[0]["batch_id"],
            receipt["id"],
        )
        self.assertNotIn(
            old_atlas["id"],
            [item["id"] for item in runtime.store.search_knowledge(
                "Release day", entity_id=atlas["id"]
            )],
        )

        rollback_batch(self.home, runtime.store, receipt["id"])
        rolled_back_replacement = runtime.store.get_knowledge(existing_new["id"])
        self.assertIsNone(rolled_back_replacement["supersedes"])
        self.assertEqual(rolled_back_replacement["supersession_edges"], [])
        retained = runtime.store.knowledge_supersessions(
            old_id=old_atlas["id"],
            entity_id=atlas["id"],
            include_inactive=True,
        )
        self.assertEqual(retained[0]["status"], "rolled_back")

        old_second = runtime.store.put_knowledge(
            "Release date remains Friday",
            source="test",
            entities=[atlas["id"]],
        )
        self.write_memory(
            "# Facts\n\n- Release day is Thursday.\n- Release day is Thursday.\n"
        )
        converging_audit = build_audit(self.source, entity="Atlas")
        self.assertEqual(len(converging_audit["entries"]), 2)
        converging_review = build_review(
            converging_audit,
            runtime.store,
            supersedes=[
                f"{converging_audit['entries'][0]['id']}={old_atlas['id']}",
                f"{converging_audit['entries'][1]['id']}={old_second['id']}",
            ],
        )
        converging_receipt = apply_review(
            self.home,
            runtime.store,
            converging_review,
            converging_audit,
        )
        self.assertIn(
            runtime.store.get_knowledge(existing_new["id"])["supersedes"],
            {old_atlas["id"], old_second["id"]},
        )
        rollback_batch(self.home, runtime.store, converging_receipt["id"])
        self.assertIsNone(
            runtime.store.get_knowledge(existing_new["id"])["supersedes"]
        )
        converged_history = runtime.store.knowledge_supersessions(
            replacement_id=existing_new["id"],
            entity_id=atlas["id"],
            include_inactive=True,
        )
        self.assertFalse(any(edge["status"] == "active" for edge in converged_history))

        foreign = runtime.store.put_knowledge(
            "Boreal-only policy", source="test", entities=[boreal["id"]]
        )
        foreign_source = self.root / "FOREIGN.md"
        foreign_source.write_text("# Facts\n\n- Replacement policy\n", encoding="utf-8")
        foreign_audit = build_audit(foreign_source, entity="Atlas")
        with self.assertRaisesRegex(ValueError, "not scoped to Atlas"):
            build_review(
                foreign_audit,
                runtime.store,
                supersedes=[
                    f"{foreign_audit['entries'][0]['id']}={foreign['id']}"
                ],
            )

    def test_invalid_rule_regex_is_a_normal_review_error(self):
        self.write_memory("# Rules\n\n- Production requires approval.\n")
        runtime = BrainAIRuntime(self.home)
        audit = build_audit(self.source, entity="Atlas")
        item_id = audit["entries"][0]["id"]
        with self.assertRaisesRegex(ValueError, "invalid procedural rule"):
            build_review(
                audit,
                runtime.store,
                rules=[f"{item_id}=["],
            )

    def test_unsafe_rule_regex_is_rejected_by_review_and_apply_without_mutation(self):
        self.write_memory("# Rules\n\n- Production requires approval.\n")
        runtime = BrainAIRuntime(self.home)
        audit = build_audit(self.source, entity="Atlas")
        item_id = audit["entries"][0]["id"]
        pathological = r"(a+)+$"

        with self.assertRaisesRegex(ValueError, "invalid procedural rule"):
            build_review(
                audit,
                runtime.store,
                rules=[f"{item_id}={pathological}"],
            )

        review = build_review(
            audit,
            runtime.store,
            rules=[f"{item_id}=deploy production"],
        )
        review["decisions"][item_id]["pattern"] = pathological
        identity = {
            "audit_id": review["audit_id"],
            "entity": review["entity"],
            "source_sha256": review["source"]["sha256"],
            "store_revision": review["store_revision"],
            "decisions": {
                key: review["decisions"][key]
                for key in sorted(review["decisions"])
            },
        }
        review["id"] = workspace_module._stable_id("review", identity)

        with self.assertRaisesRegex(ValueError, "invalid procedural rule"):
            apply_review(self.home, runtime.store, review, audit)

        with runtime.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0], 0)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM import_ledger").fetchone()[0],
                0,
            )

    def test_handoff_and_resume_are_isolated_by_entity(self):
        runtime = BrainAIRuntime(self.home)
        atlas = runtime.store.put_entity("Atlas", entity_type="project")
        boreal = runtime.store.put_entity("Boreal", entity_type="project")
        runtime.store.put_knowledge("Atlas deploys Thursday", entities=[atlas["id"]])
        runtime.store.put_knowledge("Boreal deploys Monday", entities=[boreal["id"]])
        atlas_event = runtime.store.append_event(
            "Atlas review completed", promote_to="semantic", entities=[atlas["id"]]
        )
        boreal_event = runtime.store.append_event(
            "Boreal review pending", promote_to="semantic", entities=[boreal["id"]]
        )
        runtime.store.set_state("open_reviews", 1, entity=atlas["id"])
        runtime.store.set_state("open_reviews", 7, entity=boreal["id"])
        runtime.store.add_rule(r"deploy atlas", reason="Atlas approval", entities=[atlas["id"]])
        runtime.store.add_rule(r"deploy boreal", reason="Boreal approval", entities=[boreal["id"]])

        first_session = runtime.resume("Atlas")
        self.assertEqual(first_session["status"], "not_found")
        self.assertEqual(first_session["next_actions"], [])

        atlas_handoff = runtime.handoff(
            atlas["id"], summary="Atlas handoff", next_actions=["ship Atlas"]
        )
        boreal_handoff = runtime.handoff(
            boreal["id"], summary="Boreal handoff", next_actions=["review Boreal"]
        )

        resumed_atlas = runtime.resume("Atlas")
        resumed_boreal = runtime.resume("Boreal")
        self.assertEqual(resumed_atlas["id"], atlas_handoff["id"])
        self.assertEqual(resumed_boreal["id"], boreal_handoff["id"])
        self.assertEqual(resumed_atlas["summary"], "Atlas handoff")
        self.assertEqual(resumed_boreal["summary"], "Boreal handoff")
        self.assertEqual(
            resumed_atlas["counts"],
            {"episodic": 1, "semantic": 1, "rules": 1, "exact_state": 1},
        )
        self.assertEqual(
            resumed_boreal["counts"],
            {"episodic": 1, "semantic": 1, "rules": 1, "exact_state": 1},
        )
        self.assertEqual(resumed_atlas["pending_consolidation"], [atlas_event["id"]])
        self.assertEqual(resumed_boreal["pending_consolidation"], [boreal_event["id"]])

    def test_project_connections_preview_apply_disconnect_preserve_existing_config(self):
        claude_root = self.root / "claude-project"
        claude_root.mkdir()
        claude_path = claude_root / ".mcp.json"
        claude_existing = {
            "mcpServers": {"existing": {"command": "existing", "args": ["--keep"]}},
            "other": {"keep": True},
        }
        claude_path.write_text(json.dumps(claude_existing, indent=2) + "\n", encoding="utf-8")
        claude_before = claude_path.read_bytes()

        preview = connection_change(
            self.home, "claude-code", entity="Atlas", project_root=claude_root
        )
        self.assertEqual(preview["status"], "preview")
        self.assertTrue(preview["changed"])
        self.assertIn("--project-root", preview["next"])
        self.assertIn(str(claude_root.resolve()), preview["next"])
        self.assertEqual(claude_path.read_bytes(), claude_before)
        connected = connection_change(
            self.home, "claude-code", entity="Atlas", project_root=claude_root, apply=True
        )
        self.assertEqual(connected["status"], "connected")
        claude_config = json.loads(claude_path.read_text(encoding="utf-8"))
        self.assertEqual(claude_config["mcpServers"]["existing"], claude_existing["mcpServers"]["existing"])
        self.assertEqual(claude_config["other"], claude_existing["other"])
        self.assertIn("brain-ai-memory", claude_config["mcpServers"])
        managed_claude = claude_config["mcpServers"]["brain-ai-memory"]
        self.assertTrue(Path(managed_claude["command"]).is_absolute())
        self.assertEqual(
            managed_claude["args"][:2], ["-m", "brain_ai_memory.mcp_server"]
        )

        connected_bytes = claude_path.read_bytes()
        disconnect_preview = connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=claude_root,
            disconnect=True,
        )
        self.assertEqual(disconnect_preview["status"], "preview")
        self.assertEqual(claude_path.read_bytes(), connected_bytes)
        disconnected = connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=claude_root,
            disconnect=True,
            apply=True,
        )
        self.assertEqual(disconnected["status"], "disconnected")

        claude_after = json.loads(claude_path.read_text(encoding="utf-8"))
        self.assertEqual(claude_after, claude_existing)

        codex_root = self.root / "codex-project"
        codex_path = codex_root / ".codex" / "config.toml"
        codex_path.parent.mkdir(parents=True)
        codex_existing = (
            'model = "gpt-5"\n\n'
            "[mcp_servers.existing]\n"
            'command = "existing"\n'
            'args = ["--keep"]\n\n'
        )
        codex_path.write_text(codex_existing, encoding="utf-8")
        codex_before = codex_path.read_bytes()

        preview = connection_change(self.home, "codex", entity="Atlas", project_root=codex_root)
        self.assertEqual(preview["status"], "preview")
        self.assertTrue(preview["changed"])
        self.assertEqual(codex_path.read_bytes(), codex_before)
        connected = connection_change(
            self.home, "codex", entity="Atlas", project_root=codex_root, apply=True
        )
        self.assertEqual(connected["status"], "connected")
        codex_connected = codex_path.read_text(encoding="utf-8")
        self.assertTrue(codex_connected.startswith(codex_existing))
        self.assertIn("# BEGIN brain-ai-memory managed MCP", codex_connected)
        self.assertIn("[mcp_servers.existing]", codex_connected)
        self.assertIn('args = ["-m","brain_ai_memory.mcp_server"', codex_connected)

        disconnect_preview = connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=codex_root,
            disconnect=True,
        )
        self.assertEqual(disconnect_preview["status"], "preview")
        self.assertEqual(codex_path.read_text(encoding="utf-8"), codex_connected)
        disconnected = connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=codex_root,
            disconnect=True,
            apply=True,
        )
        self.assertEqual(disconnected["status"], "disconnected")
        self.assertEqual(codex_path.read_text(encoding="utf-8"), codex_existing)

    def test_connection_keeps_virtualenv_interpreter_symlink(self):
        project_root = self.root / "venv-project"
        project_root.mkdir()
        venv_python = self.root / "venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.symlink_to(sys.executable)

        with mock.patch("brain_ai_memory.workspace.sys.executable", str(venv_python)):
            connected = connection_change(
                self.home,
                "claude-code",
                entity="Atlas",
                project_root=project_root,
                apply=True,
            )

        self.assertEqual(connected["status"], "connected")
        config = json.loads((project_root / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(
            config["mcpServers"]["brain-ai-memory"]["command"],
            str(venv_python),
        )

    def test_disconnect_refuses_tampered_or_symlinked_host_config(self):
        project_root = self.root / "tampered-project"
        project_root.mkdir()
        connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=project_root,
            apply=True,
        )
        config_path = project_root / ".mcp.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["mcpServers"]["brain-ai-memory"]["command"] = "/tmp/not-managed"
        config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
        tampered = config_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "not managed"):
            connection_change(
                self.home,
                "claude-code",
                entity="Atlas",
                project_root=project_root,
                disconnect=True,
                apply=True,
            )
        self.assertEqual(config_path.read_bytes(), tampered)

        config_path.unlink()
        outside = self.root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        config_path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            connection_change(
                self.home,
                "claude-code",
                entity="Atlas",
                project_root=project_root,
            )
        self.assertEqual(outside.read_text(encoding="utf-8"), "{}\n")

    def test_connection_preview_redacts_unrelated_secrets_and_updates_managed_entry(self):
        project_root = self.root / "managed-project"
        project_root.mkdir()
        config_path = project_root / ".mcp.json"
        config_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "unrelated": {
                            "command": "other",
                            "env": {"API_KEY": "TOP_SECRET_VALUE"},
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        preview = connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=project_root,
        )
        self.assertNotIn("TOP_SECRET_VALUE", preview["diff"])
        self.assertNotIn("unrelated", preview["diff"])
        connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=project_root,
            apply=True,
        )
        updated = connection_change(
            self.home,
            "claude-code",
            entity="Boreal",
            project_root=project_root,
            apply=True,
        )
        self.assertEqual(updated["status"], "connected")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        args = config["mcpServers"]["brain-ai-memory"]["args"]
        self.assertEqual(args[-1], "Boreal")
        self.assertEqual(
            config["mcpServers"]["unrelated"]["env"]["API_KEY"],
            "TOP_SECRET_VALUE",
        )
        removed = connection_change(
            self.home,
            "claude-code",
            entity="",
            project_root=project_root,
            disconnect=True,
            apply=True,
        )
        self.assertEqual(removed["status"], "disconnected")

    def test_codex_connection_rejects_invalid_or_quoted_unmanaged_table(self):
        invalid_root = self.root / "invalid-codex"
        (invalid_root / ".codex").mkdir(parents=True)
        invalid_path = invalid_root / ".codex" / "config.toml"
        invalid_path.write_text("[broken\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid TOML"):
            connection_change(
                self.home,
                "codex",
                entity="Atlas",
                project_root=invalid_root,
            )

        quoted_root = self.root / "quoted-codex"
        (quoted_root / ".codex").mkdir(parents=True)
        quoted_path = quoted_root / ".codex" / "config.toml"
        quoted_path.write_text(
            '[mcp_servers."brain-ai-memory"]\n'
            'command = "/usr/bin/python3"\n'
            'args = ["-m", "brain_ai_memory.mcp_server", "--home", "/tmp/x", '
            '"--entity", "Atlas"]\n',
            encoding="utf-8",
        )
        before = quoted_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "outside the managed block"):
            connection_change(
                self.home,
                "codex",
                entity="Atlas",
                project_root=quoted_root,
                apply=True,
            )
        self.assertEqual(quoted_path.read_bytes(), before)

    def test_codex_disconnect_refuses_managed_table_extended_outside_block(self):
        project_root = self.root / "extended-codex"
        (project_root / ".codex").mkdir(parents=True)
        config_path = project_root / ".codex" / "config.toml"
        connection_change(
            self.home,
            "codex",
            entity="Atlas",
            project_root=project_root,
            apply=True,
        )
        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            + "\n[mcp_servers.brain-ai-memory.env]\n"
            + 'UNRELATED = "must-not-survive"\n',
            encoding="utf-8",
        )
        before = config_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "outside the managed block"):
            connection_change(
                self.home,
                "codex",
                entity="Atlas",
                project_root=project_root,
                disconnect=True,
                apply=True,
            )
        self.assertEqual(config_path.read_bytes(), before)

    def test_codex_disconnect_requires_managed_markers_to_wrap_the_table(self):
        project_root = self.root / "misplaced-codex"
        (project_root / ".codex").mkdir(parents=True)
        config_path = project_root / ".codex" / "config.toml"
        command = os.path.abspath(sys.executable)
        table = (
            "[mcp_servers.brain-ai-memory]\n"
            f"command = {json.dumps(command)}\n"
            "args = [\"-m\", \"brain_ai_memory.mcp_server\", "
            "\"--home\", "
            f"{json.dumps(str(self.home))}, \"--entity\", \"Atlas\"]\n"
        )
        cases = (
            (
                "markers-before",
                "# BEGIN brain-ai-memory managed MCP\n"
                "unrelated = true\n"
                "# END brain-ai-memory managed MCP\n"
                + table,
            ),
            (
                "markers-after",
                table
                + "# BEGIN brain-ai-memory managed MCP\n"
                + "# END brain-ai-memory managed MCP\n",
            ),
        )
        for name, content in cases:
            with self.subTest(name=name):
                config_path.write_text(content, encoding="utf-8")
                before = config_path.read_bytes()
                with self.assertRaisesRegex(ValueError, "outside the managed block"):
                    connection_change(
                        self.home,
                        "codex",
                        entity="Atlas",
                        project_root=project_root,
                        disconnect=True,
                        apply=True,
                    )
                self.assertEqual(config_path.read_bytes(), before)
                status = connection_status(
                    self.home,
                    "codex",
                    project_root=project_root,
                    entity="Atlas",
                )
                self.assertFalse(status["configured"])
                self.assertFalse(status["managed_entry"])
                self.assertIn("outside the managed block", status["error"])

    def test_connection_apply_fails_if_config_changes_after_preview_read(self):
        project_root = self.root / "racing-config"
        project_root.mkdir()
        config_path = project_root / ".mcp.json"
        config_path.write_text("{}\n", encoding="utf-8")

        @contextlib.contextmanager
        def mutate_before_write(*_args, **_kwargs):
            config_path.write_text('{"concurrent": true}\n', encoding="utf-8")
            yield

        with mock.patch(
            "brain_ai_memory.workspace._workflow_lock", mutate_before_write
        ):
            with self.assertRaisesRegex(WorkflowConflict, "config_changed"):
                connection_change(
                    self.home,
                    "claude-code",
                    entity="Atlas",
                    project_root=project_root,
                    apply=True,
                )
        self.assertEqual(config_path.read_text(encoding="utf-8"), '{"concurrent": true}\n')

        import brain_ai_memory.workspace as workspace_module

        codex_root = self.root / "racing-parent"
        codex_dir = codex_root / ".codex"
        codex_dir.mkdir(parents=True)
        codex_path = codex_dir / "config.toml"
        codex_path.write_text("", encoding="utf-8")
        outside = self.root / "outside-config"
        outside.mkdir()
        detached = codex_root / ".codex-detached"
        original_atomic = workspace_module._atomic_bytes_at
        swapped = False

        def swap_parent_before_replace(path, payload, *, mode, parent_descriptor):
            nonlocal swapped
            if path.name == "config.toml" and path.parent.name == ".codex" and not swapped:
                codex_dir.rename(detached)
                codex_dir.symlink_to(outside, target_is_directory=True)
                swapped = True
            return original_atomic(
                path,
                payload,
                mode=mode,
                parent_descriptor=parent_descriptor,
            )

        with mock.patch(
            "brain_ai_memory.workspace._atomic_bytes_at",
            side_effect=swap_parent_before_replace,
        ):
            with self.assertRaisesRegex(WorkflowConflict, "config parent changed"):
                connection_change(
                    self.home,
                    "codex",
                    entity="Atlas",
                    project_root=codex_root,
                    apply=True,
                )
        self.assertFalse((outside / "config.toml").exists())
        self.assertTrue((detached / "config.toml").is_file())

    def test_connection_status_requires_current_home_interpreter_and_optional_entity(self):
        project_root = self.root / "status-project"
        project_root.mkdir()
        runtime = BrainAIRuntime(self.home)
        runtime.store.put_entity(
            "Atlas", entity_type="project", aliases=["A"]
        )
        connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=project_root,
            apply=True,
        )
        valid = connection_status(
            self.home,
            "claude-code",
            project_root=project_root,
            entity="Atlas",
        )
        wrong_entity = connection_status(
            self.home,
            "claude-code",
            project_root=project_root,
            entity="Boreal",
        )
        wrong_home = connection_status(
            self.root / "other-home",
            "claude-code",
            project_root=project_root,
        )
        self.assertTrue(valid["configured"])
        self.assertTrue(
            connection_status(
                self.home,
                "claude-code",
                project_root=project_root,
                entity="A",
            )["configured"]
        )
        alias_preview = connection_change(
            self.home,
            "claude-code",
            entity="A",
            project_root=project_root,
        )
        self.assertFalse(alias_preview["changed"])
        self.assertFalse(wrong_entity["configured"])
        self.assertFalse(wrong_home["configured"])
        with self.assertRaisesRegex(ValueError, "different Brain-AI home"):
            connection_change(
                self.root / "wrong-home",
                "claude-code",
                entity="Atlas",
                project_root=project_root,
                disconnect=True,
                apply=True,
            )
        with self.assertRaisesRegex(ValueError, "different entity"):
            connection_change(
                self.home,
                "claude-code",
                entity="Boreal",
                project_root=project_root,
                disconnect=True,
                apply=True,
            )
        alias_disconnect = connection_change(
            self.home,
            "claude-code",
            entity="A",
            project_root=project_root,
            disconnect=True,
            apply=True,
        )
        self.assertEqual(alias_disconnect["status"], "disconnected")

    def test_project_connection_migrates_old_unlocked_entity_binding(self):
        project_root = self.root / "migration-project"
        project_root.mkdir()
        runtime = BrainAIRuntime(self.home)
        runtime.store.put_entity("Atlas", entity_type="project")
        connected = connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=project_root,
            apply=True,
        )
        path = Path(connected["path"])
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                '"--locked-entity"', '"--entity"'
            ),
            encoding="utf-8",
        )

        status = connection_status(
            self.home,
            "claude-code",
            project_root=project_root,
            entity="Atlas",
        )
        self.assertFalse(status["configured"])
        self.assertTrue(status["managed_entry"])
        self.assertTrue(status["migration_required"])
        self.assertIn("connect claude-code --entity Atlas", status["migration_command"])
        self.assertIn(f"--project-root {project_root.resolve()}", status["migration_command"])
        self.assertTrue(status["migration_command"].endswith("--apply"))

        upgraded = connection_change(
            self.home,
            "claude-code",
            entity="Atlas",
            project_root=project_root,
            apply=True,
        )
        self.assertTrue(upgraded["changed"])
        self.assertTrue(
            connection_status(
                self.home,
                "claude-code",
                project_root=project_root,
                entity="Atlas",
            )["configured"]
        )

    def test_user_tools_connection_keeps_overridable_entity(self):
        runtime = BrainAIRuntime(self.home)
        runtime.store.put_entity("Atlas", entity_type="project")
        fake_user_home = (self.root / "user-home").resolve()
        fake_user_home.mkdir()

        with mock.patch(
            "brain_ai_memory.workspace.Path.home", return_value=fake_user_home
        ):
            for host in ("codex", "claude-code"):
                with self.subTest(host=host):
                    connected = connection_change(
                        self.home,
                        host,
                        entity="Atlas",
                        scope="user",
                        apply=True,
                    )
                    path = Path(connected["path"])
                    if host == "codex":
                        entry = tomllib.loads(path.read_text(encoding="utf-8"))[
                            "mcp_servers"
                        ]["brain-ai-memory"]
                    else:
                        entry = json.loads(path.read_text(encoding="utf-8"))[
                            "mcpServers"
                        ]["brain-ai-memory"]
                    self.assertEqual(entry["args"][4], "--entity")
                    status = connection_status(
                        self.home,
                        host,
                        scope="user",
                        entity="Atlas",
                    )
                    self.assertTrue(status["configured"])
                    self.assertFalse(status["entity_locked"])
                    self.assertFalse(status["migration_required"])
                    connection_change(
                        self.home,
                        host,
                        entity="Atlas",
                        scope="user",
                        disconnect=True,
                        apply=True,
                    )


if __name__ == "__main__":
    unittest.main()
