"""Local-first stores for differentiated memory and audit events."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

try:  # Python 3.11+; the compatibility fallback keeps Python 3.10 support.
    from re import _parser as _regex_parser
except ImportError:  # pragma: no cover - exercised on Python 3.10
    import sre_parse as _regex_parser

from .config import write_default_config
from .migrations import migrate_loop_schema
from .privacy import (
    create_private_file,
    ensure_private_directory,
    exclusive_file_lock,
    open_private_append,
    open_private_lock,
)
from .text import ranked


LIFECYCLE_OPERATIONS = {
    "keep", "compact", "archive", "migrate-to-knowledge-base",
    "migrate-to-rules", "delete", "split",
}
SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
MAX_RULE_PATTERN_BYTES = 1024
MAX_RULE_REASON_BYTES = 1024
MAX_RULE_ACTION_BYTES = 16 * 1024
MAX_RULE_FIXED_REPEAT = 1024
MAX_ACTIVE_RULES = 256


class _ClosingConnection(sqlite3.Connection):
    """Give internal ``with store.connect()`` blocks close-on-exit semantics."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def validate_rule_reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise ValueError("rule reason must be a string")
    clean = reason.strip()
    if not clean:
        raise ValueError("rule reason is required")
    if len(clean.encode("utf-8", errors="surrogatepass")) > MAX_RULE_REASON_BYTES:
        raise ValueError(f"rule reason exceeds {MAX_RULE_REASON_BYTES} bytes")
    return clean


def _rule_field_sha256(value: object) -> str:
    """Hash malformed legacy fields without assuming SQLite type affinity held."""
    if isinstance(value, str):
        raw = value.encode("utf-8", errors="surrogatepass")
    elif isinstance(value, bytes):
        raw = b"sqlite-blob\0" + value
    else:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda item: f"<{type(item).__name__}>",
        )
        raw = rendered.encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def _validate_rule_tokens(
    tokens,
    *,
    inside_repeat: bool = False,
    variable_repeats: list[int] | None = None,
) -> None:
    """Reject regex structures that can make backtracking unbounded."""
    if variable_repeats is None:
        variable_repeats = [0]
    for operation, argument in tokens:
        name = str(operation)
        if name.startswith("GROUPREF") or name == "CALL":
            raise ValueError("procedural rule patterns cannot use backreferences or conditionals")
        if name in {"MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"}:
            if inside_repeat:
                raise ValueError("procedural rule patterns cannot contain nested quantifiers")
            minimum, maximum, repeated = argument
            if maximum != _regex_parser.MAXREPEAT and maximum > MAX_RULE_FIXED_REPEAT:
                raise ValueError(
                    f"procedural rule repeat exceeds {MAX_RULE_FIXED_REPEAT}"
                )
            if minimum != maximum:
                variable_repeats[0] += 1
                if variable_repeats[0] > 1:
                    raise ValueError(
                        "procedural rule patterns cannot contain multiple variable quantifiers"
                    )
            _validate_rule_tokens(
                repeated,
                inside_repeat=True,
                variable_repeats=variable_repeats,
            )
        elif name == "SUBPATTERN":
            _validate_rule_tokens(
                argument[-1],
                inside_repeat=inside_repeat,
                variable_repeats=variable_repeats,
            )
        elif name == "BRANCH":
            if inside_repeat:
                raise ValueError("procedural rule patterns cannot repeat an alternation")
            for branch in argument[1]:
                _validate_rule_tokens(
                    branch,
                    inside_repeat=inside_repeat,
                    variable_repeats=variable_repeats,
                )
        elif name in {"ASSERT", "ASSERT_NOT"}:
            if inside_repeat:
                raise ValueError("procedural rule patterns cannot repeat a lookaround")
            _validate_rule_tokens(
                argument[-1],
                inside_repeat=inside_repeat,
                variable_repeats=variable_repeats,
            )
        elif name == "ATOMIC_GROUP":
            _validate_rule_tokens(
                argument,
                inside_repeat=inside_repeat,
                variable_repeats=variable_repeats,
            )


