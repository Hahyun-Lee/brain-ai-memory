import builtins
import json
import multiprocessing
import os
import queue
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from brain_ai_memory.privacy import exclusive_file_lock, open_private_lock
from brain_ai_memory.storage import MemoryStore


def _append_same_audit(home: str, start, results) -> None:
    start.wait()
    store = MemoryStore(Path(home))
    results.put(store.append_audit_once({"id": "audit_same", "type": "test"}))


class StorageConcurrencyTests(unittest.TestCase):
    def test_store_connection_context_closes_the_database_handle(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MemoryStore(Path(temp) / "memory")
            store.initialize()
            with store.connect() as connection:
                connection.execute("SELECT 1").fetchone()
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_append_jsonl_once_is_exactly_once_across_processes(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "memory"
            store = MemoryStore(home)
            store.initialize()

            context = multiprocessing.get_context("spawn")
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_append_same_audit,
                    args=(str(home), start, results),
                )
                for _ in range(6)
            ]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(timeout=15)
                self.assertFalse(process.is_alive())
                self.assertEqual(process.exitcode, 0)

            outcomes = []
            for _ in processes:
                try:
                    outcomes.append(results.get(timeout=2))
                except queue.Empty as exc:  # pragma: no cover - clearer failure message
                    self.fail(f"worker did not report its append result: {exc}")
            self.assertEqual(outcomes.count(True), 1)
            self.assertEqual(outcomes.count(False), len(processes) - 1)
            records = [
                json.loads(line)
                for line in store.audit_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual([item["id"] for item in records], ["audit_same"])

    def test_truncated_ascii_and_utf8_tails_are_quarantined_before_append_once(self):
        tails = (
            b'{"id":"broken-ascii"',
            b'{"id":"broken-utf8","text":"' + "한".encode("utf-8")[:2],
        )
        for index, tail in enumerate(tails):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temp:
                home = Path(temp) / "memory"
                store = MemoryStore(home)
                store.initialize()
                first = {"id": "audit_first", "type": "test"}
                self.assertTrue(store.append_audit_once(first))
                with store.audit_path.open("ab") as handle:
                    handle.write(tail)

                # Read paths skip only the damaged physical line and do not
                # fail whole-file UTF-8 decoding.
                self.assertEqual(
                    [item["id"] for item in store.recent_audit(10)],
                    ["audit_first"],
                )
                # Repair happens before the once scan, so a valid prefix id is
                # still detected and is not appended twice.
                self.assertFalse(store.append_audit_once(first))
                self.assertTrue(
                    store.append_audit_once({"id": "audit_second", "type": "test"})
                )
                plain_tail = tail + b"-plain-append"
                with store.audit_path.open("ab") as handle:
                    handle.write(plain_tail)
                store.append_audit({"id": "audit_third", "type": "test"})

                self.assertEqual(
                    [item["id"] for item in store.recent_audit(10)],
                    ["audit_first", "audit_second", "audit_third"],
                )
                payload = store.audit_path.read_bytes()
                self.assertTrue(payload.endswith(b"\n"))
                for line in payload.splitlines():
                    json.loads(line.decode("utf-8"))
                quarantines = list(
                    home.glob("audit.jsonl.truncated-*.bin")
                )
                self.assertEqual(len(quarantines), 2)
                self.assertEqual(
                    {item.read_bytes() for item in quarantines},
                    {tail, plain_tail},
                )
                if os.name == "posix":
                    self.assertEqual(stat.S_IMODE(quarantines[0].stat().st_mode), 0o600)

    def test_exclusive_file_lock_uses_windows_byte_range_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runtime.lock"
            calls = []

            def locking(descriptor, mode, length):
                calls.append((mode, length, os.lseek(descriptor, 0, os.SEEK_CUR)))

            fake_msvcrt = SimpleNamespace(LK_LOCK=10, LK_UNLCK=11, locking=locking)
            real_import = builtins.__import__

            def import_with_windows_fallback(name, *args, **kwargs):
                if name == "fcntl":
                    raise ImportError("simulated Windows")
                if name == "msvcrt":
                    return fake_msvcrt
                return real_import(name, *args, **kwargs)

            with open_private_lock(path) as handle:
                with mock.patch("builtins.__import__", side_effect=import_with_windows_fallback):
                    with exclusive_file_lock(handle):
                        self.assertEqual(handle.tell(), 0)

            self.assertEqual(path.read_bytes(), b"\0")
            self.assertEqual(calls, [(10, 1, 0), (11, 1, 0)])


if __name__ == "__main__":
    unittest.main()
