from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            checksum TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            preview_text TEXT NOT NULL,
            full_text TEXT NOT NULL,
            version_group TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            parent_document_id TEXT,
            analysis_status TEXT NOT NULL DEFAULT 'pending'
        );

        CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_documents_group ON documents(version_group, version_number);

        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id, chunk_index);

        CREATE TABLE IF NOT EXISTS document_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            analysis_type TEXT NOT NULL,
            level TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_analyses_doc_type ON document_analyses(document_id, analysis_type, level);

        CREATE TABLE IF NOT EXISTS document_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_value TEXT NOT NULL,
            confidence REAL NOT NULL,
            snippet TEXT NOT NULL,
            start_index INTEGER,
            end_index INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_entities_document_id ON document_entities(document_id, entity_type);

        DROP TABLE IF EXISTS template_runs;
        DROP TABLE IF EXISTS templates;
        DROP TABLE IF EXISTS workflow_runs;
        DROP TABLE IF EXISTS workflows;
        DROP TABLE IF EXISTS notifications;
        DROP TABLE IF EXISTS messages;
        DROP TABLE IF EXISTS conversations;
        """
        with self._connect() as conn:
            conn.executescript(schema)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._write_lock:
            with self._connect() as conn:
                cursor = conn.execute(sql, params)
                conn.commit()
                return cursor.rowcount

    def executemany(self, sql: str, seq_of_params: list[tuple[Any, ...]]) -> None:
        if not seq_of_params:
            return
        with self._write_lock:
            with self._connect() as conn:
                conn.executemany(sql, seq_of_params)
                conn.commit()

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if row is None:
            return None
        return dict(row)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