@lru_cache(maxsize=256)
def compile_safe_rule_pattern(pattern: str) -> re.Pattern[str]:
    """Compile the deliberately small, backtracking-bounded rule subset."""
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("procedural rule pattern is required")
    if len(pattern.encode("utf-8", errors="surrogatepass")) > MAX_RULE_PATTERN_BYTES:
        raise ValueError(
            f"procedural rule pattern exceeds {MAX_RULE_PATTERN_BYTES} bytes"
        )
    try:
        parsed = _regex_parser.parse(pattern)
        variable_repeats = [0]
        _validate_rule_tokens(parsed, variable_repeats=variable_repeats)
        if variable_repeats[0]:
            first = next(iter(parsed), None)
            anchored = bool(
                first
                and str(first[0]) == "AT"
                and str(first[1]) in {"AT_BEGINNING", "AT_BEGINNING_STRING"}
                and not (
                    str(first[1]) == "AT_BEGINNING"
                    and parsed.state.flags & re.MULTILINE
                )
            )
            if not anchored:
                raise ValueError(
                    "procedural rule patterns with a variable quantifier "
                    "must begin with ^ or \\A and cannot use multiline mode"
                )
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid procedural rule pattern: {exc}") from exc


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
        ensure_private_directory(self.home)
        write_default_config(self.home)
        for path in (self.events_path, self.audit_path, self.checkpoints_path):
            create_private_file(path)
        create_private_file(self.db_path)
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
                    global_scope INTEGER NOT NULL DEFAULT 1,
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
                CREATE TABLE IF NOT EXISTS rule_admin_events (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    pattern_sha256 TEXT NOT NULL,
                    rule_reason_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(rule_id) REFERENCES rules(id)
                );
                CREATE INDEX IF NOT EXISTS idx_rule_admin_events_rule
                    ON rule_admin_events(rule_id, created_at);
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
                CREATE TABLE IF NOT EXISTS imported_events (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    promote_to TEXT,
                    rule_pattern TEXT,
                    entity_ids_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS import_batches (
                    id TEXT PRIMARY KEY,
                    review_id TEXT NOT NULL,
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
                );
                CREATE TABLE IF NOT EXISTS import_ledger (
                    id TEXT PRIMARY KEY,
                    entry_fingerprint TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    decision_digest TEXT NOT NULL,
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
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES import_batches(id),
                    FOREIGN KEY(entity_id) REFERENCES entities(id)
                );
                """
            )
            knowledge_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(knowledge)")
            }
            if "global_scope" not in knowledge_columns:
                conn.execute(
                    "ALTER TABLE knowledge ADD COLUMN global_scope INTEGER NOT NULL DEFAULT 1"
                )
                conn.execute(
                    """UPDATE knowledge SET global_scope = 0
                    WHERE EXISTS (
                        SELECT 1 FROM memory_entities me
                        WHERE me.target_type = 'semantic' AND me.target_id = knowledge.id
                    )"""
                )

            ledger_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(import_ledger)")
            }
            if "entry_fingerprint" not in ledger_columns:
                conn.execute("ALTER TABLE import_ledger RENAME TO import_ledger_legacy")
                conn.execute(
                    """CREATE TABLE import_ledger (
                        id TEXT PRIMARY KEY,
                        entry_fingerprint TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        decision_digest TEXT NOT NULL,
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
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(batch_id) REFERENCES import_batches(id),
                        FOREIGN KEY(entity_id) REFERENCES entities(id)
                    )"""
                )
                conn.execute(
                    """INSERT INTO import_ledger
                    (id, entry_fingerprint, entity_id, decision_digest, batch_id,
                     source_path, source_sha256, fragment_sha256, line_start,
                     line_end, memory_type, target_id, status, payload_json, created_at)
                    SELECT l.fingerprint, l.fingerprint, b.entity_id,
                           'legacy:' || l.memory_type, l.batch_id, l.source_path,
                           l.source_sha256, l.fragment_sha256, l.line_start,
                           l.line_end, l.memory_type, l.target_id, l.status,
                           l.payload_json, l.created_at
                    FROM import_ledger_legacy l
                    JOIN import_batches b ON b.id = l.batch_id"""
                )
                conn.execute("DROP TABLE import_ledger_legacy")
            conn.execute("DROP INDEX IF EXISTS idx_import_ledger_batch")
            conn.execute(
                "CREATE INDEX idx_import_ledger_batch ON import_ledger(batch_id, status)"
            )
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_import_ledger_active
                ON import_ledger(entry_fingerprint, entity_id, decision_digest)
                WHERE status = 'active'"""
            )
            legacy_review_unique = False
            for index in conn.execute("PRAGMA index_list(import_batches)"):
                if index["origin"] != "u":
                    continue
                columns = [
                    row["name"]
                    for row in conn.execute(
                        f"PRAGMA index_info({json.dumps(index['name'])})"
                    )
                ]
                if columns == ["review_id"]:
                    legacy_review_unique = True
                    break
            if legacy_review_unique:
                conn.commit()
                conn.execute("PRAGMA foreign_keys = OFF")
                try:
                    conn.executescript(
                        """
                        BEGIN IMMEDIATE;
                        CREATE TABLE import_batches_new (
                            id TEXT PRIMARY KEY,
                            review_id TEXT NOT NULL,
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
                        );
                        INSERT INTO import_batches_new
                        SELECT * FROM import_batches;
                        DROP TABLE import_batches;
                        ALTER TABLE import_batches_new RENAME TO import_batches;
                        COMMIT;
                        """
                    )
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.execute("PRAGMA foreign_keys = ON")
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError("import batch migration violated foreign keys")
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_import_batches_current_review
                ON import_batches(review_id)
                WHERE status IN ('applying', 'applied')"""
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_import_batches_review_history
                ON import_batches(review_id, created_at)"""
            )
            lineage_table_preexisting = conn.execute(
                """SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'knowledge_supersessions'"""
            ).fetchone() is not None
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS import_dependencies (
                    id TEXT PRIMARY KEY,
                    dependent_batch_id TEXT NOT NULL,
                    provider_ledger_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(dependent_batch_id, provider_ledger_id),
                    FOREIGN KEY(dependent_batch_id) REFERENCES import_batches(id),
                    FOREIGN KEY(provider_ledger_id) REFERENCES import_ledger(id)
                    )"""
                )
                conn.execute(
                    """CREATE INDEX IF NOT EXISTS idx_import_dependencies_provider
                    ON import_dependencies(provider_ledger_id, dependent_batch_id)"""
                )
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS knowledge_supersessions (
                    id TEXT PRIMARY KEY,
                    old_id TEXT NOT NULL,
                    replacement_id TEXT NOT NULL,
                    entity_id TEXT,
                    source TEXT NOT NULL,
                    batch_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    rolled_back_at TEXT,
                    FOREIGN KEY(old_id) REFERENCES knowledge(id),
                    FOREIGN KEY(replacement_id) REFERENCES knowledge(id),
                    FOREIGN KEY(entity_id) REFERENCES entities(id),
                    FOREIGN KEY(batch_id) REFERENCES import_batches(id)
                    )"""
                )
                conn.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_supersessions_global_active
                    ON knowledge_supersessions(old_id)
                    WHERE entity_id IS NULL AND status = 'active'"""
                )
                conn.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_supersessions_scoped_active
                    ON knowledge_supersessions(old_id, entity_id)
                    WHERE entity_id IS NOT NULL AND status = 'active'"""
                )
                conn.execute(
                    """CREATE INDEX IF NOT EXISTS idx_knowledge_supersessions_replacement
                    ON knowledge_supersessions(replacement_id, status)"""
                )
                if not lineage_table_preexisting:
                    legacy_rows = conn.execute(
                        """SELECT replacement.id AS replacement_id,
                                  replacement.supersedes AS old_id,
                                  replacement.status AS replacement_status,
                                  replacement.created_at,
                                  replacement.updated_at
                        FROM knowledge replacement
                        JOIN knowledge old ON old.id = replacement.supersedes
                        WHERE replacement.supersedes IS NOT NULL
                          AND replacement.id != replacement.supersedes
                        ORDER BY replacement.supersedes,
                                 CASE WHEN replacement.status = 'active' THEN 0 ELSE 1 END,
                                 replacement.updated_at DESC,
                                 replacement.created_at DESC,
                                 replacement.id"""
                    ).fetchall()
                    selected_old_ids: set[str] = set()
                    for row in legacy_rows:
                        old_id = row["old_id"]
                        replacement_id = row["replacement_id"]
                        digest = hashlib.sha256(
                            f"legacy-v0.4\0{old_id}\0{replacement_id}".encode("utf-8")
                        ).hexdigest()
                        status = (
                            "active"
                            if old_id not in selected_old_ids
                            else "legacy_conflict"
                        )
                        selected_old_ids.add(old_id)
                        conn.execute(
                            """INSERT INTO knowledge_supersessions
                            (id, old_id, replacement_id, entity_id, source,
                             batch_id, status, created_at, rolled_back_at)
                            VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, NULL)""",
                            (
                                f"sup_{digest[:12]}",
                                old_id,
                                replacement_id,
                                "migration:v0.5:legacy-knowledge.supersedes",
                                status,
                                row["created_at"],
                            ),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        with self.connect() as conn:
            migrate_loop_schema(conn)

        self.quarantine_unsafe_rules()
        # SQLite is the authoritative safety receipt.  Audit JSONL is an
        # inspectable mirror and must never prevent startup or enforcement;
        # every initialization retries any mirror interrupted by a crash or
        # filesystem error.
        self.mirror_rule_admin_events()

        ignore_path = self.home / ".gitignore"
        create_private_file(ignore_path, b"*\n")

    def connect(self) -> sqlite3.Connection:
        create_private_file(self.db_path)
        conn = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            factory=_ClosingConnection,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    @staticmethod
    def _append_jsonl_unlocked(path: Path, record: dict) -> None:
        payload = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        with open_private_append(path) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _repair_jsonl_tail_unlocked(path: Path) -> Path | None:
        """Quarantine and remove an unterminated final physical line.

        Callers must hold the stream's sidecar lock.  A committed JSONL record
        always ends in a newline, so an unterminated tail is crash evidence,
        not a record that is safe to extend.
        """
        if not path.exists():
            return None
        with open_private_lock(path) as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size == 0:
                return None
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) == b"\n":
                return None

            cursor = size
            tail_start = 0
            while cursor:
                start = max(0, cursor - 64 * 1024)
                handle.seek(start)
                chunk = handle.read(cursor - start)
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    tail_start = start + newline + 1
                    break
                cursor = start

            handle.seek(tail_start)
            tail = handle.read(size - tail_start)
            digest = hashlib.sha256(tail).hexdigest()
            quarantine = path.with_name(
                f"{path.name}.truncated-{digest}.bin"
            )
            created = create_private_file(quarantine, tail)
            if not created and quarantine.read_bytes() != tail:
                raise ValueError(
                    f"truncated JSONL evidence conflicts with quarantine: {quarantine}"
                )
            handle.truncate(tail_start)
            handle.flush()
            os.fsync(handle.fileno())
            return quarantine

    @classmethod
    def _append_jsonl(cls, path: Path, record: dict) -> None:
        """Append one record under the same cross-platform stream lock."""
        lock_path = path.with_name(f"{path.name}.lock")
        with open_private_lock(lock_path) as lock:
            with exclusive_file_lock(lock):
                cls._repair_jsonl_tail_unlocked(path)
                cls._append_jsonl_unlocked(path, record)

    @classmethod
    def _append_jsonl_once(cls, path: Path, record: dict) -> bool:
        """Append one stable-id record exactly once across local hook processes."""
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("idempotent JSONL records require a stable id")
        lock_path = path.with_name(f"{path.name}.lock")
        with open_private_lock(lock_path) as lock:
            with exclusive_file_lock(lock):
                cls._repair_jsonl_tail_unlocked(path)
                if any(
                    item.get("id") == record_id
                    for item in cls._read_jsonl_unlocked(path)
                ):
                    return False
                cls._append_jsonl_unlocked(path, record)
                return True

    @staticmethod
    def _read_jsonl_unlocked(path: Path) -> list[dict]:
        records = []
        if not path.exists():
            return records
        with open_private_lock(path) as handle:
            handle.seek(0)
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                if not raw_line.endswith(b"\n"):
                    # Appenders commit complete physical lines.  Never expose
                    # an unterminated tail as a record, even if its JSON text
                    # happens to be syntactically complete.
                    continue
                try:
                    value = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    records.append(value)
        return records

    @classmethod
    def _read_jsonl(cls, path: Path) -> list[dict]:
        lock_path = path.with_name(f"{path.name}.lock")
        with open_private_lock(lock_path) as lock:
            with exclusive_file_lock(lock):
                return cls._read_jsonl_unlocked(path)

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
            if target_type == "semantic":
                existing = conn.execute(
                    "SELECT id FROM knowledge WHERE id = ?", (target_id,)
                ).fetchone()
                if not existing:
                    raise KeyError(f"unknown knowledge id: {target_id}")
                conn.execute(
                    """UPDATE knowledge SET global_scope = 0, updated_at = ?
                    WHERE id = ?""",
                    (record["created_at"], target_id),
                )
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

    def append_event_once(self, record: dict) -> bool:
        """Mirror an admitted autonomous event without duplicating retries."""
        self._validate_event_record(record)
        return self._append_jsonl_once(self.events_path, dict(record))

    def _validate_event_record(self, record: dict) -> None:
        if record.get("type") != "episodic":
            raise ValueError("autonomous event records must be episodic")
        if not str(record.get("text", "")).strip():
            raise ValueError("event text is required")
        entity_ids = record.get("entity_ids") or []
        if not isinstance(entity_ids, list):
            raise ValueError("event entity_ids must be a list")
        for reference in entity_ids:
            self.get_entity(reference)

    def events(self, include_inactive: bool = False) -> list[dict]:
        records = self._read_jsonl(self.events_path)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM imported_events ORDER BY created_at"
            ).fetchall()
        for row in rows:
            record = dict(row)
            record["tags"] = json.loads(record.pop("tags_json"))
            record["entity_ids"] = json.loads(record.pop("entity_ids_json"))
            record["type"] = "episodic"
            status = record.pop("status")
            if include_inactive or status == "active":
                records.append(record)
        records.sort(key=lambda item: item.get("created_at", ""))
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
        entity_refs = list(entities)
        if supersedes and entity_refs:
            raise ValueError(
                "scoped supersession requires supersede_knowledge_for_entity"
            )
        entity_ids = list(
            dict.fromkeys(self.get_entity(reference)["id"] for reference in entity_refs)
        )
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        now = utc_now()
        existing_id: str | None = None
        existing_is_global = False
        with self.connect() as conn:
            if supersedes:
                old = conn.execute(
                    "SELECT id, status, global_scope FROM knowledge WHERE id = ?",
                    (supersedes,),
                ).fetchone()
                if not old or old["status"] != "active":
                    raise ValueError(f"supersession target is not active: {supersedes}")
                if not old["global_scope"]:
                    raise ValueError(
                        "project-scoped supersession requires "
                        "supersede_knowledge_for_entity"
                    )
            existing = conn.execute("SELECT * FROM knowledge WHERE content_hash = ?", (digest,)).fetchone()
            if existing:
                existing_id = existing["id"]
                existing_is_global = bool(existing["global_scope"])
                if supersedes == existing_id:
                    raise ValueError("replacement knowledge is identical to the target")
                if not entity_refs and not existing["global_scope"]:
                    raise ValueError(
                        "identical semantic memory is project-scoped; pass an entity "
                        "instead of widening it to global scope"
                    )
                if supersedes:
                    conn.execute(
                        """UPDATE knowledge SET status = 'active',
                        supersedes = COALESCE(supersedes, ?), updated_at = ?
                        WHERE id = ?""",
                        (supersedes, now, existing_id),
                    )
                    conn.execute(
                        """UPDATE knowledge SET status = 'superseded', updated_at = ?
                        WHERE id = ?""",
                        (now, supersedes),
                    )
            else:
                record_id = new_id("mem")
                conn.execute(
                    """INSERT INTO knowledge
                    (id, text, source, tags_json, status, content_hash, global_scope,
                     supersedes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
                    (
                        record_id,
                        clean,
                        source,
                        json.dumps(sorted(set(tags)), ensure_ascii=False),
                        digest,
                        0 if entity_refs else 1,
                        supersedes,
                        now,
                        now,
                    ),
                )
                if supersedes:
                    conn.execute(
                        "UPDATE knowledge SET status = 'superseded', updated_at = ? WHERE id = ?",
                        (now, supersedes),
                    )
            replacement_id = existing_id or record_id
            if supersedes:
                self._record_knowledge_supersession(
                    conn,
                    old_id=supersedes,
                    replacement_id=replacement_id,
                    entity_id=None,
                    source=source,
                    created_at=now,
                )
            if not existing_is_global:
                for entity_id in entity_ids:
                    conn.execute(
                        """INSERT OR IGNORE INTO memory_entities
                        (target_type, target_id, entity_id, role, created_at)
                        VALUES ('semantic', ?, ?, 'about', ?)""",
                        (replacement_id, entity_id, now),
                    )
        record_id = existing_id or record_id
        return self.get_knowledge(record_id)

    @staticmethod
    def _knowledge_row(row: sqlite3.Row) -> dict:
        record = dict(row)
        record["tags"] = json.loads(record.pop("tags_json"))
        record.pop("global_scope", None)
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
        record["supersession_edges"] = self.knowledge_supersessions(
            replacement_id=record_id
        )
        record["supersedes_ids"] = [
            edge["old_id"] for edge in record["supersession_edges"]
        ]
        return record

    def _record_knowledge_supersession(
        self,
        conn: sqlite3.Connection,
        *,
        old_id: str,
        replacement_id: str,
        entity_id: str | None,
        source: str,
        created_at: str,
        batch_id: str | None = None,
    ) -> dict:
        scope_clause = "entity_id IS NULL" if entity_id is None else "entity_id = ?"
        parameters: tuple[str, ...] = (old_id,) if entity_id is None else (old_id, entity_id)
        existing = conn.execute(
            f"""SELECT * FROM knowledge_supersessions
            WHERE old_id = ? AND {scope_clause} AND status = 'active'""",
            parameters,
        ).fetchone()
        if existing:
            if existing["replacement_id"] != replacement_id:
                raise ValueError(
                    "supersession scope already has a different active replacement"
                )
            return dict(existing)
        record = {
            "id": new_id("sup"),
            "old_id": old_id,
            "replacement_id": replacement_id,
            "entity_id": entity_id,
            "source": source,
            "batch_id": batch_id,
            "status": "active",
            "created_at": created_at,
            "rolled_back_at": None,
        }
        conn.execute(
            """INSERT INTO knowledge_supersessions
            (id, old_id, replacement_id, entity_id, source, batch_id, status,
             created_at, rolled_back_at)
            VALUES (:id, :old_id, :replacement_id, :entity_id, :source,
                    :batch_id, :status, :created_at, :rolled_back_at)""",
            record,
        )
        return record

    def knowledge_supersessions(
        self,
        *,
        old_id: str | None = None,
        replacement_id: str | None = None,
        entity_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[dict]:
        clauses: list[str] = []
        parameters: list[str] = []
        if old_id:
            clauses.append("old_id = ?")
            parameters.append(old_id)
        if replacement_id:
            clauses.append("replacement_id = ?")
            parameters.append(replacement_id)
        if entity_id:
            clauses.append("entity_id = ?")
            parameters.append(entity_id)
        if not include_inactive:
            clauses.append("status = 'active'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM knowledge_supersessions {where} ORDER BY created_at, id",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def supersede_knowledge_for_entity(
        self,
        old_id: str,
        new_text: str,
        entity: str,
        *,
        source: str = "user",
        tags: Iterable[str] = (),
    ) -> dict:
        """Replace one entity's fact without changing other entity scopes."""
        clean = new_text.strip()
        if not clean:
            raise ValueError("replacement knowledge text is required")
        entity_id = self.get_entity(entity)["id"]
        content_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                """SELECT id, status, global_scope FROM knowledge WHERE id = ?""",
                (old_id,),
            ).fetchone()
            if not old or old["status"] != "active":
                conn.rollback()
                raise ValueError(f"supersession target is not active: {old_id}")
            if old["global_scope"]:
                conn.rollback()
                raise ValueError("entity-scoped supersession cannot replace global memory")
            linked = conn.execute(
                """SELECT 1 FROM memory_entities
                WHERE target_type = 'semantic' AND target_id = ? AND entity_id = ?""",
                (old_id, entity_id),
            ).fetchone()
            if not linked:
                conn.rollback()
                raise ValueError("supersession target is not linked to the selected entity")
            existing = conn.execute(
                """SELECT id, status, global_scope FROM knowledge
                WHERE content_hash = ?""",
                (content_hash,),
            ).fetchone()
            if existing and existing["id"] == old_id:
                conn.rollback()
                raise ValueError("replacement knowledge is identical to the target")
            if existing:
                if existing["status"] != "active":
                    conn.rollback()
                    raise ValueError(
                        "identical replacement knowledge exists but is inactive"
                    )
                replacement_id = existing["id"]
                replacement_is_global = bool(existing["global_scope"])
                conn.execute(
                    """UPDATE knowledge SET supersedes = COALESCE(supersedes, ?),
                    updated_at = ? WHERE id = ?""",
                    (old_id, now, replacement_id),
                )
            else:
                replacement_id = new_id("mem")
                conn.execute(
                    """INSERT INTO knowledge
                    (id, text, source, tags_json, status, content_hash,
                     global_scope, supersedes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'active', ?, 0, ?, ?, ?)""",
                    (
                        replacement_id,
                        clean,
                        source,
                        json.dumps(sorted(set(tags)), ensure_ascii=False),
                        content_hash,
                        old_id,
                        now,
                        now,
                    ),
                )
                replacement_is_global = False
            conn.execute(
                """DELETE FROM memory_entities
                WHERE target_type = 'semantic' AND target_id = ? AND entity_id = ?""",
                (old_id, entity_id),
            )
            remaining = conn.execute(
                """SELECT COUNT(*) FROM memory_entities
                WHERE target_type = 'semantic' AND target_id = ?""",
                (old_id,),
            ).fetchone()[0]
            if not remaining:
                conn.execute(
                    """UPDATE knowledge SET status = 'superseded', updated_at = ?
                    WHERE id = ?""",
                    (now, old_id),
                )
            if not replacement_is_global:
                conn.execute(
                    """INSERT OR IGNORE INTO memory_entities
                    (target_type, target_id, entity_id, role, created_at)
                    VALUES ('semantic', ?, ?, 'about', ?)""",
                    (replacement_id, entity_id, now),
                )
            self._record_knowledge_supersession(
                conn,
                old_id=old_id,
                replacement_id=replacement_id,
                entity_id=entity_id,
                source=source,
                created_at=now,
            )
            conn.commit()
        return self.get_knowledge(replacement_id)

    def knowledge(
        self,
        include_inactive: bool = False,
        entity_id: str | None = None,
    ) -> list[dict]:
        clauses = []
        params: list[str] = []
        if not include_inactive:
            clauses.append("status = 'active'")
        if entity_id:
            clauses.append(
                """(global_scope = 1 OR EXISTS (
                    SELECT 1 FROM memory_entities me
                    WHERE me.target_type = 'semantic'
                      AND me.target_id = knowledge.id
                      AND me.entity_id = ?
                ))"""
            )
            params.append(entity_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM knowledge {where} ORDER BY created_at", params
            ).fetchall()
        records = []
        for row in rows:
            record = self._knowledge_row(row)
            record["entity_ids"] = [
                link["entity_id"] for link in self.entity_links("semantic", record["id"])
            ]
            records.append(record)
        return records

    def search_knowledge(self, query: str, limit: int = 5, entity_id: str | None = None) -> list[dict]:
        records = self.knowledge(entity_id=entity_id)
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
        clean_reason = validate_rule_reason(reason)
        compile_safe_rule_pattern(pattern)
        entity_ids = list(
            dict.fromkeys(self.get_entity(reference)["id"] for reference in entities)
        )
        record = {
            "id": new_id("rule"), "pattern": pattern, "effect": effect,
            "reason": clean_reason, "source": source, "enabled": 1,
            "created_at": utc_now(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO rules (id, pattern, effect, reason, source, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                tuple(record[key] for key in ("id", "pattern", "effect", "reason", "source", "enabled", "created_at")),
            )
            for entity_id in entity_ids:
                conn.execute(
                    """INSERT OR IGNORE INTO memory_entities
                    (target_type, target_id, entity_id, role, created_at)
                    VALUES ('rule', ?, ?, 'about', ?)""",
                    (record["id"], entity_id, record["created_at"]),
                )
        record["entity_ids"] = [
            link["entity_id"] for link in self.entity_links("rule", record["id"])
        ]
        return record

    @staticmethod
    def _rule_safety_error(record: dict) -> str | None:
        try:
            if record.get("effect") not in {"block", "warn"}:
                raise ValueError("rule effect must be block or warn")
            compile_safe_rule_pattern(record["pattern"])
            validate_rule_reason(record["reason"])
        except ValueError as exc:
            return re.sub(r"\s+", " ", str(exc)).strip()[:1024]
        return None

    @staticmethod
    def _rule_admin_event(
        conn: sqlite3.Connection,
        record: dict,
        *,
        operation: str,
        reason: str,
    ) -> dict:
        now = utc_now()
        event = {
            "id": new_id("ruleevt"),
            "rule_id": record["id"],
            "operation": operation,
            "reason": reason,
            "pattern_sha256": _rule_field_sha256(record["pattern"]),
            "rule_reason_sha256": _rule_field_sha256(record["reason"]),
            "created_at": now,
        }
        conn.execute(
            """INSERT INTO rule_admin_events
            (id, rule_id, operation, reason, pattern_sha256,
             rule_reason_sha256, created_at)
            VALUES (:id, :rule_id, :operation, :reason, :pattern_sha256,
                    :rule_reason_sha256, :created_at)""",
            event,
        )
        return event

    def quarantine_unsafe_rules(self) -> list[dict]:
        """Register unsafe legacy rules without silently changing enforcement."""
        events: list[dict] = []
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM rules WHERE enabled = 1 ORDER BY created_at"
            ).fetchall()
            for row in rows:
                record = dict(row)
                error = self._rule_safety_error(record)
                if not error:
                    continue
                pattern_sha256 = _rule_field_sha256(record["pattern"])
                latest = conn.execute(
                    """SELECT operation, pattern_sha256 FROM rule_admin_events
                    WHERE rule_id=? ORDER BY created_at DESC LIMIT 1""",
                    (record["id"],),
                ).fetchone()
                if (
                    latest
                    and latest["operation"] == "auto-quarantine"
                    and latest["pattern_sha256"] == pattern_sha256
                ):
                    continue
                events.append(
                    self._rule_admin_event(
                        conn,
                        record,
                        operation="auto-quarantine",
                        reason=f"v0.6 safe-pattern admission: {error}"[:1024],
                    )
                )
            conn.commit()
        return events

    def unresolved_rule_quarantines(self) -> list[dict]:
        """Return rules whose latest admin event still requires acknowledgment."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT r.*, e.id AS quarantine_event_id,
                          e.reason AS quarantine_reason,
                          e.created_at AS quarantined_at
                FROM rules r
                JOIN rule_admin_events e ON e.id = (
                    SELECT latest.id FROM rule_admin_events latest
                    WHERE latest.rule_id = r.id
                    ORDER BY latest.created_at DESC LIMIT 1
                )
                WHERE e.operation = 'auto-quarantine'
                ORDER BY e.created_at"""
            ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["entity_ids"] = [
                link["entity_id"] for link in self.entity_links("rule", record["id"])
            ]
            records.append(record)
        return records

    def applicable_rule_quarantines(self, entity: str | None = None) -> list[dict]:
        """Return unresolved quarantines that can affect one execution scope.

        Rules without entity links are global.  Entity-linked rules apply only
        when that entity is selected; this mirrors the runtime gate instead of
        making an unrelated project's quarantine block every doctor/connect
        operation that shares the same local store.
        """
        entity_id = self.get_entity(entity)["id"] if entity else None
        return [
            rule
            for rule in self.unresolved_rule_quarantines()
            if not rule.get("entity_ids")
            or (entity_id is not None and entity_id in rule["entity_ids"])
        ]

    def rule_admin_events(self, rule_id: str | None = None) -> list[dict]:
        with self.connect() as conn:
            if rule_id:
                rows = conn.execute(
                    """SELECT * FROM rule_admin_events
                    WHERE rule_id=? ORDER BY created_at""",
                    (rule_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM rule_admin_events ORDER BY created_at"
                ).fetchall()
        return [dict(row) for row in rows]

    def mirror_rule_admin_events(self) -> list[str]:
        """Best-effort replay of authoritative rule-admin receipts to audit JSONL."""
        pending: list[str] = []
        for event in self.rule_admin_events():
            try:
                self.append_audit_once(
                    {**event, "id": f"audit_{event['id']}", "event": "rule_admin"}
                )
            except Exception:
                pending.append(event["id"])
        return pending

    def admin_rules(self) -> list[dict]:
        records = self.rules(include_disabled=True)
        events: dict[str, list[dict]] = {}
        for event in self.rule_admin_events():
            events.setdefault(event["rule_id"], []).append(event)
        for record in records:
            record["admin_events"] = events.get(record["id"], [])
            record["safe_pattern"] = self._rule_safety_error(record) is None
            for field in ("pattern", "effect", "reason", "source"):
                value = record.get(field)
                if not isinstance(value, str):
                    byte_count = len(value) if isinstance(value, bytes) else None
                    record[field] = {
                        "invalid_type": type(value).__name__,
                        "sha256": _rule_field_sha256(value),
                        "byte_count": byte_count,
                    }
        return records

    def disable_rule(self, rule_id: str, *, reason: str) -> dict:
        clean_reason = validate_rule_reason(reason)
        event = None
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
            if not row:
                conn.rollback()
                raise KeyError(f"unknown rule: {rule_id}")
            record = dict(row)
            latest = conn.execute(
                """SELECT operation FROM rule_admin_events
                WHERE rule_id=? ORDER BY created_at DESC LIMIT 1""",
                (rule_id,),
            ).fetchone()
            needs_acknowledgment = bool(
                latest and latest["operation"] == "auto-quarantine"
            )
            if record["enabled"] or needs_acknowledgment:
                conn.execute("UPDATE rules SET enabled=0 WHERE id=?", (rule_id,))
                event = self._rule_admin_event(
                    conn,
                    record,
                    operation="operator-disable",
                    reason=clean_reason,
                )
            conn.commit()
        if event:
            self.mirror_rule_admin_events()
        return {
            "status": "disabled" if event else "already_disabled",
            "rule_id": rule_id,
            "event": event,
        }

    def enable_rule(self, rule_id: str) -> dict:
        event = None
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
            if not row:
                conn.rollback()
                raise KeyError(f"unknown rule: {rule_id}")
            record = dict(row)
            error = self._rule_safety_error(record)
            if error:
                conn.rollback()
                raise ValueError(
                    "rule still fails current safe-pattern admission; create a "
                    f"replacement rule instead: {error}"
                )
            if not record["enabled"]:
                conn.execute("UPDATE rules SET enabled=1 WHERE id=?", (rule_id,))
                event = self._rule_admin_event(
                    conn,
                    record,
                    operation="operator-enable",
                    reason="validated against current safe-pattern admission",
                )
            conn.commit()
        if event:
            self.mirror_rule_admin_events()
        return {
            "status": "enabled" if event else "already_enabled",
            "rule_id": rule_id,
            "event": event,
        }

    def rules(self, include_disabled: bool = False) -> list[dict]:
        with self.connect() as conn:
            where = "" if include_disabled else "WHERE enabled = 1"
            rows = conn.execute(
                f"SELECT * FROM rules {where} ORDER BY created_at"
            ).fetchall()
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

    def append_audit_once(self, record: dict) -> bool:
        """Append a stable-id audit receipt once across hook retries."""
        value = dict(record)
        value.setdefault("created_at", utc_now())
        return self._append_jsonl_once(self.audit_path, value)

    def append_checkpoint(self, record: dict) -> None:
        value = dict(record)
        value.setdefault("created_at", utc_now())
        self._append_jsonl(self.checkpoints_path, value)

    def append_checkpoint_once(self, record: dict) -> bool:
        value = dict(record)
        value.setdefault("created_at", utc_now())
        return self._append_jsonl_once(self.checkpoints_path, value)

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
