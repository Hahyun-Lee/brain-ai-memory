"""Additive SQLite migrations for the autonomous host loop.

The v0.5 memory tables remain untouched.  Hook traffic has different durability
and idempotency requirements, so it uses a separate ledger that older releases
can safely ignore.
"""

from __future__ import annotations

import sqlite3


LOOP_SCHEMA_VERSION = 3
LOOP_TABLES = {
    "loop_sessions",
    "loop_events",
    "loop_candidates",
    "loop_checkpoints",
    "handoff_deliveries",
}


def migrate_loop_schema(conn: sqlite3.Connection) -> None:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current > LOOP_SCHEMA_VERSION:
        raise RuntimeError(
            "this Brain-AI Memory build is older than the autonomous-loop database"
        )
    if current == LOOP_SCHEMA_VERSION:
        present = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        session_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(loop_sessions)")
        }
        candidate_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(loop_candidates)")
        }
        if (
            LOOP_TABLES.issubset(present)
            and "last_error_event_key" in session_columns
            and {"mirror_status", "mirrored_at"}.issubset(candidate_columns)
        ):
            return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS loop_sessions (
            host TEXT NOT NULL,
            session_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            dirty_generation INTEGER NOT NULL DEFAULT 0,
            checkpoint_generation INTEGER NOT NULL DEFAULT 0,
            changes_json TEXT NOT NULL DEFAULT '[]',
            last_event_at TEXT NOT NULL,
            last_checkpoint_id TEXT,
            last_error TEXT,
            last_error_event_key TEXT,
            PRIMARY KEY(host, session_id, entity_id),
            FOREIGN KEY(entity_id) REFERENCES entities(id)
        );

        CREATE TABLE IF NOT EXISTS loop_events (
            event_key TEXT PRIMARY KEY,
            host TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn_id TEXT,
            event_name TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            status TEXT NOT NULL,
            dirty_generation INTEGER,
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(entity_id) REFERENCES entities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_loop_events_session
            ON loop_events(host, session_id, entity_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_loop_events_name
            ON loop_events(entity_id, event_name, created_at);

        CREATE TABLE IF NOT EXISTS loop_candidates (
            id TEXT PRIMARY KEY,
            event_key TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            text TEXT NOT NULL,
            source TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            mirror_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            mirrored_at TEXT,
            UNIQUE(event_key, memory_type, evidence_hash),
            FOREIGN KEY(event_key) REFERENCES loop_events(event_key),
            FOREIGN KEY(entity_id) REFERENCES entities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_loop_candidates_status
            ON loop_candidates(entity_id, status, created_at);

        CREATE TABLE IF NOT EXISTS loop_checkpoints (
            event_key TEXT PRIMARY KEY,
            checkpoint_id TEXT NOT NULL UNIQUE,
            host TEXT NOT NULL,
            session_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            record_json TEXT NOT NULL,
            mirror_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            written_at TEXT,
            FOREIGN KEY(event_key) REFERENCES loop_events(event_key),
            FOREIGN KEY(entity_id) REFERENCES entities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_loop_checkpoints_pending
            ON loop_checkpoints(mirror_status, created_at);

        CREATE TABLE IF NOT EXISTS handoff_deliveries (
            checkpoint_id TEXT NOT NULL,
            host TEXT NOT NULL,
            session_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            status TEXT NOT NULL,
            delivered_at TEXT NOT NULL,
            acknowledged_at TEXT,
            PRIMARY KEY(checkpoint_id, host, session_id, entity_id),
            FOREIGN KEY(entity_id) REFERENCES entities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_handoff_deliveries_status
            ON handoff_deliveries(host, session_id, entity_id, status);

        """
    )
    session_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(loop_sessions)")
    }
    if "last_error_event_key" not in session_columns:
        conn.execute(
            "ALTER TABLE loop_sessions ADD COLUMN last_error_event_key TEXT"
        )
    candidate_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(loop_candidates)")
    }
    if "mirror_status" not in candidate_columns:
        conn.execute(
            """ALTER TABLE loop_candidates ADD COLUMN mirror_status TEXT
            NOT NULL DEFAULT 'pending'"""
        )
    if "mirrored_at" not in candidate_columns:
        conn.execute(
            "ALTER TABLE loop_candidates ADD COLUMN mirrored_at TEXT"
        )
    conn.execute(f"PRAGMA user_version = {LOOP_SCHEMA_VERSION}")
