"""Local-first stores for differentiated memory and audit events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import write_default_config
from .text import ranked


LIFECYCLE_OPERATIONS = {
    "keep", "compact", "archive", "migrate-to-knowledge-base",
    "migrate-to-rules", "delete", "split",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class MemoryStore:
    def __init__(self, home: Path):
        self.home = home
        self.db_path = home / "state.sqlite3"
        self.events_path = home / "events.jsonl"
        self.audit_path = home / "audit.jsonl"
        self.checkpoints_path = home / "checkpoints.jsonl"

    def initialize(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        write_default_config(self.home)
        for path in (self.events_path, self.audit_path, self.checkpoints_path):
            path.touch(exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    content_hash TEXT NOT NULL UNIQUE,
                    supersedes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rules (
                    id TEXT PRIMARY KEY,
                    pattern TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS numerical_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lifecycle (
                    id TEXT PRIMARY KEY,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lifecycle_target
                    ON lifecycle(target_type, target_id, created_at);
                """
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _append_jsonl(path: Path, record: dict) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        records = []
        if not path.exists():
            return records
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records

    def append_event(
        self,
        text: str,
        *,
        source: str = "user",
        tags: Iterable[str] = (),
        promote_to: str | None = None,
        rule_pattern: str | None = None,
    ) -> dict:
        record = {
            "id": new_id("evt"),
            "type": "episodic",
            "text": text.strip(),
            "source": source,
            "tags": sorted(set(tags)),
            "promote_to": promote_to,
            "rule_pattern": rule_pattern,
            "created_at": utc_now(),
        }
        self._append_jsonl(self.events_path, record)
        return record

    def events(self, include_inactive: bool = False) -> list[dict]:
        records = self._read_jsonl(self.events_path)
        if include_inactive:
            return records
        inactive = self._inactive_ids("episodic")
        return [record for record in records if record.get("id") not in inactive]

    def search_events(self, query: str, limit: int = 5) -> list[dict]:
        results = ranked(self.events(), query, limit=limit)
        for result in results:
            result["component"] = "HC"
            result["kind"] = "episodic"
        return results

    def put_knowledge(
        self,
        text: str,
        *,
        source: str = "user",
        tags: Iterable[str] = (),
        supersedes: str | None = None,
    ) -> dict:
        clean = text.strip()
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM knowledge WHERE content_hash = ?", (digest,)).fetchone()
            if existing:
                return self._knowledge_row(existing)
            record_id = new_id("mem")
            conn.execute(
                """INSERT INTO knowledge
                (id, text, source, tags_json, status, content_hash, supersedes, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
                (record_id, clean, source, json.dumps(sorted(set(tags)), ensure_ascii=False), digest, supersedes, now, now),
            )
            if supersedes:
                conn.execute(
                    "UPDATE knowledge SET status = 'superseded', updated_at = ? WHERE id = ?",
                    (now, supersedes),
                )
        return self.get_knowledge(record_id)

    @staticmethod
    def _knowledge_row(row: sqlite3.Row) -> dict:
        record = dict(row)
        record["tags"] = json.loads(record.pop("tags_json"))
        return record

    def get_knowledge(self, record_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM knowledge WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise KeyError(f"unknown knowledge id: {record_id}")
        return self._knowledge_row(row)

    def knowledge(self, include_inactive: bool = False) -> list[dict]:
        where = "" if include_inactive else "WHERE status = 'active'"
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM knowledge {where} ORDER BY created_at").fetchall()
        return [self._knowledge_row(row) for row in rows]

    def search_knowledge(self, query: str, limit: int = 5) -> list[dict]:
        results = ranked(self.knowledge(), query, limit=limit)
        for result in results:
            result["component"] = "ATL"
            result["kind"] = "semantic"
            result["backend"] = "local-bm25"
        return results

    def add_rule(self, pattern: str, *, effect: str = "block", reason: str, source: str = "user") -> dict:
        if effect not in {"block", "warn"}:
            raise ValueError("rule effect must be block or warn")
        import re
        re.compile(pattern)
        record = {
            "id": new_id("rule"), "pattern": pattern, "effect": effect,
            "reason": reason.strip(), "source": source, "enabled": 1,
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO rules (id, pattern, effect, reason, source, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                tuple(record[key] for key in ("id", "pattern", "effect", "reason", "source", "enabled", "created_at")),
            )
        return record

    def rules(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM rules WHERE enabled = 1 ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def set_state(self, key: str, value, *, source: str = "user") -> dict:
        now = utc_now()
        payload = json.dumps(value, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO numerical_state (key, value_json, source, updated_at)
                VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json, source=excluded.source, updated_at=excluded.updated_at""",
                (key, payload, source, now),
            )
        return {"key": key, "value": value, "source": source, "updated_at": now}

    def states(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM numerical_state ORDER BY key").fetchall()
        return [
            {"key": row["key"], "value": json.loads(row["value_json"]), "source": row["source"], "updated_at": row["updated_at"]}
            for row in rows
        ]

    def search_states(self, query: str, limit: int = 5) -> list[dict]:
        documents = []
        for state in self.states():
            item = dict(state)
            item["id"] = state["key"]
            item["text"] = f"{state['key']} {state['value']}"
            documents.append(item)
        results = ranked(documents, query, limit=limit)
        for result in results:
            result.update({"component": "IPS", "kind": "numerical"})
        return results

    def record_lifecycle(self, target_type: str, target_id: str, operation: str, reason: str = "") -> dict:
        if operation not in LIFECYCLE_OPERATIONS:
            raise ValueError(f"unknown lifecycle operation: {operation}")
        record = {
            "id": new_id("life"), "target_type": target_type, "target_id": target_id,
            "operation": operation, "reason": reason.strip(), "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO lifecycle (id, target_type, target_id, operation, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                tuple(record.values()),
            )
            if target_type == "semantic" and operation in {"archive", "delete"}:
                conn.execute(
                    "UPDATE knowledge SET status = ?, updated_at = ? WHERE id = ?",
                    ("archived" if operation == "archive" else "deleted", utc_now(), target_id),
                )
        return record

    def _inactive_ids(self, target_type: str) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT l.target_id, l.operation FROM lifecycle l JOIN (
                    SELECT target_id, MAX(created_at) AS newest FROM lifecycle
                    WHERE target_type = ? GROUP BY target_id
                ) x ON l.target_id=x.target_id AND l.created_at=x.newest
                WHERE l.target_type = ?""",
                (target_type, target_type),
            ).fetchall()
        inactive_operations = {
            "archive", "delete", "migrate-to-knowledge-base", "migrate-to-rules",
        }
        return {row["target_id"] for row in rows if row["operation"] in inactive_operations}

    def append_audit(self, record: dict) -> None:
        value = dict(record)
        value.setdefault("created_at", utc_now())
        self._append_jsonl(self.audit_path, value)

    def append_checkpoint(self, record: dict) -> None:
        value = dict(record)
        value.setdefault("created_at", utc_now())
        self._append_jsonl(self.checkpoints_path, value)

    def recent_audit(self, limit: int = 50) -> list[dict]:
        return self._read_jsonl(self.audit_path)[-limit:]

    def checkpoints(self, limit: int = 20) -> list[dict]:
        return self._read_jsonl(self.checkpoints_path)[-limit:]

    def counts(self) -> dict:
        with self.connect() as conn:
            knowledge = conn.execute("SELECT COUNT(*) FROM knowledge WHERE status = 'active'").fetchone()[0]
            rules = conn.execute("SELECT COUNT(*) FROM rules WHERE enabled = 1").fetchone()[0]
            states = conn.execute("SELECT COUNT(*) FROM numerical_state").fetchone()[0]
        return {
            "episodic": len(self.events()), "semantic": knowledge,
            "rules": rules, "numerical_state": states,
            "audit_events": len(self._read_jsonl(self.audit_path)),
            "checkpoints": len(self._read_jsonl(self.checkpoints_path)),
        }
