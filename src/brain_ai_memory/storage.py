"""Local-first stores for differentiated memory and audit events."""

from __future__ import annotations

import hashlib
import json
import re
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
SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


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
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_name_type
                    ON entities(lower(name), type);
                CREATE TABLE IF NOT EXISTS relations (
                    id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(subject_id, predicate, object_id),
                    FOREIGN KEY(subject_id) REFERENCES entities(id),
                    FOREIGN KEY(object_id) REFERENCES entities(id)
                );
                CREATE INDEX IF NOT EXISTS idx_relations_subject
                    ON relations(subject_id, predicate);
                CREATE INDEX IF NOT EXISTS idx_relations_object
                    ON relations(object_id, predicate);
                CREATE TABLE IF NOT EXISTS memory_entities (
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'about',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(target_type, target_id, entity_id, role),
                    FOREIGN KEY(entity_id) REFERENCES entities(id)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_entities_entity
                    ON memory_entities(entity_id, target_type);
                CREATE TABLE IF NOT EXISTS entity_state (
                    entity_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(entity_id, key),
                    FOREIGN KEY(entity_id) REFERENCES entities(id)
                );
                """
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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

    @staticmethod
    def _entity_row(row: sqlite3.Row) -> dict:
        record = dict(row)
        record["aliases"] = json.loads(record.pop("aliases_json"))
        record["metadata"] = json.loads(record.pop("metadata_json"))
        return record

    def put_entity(
        self,
        name: str,
        *,
        entity_type: str = "concept",
        aliases: Iterable[str] = (),
        metadata: dict | None = None,
    ) -> dict:
        clean_name = name.strip()
        clean_type = entity_type.strip().lower()
        if not clean_name:
            raise ValueError("entity name is required")
        if not SLUG.fullmatch(clean_type):
            raise ValueError("entity type must be a lowercase slug")
        clean_aliases = sorted({alias.strip() for alias in aliases if alias.strip()})
        now = utc_now()
        entity_id: str
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM entities WHERE lower(name) = lower(?) AND type = ?",
                (clean_name, clean_type),
            ).fetchone()
            if existing:
                record = self._entity_row(existing)
                merged_aliases = sorted(set(record["aliases"]) | set(clean_aliases))
                merged_metadata = {**record["metadata"], **(metadata or {})}
                conn.execute(
                    "UPDATE entities SET aliases_json = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
                    (
                        json.dumps(merged_aliases, ensure_ascii=False),
                        json.dumps(merged_metadata, ensure_ascii=False, sort_keys=True),
                        now,
                        record["id"],
                    ),
                )
                entity_id = record["id"]
            else:
                entity_id = new_id("ent")
                conn.execute(
                    """INSERT INTO entities
                    (id, name, type, aliases_json, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entity_id,
                        clean_name,
                        clean_type,
                        json.dumps(clean_aliases, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                    ),
                )
        return self.get_entity(entity_id)

    def get_entity(self, reference: str) -> dict:
        key = reference.strip()
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (key,)).fetchone()
            if row:
                return self._entity_row(row)
            rows = conn.execute("SELECT * FROM entities ORDER BY name").fetchall()
        matches = []
        folded = key.casefold()
        for candidate in rows:
            record = self._entity_row(candidate)
            names = [record["name"], *record["aliases"]]
            if any(name.casefold() == folded for name in names):
                matches.append(record)
        if not matches:
            raise KeyError(f"unknown entity: {reference}")
        if len(matches) > 1:
            options = ", ".join(f"{item['name']} ({item['id']})" for item in matches)
            raise ValueError(f"ambiguous entity '{reference}': {options}")
        return matches[0]

    def entities(self, query: str | None = None) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM entities ORDER BY type, name").fetchall()
        records = [self._entity_row(row) for row in rows]
        if not query:
            return records
        folded = query.casefold()
        return [
            record
            for record in records
            if folded in record["name"].casefold()
            or any(folded in alias.casefold() for alias in record["aliases"])
        ]

    def add_relation(
        self,
        subject: str,
        predicate: str,
        object_: str,
        *,
        source: str = "user",
    ) -> dict:
        subject_record = self.get_entity(subject)
        object_record = self.get_entity(object_)
        clean_predicate = predicate.strip().lower()
        if not SLUG.fullmatch(clean_predicate):
            raise ValueError("relation predicate must be a lowercase slug")
        record = {
            "id": new_id("rel"),
            "subject_id": subject_record["id"],
            "predicate": clean_predicate,
            "object_id": object_record["id"],
            "source": source,
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM relations WHERE subject_id = ? AND predicate = ? AND object_id = ?",
                (record["subject_id"], clean_predicate, record["object_id"]),
            ).fetchone()
            if existing:
                return dict(existing)
            conn.execute(
                """INSERT INTO relations
                (id, subject_id, predicate, object_id, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                tuple(record.values()),
            )
        return record

    def relations(self, entity: str | None = None) -> list[dict]:
        params: tuple = ()
        where = ""
        if entity:
            entity_id = self.get_entity(entity)["id"]
            where = "WHERE r.subject_id = ? OR r.object_id = ?"
            params = (entity_id, entity_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT r.*, s.name AS subject_name, o.name AS object_name
                FROM relations r
                JOIN entities s ON s.id = r.subject_id
                JOIN entities o ON o.id = r.object_id
                {where} ORDER BY r.created_at""",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def link_entity(
        self,
        target_type: str,
        target_id: str,
        entity: str,
        *,
        role: str = "about",
    ) -> dict:
        if target_type not in {"episodic", "semantic", "rule", "state"}:
            raise ValueError("unsupported entity-link target type")
        clean_role = role.strip().lower()
        if not SLUG.fullmatch(clean_role):
            raise ValueError("entity role must be a lowercase slug")
        entity_id = self.get_entity(entity)["id"]
        record = {
            "target_type": target_type,
            "target_id": target_id,
            "entity_id": entity_id,
            "role": clean_role,
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO memory_entities
                (target_type, target_id, entity_id, role, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                tuple(record.values()),
            )
        return record

    def entity_links(self, target_type: str, target_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT me.*, e.name, e.type FROM memory_entities me
                JOIN entities e ON e.id = me.entity_id
                WHERE me.target_type = ? AND me.target_id = ? ORDER BY e.name""",
                (target_type, target_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def append_event(
        self,
        text: str,
        *,
        source: str = "user",
        tags: Iterable[str] = (),
        promote_to: str | None = None,
        rule_pattern: str | None = None,
        entities: Iterable[str] = (),
    ) -> dict:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("event text is required")
        if promote_to not in {None, "semantic", "rule"}:
            raise ValueError("event promotion target must be semantic or rule")
        entity_ids = [self.get_entity(reference)["id"] for reference in entities]
        record = {
            "id": new_id("evt"),
            "type": "episodic",
            "text": clean_text,
            "source": source,
            "tags": sorted(set(tags)),
            "promote_to": promote_to,
            "rule_pattern": rule_pattern,
            "entity_ids": list(dict.fromkeys(entity_ids)),
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

    def search_events(self, query: str, limit: int = 5, entity_id: str | None = None) -> list[dict]:
        records = self.events()
        if entity_id:
            records = [
                record for record in records
                if not record.get("entity_ids") or entity_id in record.get("entity_ids", [])
            ]
        results = ranked(records, query, limit=limit)
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
        entities: Iterable[str] = (),
    ) -> dict:
        clean = text.strip()
        if not clean:
            raise ValueError("knowledge text is required")
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute("SELECT * FROM knowledge WHERE content_hash = ?", (digest,)).fetchone()
            if existing:
                record = self._knowledge_row(existing)
                for entity in entities:
                    self.link_entity("semantic", record["id"], entity)
                record["entity_ids"] = [
                    link["entity_id"] for link in self.entity_links("semantic", record["id"])
                ]
                return record
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
        for entity in entities:
            self.link_entity("semantic", record_id, entity)
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
        record = self._knowledge_row(row)
        record["entity_ids"] = [
            link["entity_id"] for link in self.entity_links("semantic", record_id)
        ]
        return record

    def knowledge(self, include_inactive: bool = False) -> list[dict]:
        where = "" if include_inactive else "WHERE status = 'active'"
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM knowledge {where} ORDER BY created_at").fetchall()
        records = []
        for row in rows:
            record = self._knowledge_row(row)
            record["entity_ids"] = [
                link["entity_id"] for link in self.entity_links("semantic", record["id"])
            ]
            records.append(record)
        return records

    def search_knowledge(self, query: str, limit: int = 5, entity_id: str | None = None) -> list[dict]:
        records = self.knowledge()
        if entity_id:
            records = [
                record for record in records
                if not record.get("entity_ids") or entity_id in record.get("entity_ids", [])
            ]
        results = ranked(records, query, limit=limit)
        for result in results:
            result["component"] = "ATL"
            result["kind"] = "semantic"
            result["backend"] = "local-bm25"
        return results

    def add_rule(
        self,
        pattern: str,
        *,
        effect: str = "block",
        reason: str,
        source: str = "user",
        entities: Iterable[str] = (),
    ) -> dict:
        if effect not in {"block", "warn"}:
            raise ValueError("rule effect must be block or warn")
        if not reason.strip():
            raise ValueError("rule reason is required")
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
        for entity in entities:
            self.link_entity("rule", record["id"], entity)
        record["entity_ids"] = [
            link["entity_id"] for link in self.entity_links("rule", record["id"])
        ]
        return record

    def rules(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM rules WHERE enabled = 1 ORDER BY created_at").fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["entity_ids"] = [
                link["entity_id"] for link in self.entity_links("rule", record["id"])
            ]
            records.append(record)
        return records

    def set_state(self, key: str, value, *, source: str = "user", entity: str | None = None) -> dict:
        clean_key = key.strip()
        if not clean_key:
            raise ValueError("state key is required")
        now = utc_now()
        payload = json.dumps(value, ensure_ascii=False)
        if entity:
            entity_id = self.get_entity(entity)["id"]
            with self.connect() as conn:
                conn.execute(
                    """INSERT INTO entity_state (entity_id, key, value_json, source, updated_at)
                    VALUES (?, ?, ?, ?, ?) ON CONFLICT(entity_id, key) DO UPDATE SET
                    value_json=excluded.value_json, source=excluded.source, updated_at=excluded.updated_at""",
                    (entity_id, clean_key, payload, source, now),
                )
            return {
                "key": clean_key,
                "value": value,
                "source": source,
                "entity_id": entity_id,
                "updated_at": now,
            }
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO numerical_state (key, value_json, source, updated_at)
                VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json, source=excluded.source, updated_at=excluded.updated_at""",
                (clean_key, payload, source, now),
            )
        return {"key": clean_key, "value": value, "source": source, "entity_id": None, "updated_at": now}

    def states(self, entity: str | None = None, *, include_global: bool = True) -> list[dict]:
        records = []
        with self.connect() as conn:
            if include_global:
                rows = conn.execute("SELECT * FROM numerical_state ORDER BY key").fetchall()
                records.extend(
                    {
                        "key": row["key"],
                        "value": json.loads(row["value_json"]),
                        "source": row["source"],
                        "entity_id": None,
                        "updated_at": row["updated_at"],
                    }
                    for row in rows
                )
            if entity:
                entity_id = self.get_entity(entity)["id"]
                scoped = conn.execute(
                    "SELECT * FROM entity_state WHERE entity_id = ? ORDER BY key", (entity_id,)
                ).fetchall()
                scoped_records = [
                    {
                        "key": row["key"],
                        "value": json.loads(row["value_json"]),
                        "source": row["source"],
                        "entity_id": row["entity_id"],
                        "updated_at": row["updated_at"],
                    }
                    for row in scoped
                ]
                scoped_keys = {record["key"] for record in scoped_records}
                records = [record for record in records if record["key"] not in scoped_keys]
                records.extend(scoped_records)
        return records

    def search_states(self, query: str, limit: int = 5, entity: str | None = None) -> list[dict]:
        documents = []
        for state in self.states(entity):
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
            scoped_states = conn.execute("SELECT COUNT(*) FROM entity_state").fetchone()[0]
            entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            relations = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        return {
            "episodic": len(self.events()), "semantic": knowledge,
            "rules": rules, "numerical_state": states + scoped_states,
            "entities": entities, "relations": relations,
            "audit_events": len(self._read_jsonl(self.audit_path)),
            "checkpoints": len(self._read_jsonl(self.checkpoints_path)),
        }
